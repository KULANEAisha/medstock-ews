"""Tool functions the LLM can call. Every number the assistant states must come from these.

Notes:
- No `from __future__ import annotations` here on purpose: the Gemini SDK builds tool
  schemas from these signatures and docstrings, so keep plain type hints.
- All data is SYNTHETIC.
"""
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .data_gen import COMMODITIES
from .forecast import assess_latest
from .redistribution import suggest_transfers

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_ALIASES = {
    "amoxicillin_dt": ["amoxicillin", "amoxil"],
    "al_6x4": ["artemether", "lumefantrine", "coartem", "malaria"],
    "ors_zinc": ["ors", "zinc", "oral rehydration"],
    "paracetamol": ["paracetamol", "acetaminophen"],
}


@lru_cache(maxsize=1)
def _data():
    fac = pd.read_csv(DATA_DIR / "facilities.csv")
    stock = pd.read_csv(DATA_DIR / "stock_monthly.csv")
    return fac, stock, assess_latest(stock)


def _clean(x) -> Any:
    """Make results JSON-safe: numpy -> python, NaN/inf -> None."""
    if isinstance(x, pd.DataFrame):
        return _clean(x.to_dict("records"))
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def resolve_commodity(text):
    t = str(text).strip().lower()
    if t in COMMODITIES:
        return t
    for code, names in _ALIASES.items():
        if any(n in t for n in names) or t == code.lower():
            return code
    return None


def resolve_district(text):
    t = str(text).strip().lower().replace("district", "").strip()
    for d in _data()[0].district.unique():
        if d.lower().replace("district", "").strip() == t:
            return d
    return None


def resolve_facility(text):
    m = re.fullmatch(r"F?\s*0*(\d+)", str(text).strip().upper())
    if not m:
        return None
    fid = f"F{int(m.group(1)):02d}"
    return fid if fid in set(_data()[0].facility_id) else None


def _err(msg, **extra):
    return _clean({"data_available": False, "error": msg, **extra})


def _unknown_commodity(text):
    return _err(f"Unknown commodity '{text}'.", known_commodities={k: v["label"] for k, v in COMMODITIES.items()})


_COLS = ["facility_id", "name", "district", "commodity", "as_of", "stock_on_hand",
         "avg_monthly_consumption", "months_of_stock", "weeks_of_stock", "status", "explanation"]


def get_catalog() -> dict:
    """List the commodities, districts and facility count in the dataset, plus the status definitions.
    Call this first if you are unsure which commodity code or district name matches the user's wording."""
    fac, stock, _ = _data()
    return _clean({
        "data_note": "SYNTHETIC demo data, not real facility data.",
        "commodities": [{"code": k, "label": v["label"], "unit": v["unit"]} for k, v in COMMODITIES.items()],
        "districts": sorted(fac.district.unique()),
        "n_facilities": len(fac),
        "latest_month": stock.month.max(),
        "status_definitions": {
            "STOCKOUT_RISK": "less than 1 month of stock at forecast consumption",
            "WATCH": "1 to 2 months of stock",
            "OK": "2 to 6 months of stock",
            "SURPLUS": "more than 6 months of stock",
        },
        "forecast_method": "stock on hand divided by the average monthly consumption of the last 3 months",
    })


def get_facility_stock(facility_id: str, commodity: str = "") -> dict:
    """Get the latest stock position, months of stock remaining, status and 6-month history for one facility.

    Args:
        facility_id: Facility ID such as 'F03'.
        commodity: Commodity name or code (e.g. 'amoxicillin'). Leave empty for all commodities at the facility.
    """
    fac, stock, assess = _data()
    fid = resolve_facility(facility_id)
    if fid is None:
        return _err(f"Facility '{facility_id}' not found in the dataset.")
    info = fac[fac.facility_id == fid].iloc[0]
    a = assess[assess.facility_id == fid].merge(fac[["facility_id", "name", "district"]], on="facility_id")
    if commodity.strip():
        code = resolve_commodity(commodity)
        if code is None:
            return _unknown_commodity(commodity)
        a = a[a.commodity == code]
        if a.empty:
            return _err(f"Facility {fid} has no stock records for {code}; it may not stock this commodity.",
                        facility_id=fid, commodity=code)
    items = []
    for _, r in a.iterrows():
        hist = stock[(stock.facility_id == fid) & (stock.commodity == r.commodity)].sort_values("month").tail(6)
        items.append({**{c: r[c] for c in _COLS},
                      "recent_history": hist[["month", "received", "consumed", "stock_on_hand"]].to_dict("records")})
    return _clean({"data_available": True, "facility": {"facility_id": fid, "name": info["name"], "district": info.district},
                   "items": items})


