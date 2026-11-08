"""LLM layer: Gemini with tool calling. Answers must come from tool results only.

Setup (PowerShell):   $env:GOOGLE_API_KEY = "your-key"
Optional:             $env:GEMINI_MODEL = "a-free-model-name-from-AI-Studio"
Try it:               python -m medstock.llm "Which facilities in District A are at high risk of running out of amoxicillin?"

To swap providers later, only `_run_gemini` needs replacing; tools, prompt, cache and evaluation stay the same.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from .tools import TOOLS

DEFAULT_MODEL = "gemini-2.5-flash-lite"  # check AI Studio for a currently free model and set GEMINI_MODEL
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "llm"

SYSTEM_PROMPT = """You are a decision-support assistant for monitoring medicine stock at health facilities.
All data is SYNTHETIC demo data; say so if asked whether it is real.

Rules:
1. Answer ONLY from tool results. Never use outside knowledge or guesses for any facility, stock level,
   consumption figure, distance or status. Always call a tool before stating a facility-specific fact.
2. If a tool says data is unavailable (data_available is false, or an error), say plainly what is missing.
   Do not substitute another facility, commodity or district, and do not estimate.
3. Copy facility IDs and numbers exactly as the tool returned them.
4. Status meanings: STOCKOUT_RISK = under 1 month of stock; WATCH = 1 to 2 months; OK = 2 to 6 months;
   SURPLUS = over 6 months. Months of stock = stock on hand / average monthly consumption of the last 3 months.
5. For "within the next 8 weeks" questions, include WATCH facilities (include_watch=true) and say which are which.
6. Redistribution output is a suggestion for a person to review, not an instruction. Mention unmet need if present.
7. If a question cannot be answered with the tools (other regions, clinical advice, predictions beyond the
   forecast), say so briefly.
8. Be concise: a short direct answer first, then the supporting numbers."""


def _with_retry(fn, attempts=5):
    delay = 5
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # SDK raises various error types; decide by message
            msg = str(e)
            transient = any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "500", "503", "UNAVAILABLE", "INTERNAL"))
            if not transient or i == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("retry loop exited without a result")  # unreachable; keeps the return type non-Optional


def _run_gemini(question, system, model, max_steps):
    from google import genai
    from google.genai import types

    client = genai.Client()  # reads GOOGLE_API_KEY (or GEMINI_API_KEY) from the environment
    cfg = types.GenerateContentConfig(
        system_instruction=system,  # pyright: ignore[reportCallIssue]
        tools=list(TOOLS.values()),  # pyright: ignore[reportCallIssue]
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # pyright: ignore[reportCallIssue]  we run tools ourselves
        temperature=0,  # pyright: ignore[reportCallIssue]
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
    trace = []
    for _ in range(max_steps):
        resp = _with_retry(lambda: client.models.generate_content(model=model, contents=contents, config=cfg))
        calls = resp.function_calls or []
        if not calls:
            return (resp.text or "").strip(), trace
        if not resp.candidates or resp.candidates[0].content is None:
            return "(Stopped: the model returned no content.)", trace
        contents.append(resp.candidates[0].content)  # keep the model's turn exactly as returned
        parts = []
        for c in calls:
            name = c.name or ""
            args = dict(c.args or {})
            fn = TOOLS.get(name)
            try:
                result = fn(**args) if fn else {"data_available": False, "error": f"unknown tool {name}"}
            except Exception as e:  # bad arguments from the model are fed back, not crashed on
                result = {"data_available": False, "error": f"tool call failed: {e}"}
            trace.append({"tool": name, "args": args, "result": result})
            parts.append(types.Part.from_function_response(name=name, response={"result": result}))
        contents.append(types.Content(role="user", parts=parts))
    return "(Stopped: too many tool steps without a final answer.)", trace


def ask(question, model=None, use_cache=True, max_steps=6):
    """Return {question, answer, tool_calls, model, error}. Errors are returned, never cached."""
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    key = hashlib.sha256(f"{model}|{SYSTEM_PROMPT}|{question}".encode()).hexdigest()[:24]
    path = CACHE_DIR / f"{key}.json"
    if use_cache and path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "cached": True}
    try:
        answer, trace = _run_gemini(question, SYSTEM_PROMPT, model, max_steps)
    except Exception as e:
        return {"question": question, "answer": "", "tool_calls": [], "model": model, "error": f"{type(e).__name__}: {e}"}
    out = {"question": question, "answer": answer, "tool_calls": trace, "model": model, "error": None}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return {**out, "cached": False}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Which facilities in District A are at high risk of running out of amoxicillin?"
    r = ask(q)
    if r["error"]:
        sys.exit(f"ERROR: {r['error']}")
    print("Q:", q, "\n")
    for t in r["tool_calls"]:
        print(f"  tool: {t['tool']}({t['args']})")
    print("\nA:", r["answer"])