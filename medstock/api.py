"""HTTP API for the assistant. The Gemini key stays on the server; the browser only talks to this.

Run locally:   uvicorn medstock.api:app --reload
Environment:   GOOGLE_API_KEY        required (set on the host, never in the front end)
               GEMINI_MODEL          optional model override
               ALLOWED_ORIGINS       comma-separated front-end URLs allowed by CORS
                                     e.g. "https://your-site.netlify.app,http://localhost:5173"
               RATE_LIMIT_PER_MIN    optional, default 10 requests per IP per minute
"""
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import llm
from .data_gen import COMMODITIES
from .tools import _clean, _data  # _data also preloads the CSVs at startup

MAX_QUESTION_CHARS = 500
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "10"))

@asynccontextmanager
async def lifespan(_app):
    _data()  # load and assess the CSVs once so the first request is fast
    yield


app = FastAPI(title="MedStock Early Warning Assistant", version="1.0", lifespan=lifespan)

origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
           if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

_hits = defaultdict(deque)  # ip -> timestamps of recent requests (in memory; resets on restart)


def _rate_limited(ip: str) -> bool:
    now, window = time.time(), _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        return True
    window.append(now)
    return False


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)


class ToolCall(BaseModel):
    tool: str
    args: dict


class AskResponse(BaseModel):
    answer: str
    tools_called: list[ToolCall]
    model: str
    cached: bool
    note: str = "All data is SYNTHETIC demo data. Suggestions are for human review."


@lru_cache(maxsize=1)
def _build_overview() -> dict:
    """Every facility x commodity status in one payload. No LLM involved, so it is free and fast."""
    fac, stock, assess = _data()
    hist = {k: g.sort_values("month").tail(6) for k, g in stock.groupby(["facility_id", "commodity"])}
    by_fac = {fid: g for fid, g in assess.groupby("facility_id")}
    rows, counts = [], {c: {"STOCKOUT_RISK": 0, "WATCH": 0, "OK": 0, "SURPLUS": 0} for c in COMMODITIES}
    for _, f in fac.iterrows():
        cells = {}
        for _, r in by_fac.get(f.facility_id, assess.iloc[0:0]).iterrows():
            h = hist[(f.facility_id, r.commodity)]
            cells[r.commodity] = {
                "status": r.status, "months": r.months_of_stock, "weeks": r.weeks_of_stock,
                "stock": r.stock_on_hand, "avg_use": r.avg_monthly_consumption, "explanation": r.explanation,
                "history": [{"month": m, "stock": st, "consumed": c} for m, st, c in
                            zip(h.month, h.stock_on_hand, h.consumed)],
            }
            counts[r.commodity][r.status] += 1
        rows.append({"id": f.facility_id, "name": f["name"], "district": f.district, "level": f.level, "cells": cells})
    return _clean({
        "as_of": assess.as_of.max(),
        "commodities": [{"code": k, "label": v["label"], "unit": v["unit"]} for k, v in COMMODITIES.items()],
        "counts": counts,
        "facilities": rows,
    })


@app.get("/overview")
def overview():
    return _build_overview()


@app.get("/health")
def health():
    return {"status": "ok", "api_key_configured": bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))}


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(body: AskRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    result = llm.ask(body.question.strip())
    if result["error"]:
        print("LLM error:", result["error"])  # full detail stays in server logs
        raise HTTPException(status_code=502, detail="The assistant is temporarily unavailable. Please try again.")
    return AskResponse(
        answer=result["answer"],
        tools_called=[ToolCall(tool=t["tool"], args=t["args"]) for t in result["tool_calls"]],
        model=result["model"],
        cached=bool(result.get("cached")),
    )