def get_at_risk_facilities(commodity: str, district: str = "", include_watch: bool = False, limit: int = 30) -> dict:
    """List facilities at risk of stocking out of a commodity, most urgent first.

    Args:
        commodity: Commodity name or code (e.g. 'amoxicillin').
        district: Optional district name such as 'District A'. Empty means all districts.
        include_watch: If true, also include WATCH facilities (1 to 2 months of stock, i.e. within about 8 weeks).
            Default false returns only STOCKOUT_RISK (under 1 month).
        limit: Maximum facilities to return.
    """
    code = resolve_commodity(commodity)
    if code is None:
        return _unknown_commodity(commodity)
    fac, _, assess = _data()
    d = None
    if str(district).strip():
        d = resolve_district(district)
        if d is None:
            return _err(f"Unknown district '{district}'.", known_districts=sorted(fac.district.unique()))
    a = assess[assess.commodity == code].merge(fac[["facility_id", "name", "district"]], on="facility_id")
    if d:
        a = a[a.district == d]
    statuses = ["STOCKOUT_RISK"] + (["WATCH"] if include_watch else [])
    hit = a[a.status.isin(statuses)].sort_values("months_of_stock")
    return _clean({"data_available": True, "commodity": code, "district": d or "all districts",
                   "statuses_included": statuses, "facilities_checked": len(a), "count": len(hit),
                   "facilities": hit.head(int(limit))[_COLS]})


def get_facilities_by_status(commodity: str, status: str, district: str = "", limit: int = 30) -> dict:
    """List ALL facilities with a given status for a commodity (e.g. every SURPLUS facility).
    Use this for 'which facilities have surplus / are OK / are on watch' questions.

    Args:
        commodity: Commodity name or code (e.g. 'amoxicillin').
        status: One of STOCKOUT_RISK, WATCH, OK, SURPLUS.
        district: Optional district name such as 'District A'. Empty means all districts.
        limit: Maximum facilities to return.
    """
    code = resolve_commodity(commodity)
    if code is None:
        return _unknown_commodity(commodity)
    st = str(status).strip().upper().replace(" ", "_")
    if st not in ("STOCKOUT_RISK", "WATCH", "OK", "SURPLUS"):
        return _err(f"Unknown status '{status}'.", known_statuses=["STOCKOUT_RISK", "WATCH", "OK", "SURPLUS"])
    fac, _, assess = _data()
    d = None
    if str(district).strip():
        d = resolve_district(district)
        if d is None:
            return _err(f"Unknown district '{district}'.", known_districts=sorted(fac.district.unique()))
    a = assess[assess.commodity == code].merge(fac[["facility_id", "name", "district"]], on="facility_id")
    if d:
        a = a[a.district == d]
    hit = a[a.status == st].sort_values("months_of_stock", ascending=(st != "SURPLUS"))
    return _clean({"data_available": True, "commodity": code, "district": d or "all districts", "status": st,
                   "facilities_checked": len(a), "count": len(hit), "facilities": hit.head(int(limit))[_COLS]})


def suggest_redistribution(commodity: str, district: str = "", max_km: float = 60.0) -> dict:
    """Suggest moving surplus stock from nearby SURPLUS facilities to STOCKOUT_RISK facilities.
    These are suggestions for human review, not orders.

    Args:
        commodity: Commodity name or code.
        district: Optional district; only recipients in this district are considered. Donors may be in any district.
        max_km: Maximum straight-line distance between donor and recipient in km.
    """
    code = resolve_commodity(commodity)
    if code is None:
        return _unknown_commodity(commodity)
    fac, _, assess = _data()
    d = None
    if str(district).strip():
        d = resolve_district(district)
        if d is None:
            return _err(f"Unknown district '{district}'.", known_districts=sorted(fac.district.unique()))
    t, unmet = suggest_transfers(assess, fac, code, max_km=float(max_km))
    dmap = dict(zip(fac.facility_id, fac.district))
    if len(t):
        t = t.assign(from_district=t.from_facility.map(dmap), to_district=t.to_facility.map(dmap))
        if d:
            t = t[t.to_district == d]
    if len(unmet) and d:
        unmet = unmet[unmet.facility_id.map(dmap) == d]
    return _clean({"data_available": True, "commodity": code, "district": d or "all districts",
                   "transfers": t, "unmet_need": unmet,
                   "assumptions": (f"Donors have more than 6 months of stock and keep 3 months. Recipients have under "
                                   f"1 month and are topped up to 3 months. Max distance {float(max_km):g} km, "
                                   "straight line. Suggestions only; a person must review them."),
                   })


TOOLS = {f.__name__: f for f in (get_catalog, get_facility_stock, get_at_risk_facilities, get_facilities_by_status,
                                      suggest_redistribution)}