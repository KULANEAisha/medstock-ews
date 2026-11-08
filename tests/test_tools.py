import json

import pandas as pd
import pytest

from medstock import tools
from evaluation.scoring import score


def _fac_stock():
    fac, stock, assess = tools._data()
    return fac, stock, assess


def test_catalog_lists_commodities_and_districts():
    c = tools.get_catalog()
    assert len(c["commodities"]) == 4 and len(c["districts"]) == 3
    assert "SYNTHETIC" in c["data_note"]


def test_resolvers():
    assert tools.resolve_commodity("Amoxicillin") == "amoxicillin_dt"
    assert tools.resolve_commodity("malaria treatment") == "al_6x4"
    assert tools.resolve_commodity("insulin") is None
    assert tools.resolve_facility("f3") == "F03" and tools.resolve_facility("F99") is None
    assert tools.resolve_district("a") == "District A" and tools.resolve_district("District Z") is None


def test_unknown_things_report_missing_data_not_guesses():
    assert tools.get_facility_stock("F99")["data_available"] is False
    assert tools.get_facility_stock("F03", "insulin")["data_available"] is False
    assert tools.get_at_risk_facilities("amoxicillin", "District Z")["data_available"] is False


def test_unstocked_pair_reports_missing():
    fac, stock, _ = _fac_stock()
    have = set(zip(stock.facility_id, stock.commodity))
    f, c = next((f, c) for f in fac.facility_id for c in tools.COMMODITIES if (f, c) not in have)
    r = tools.get_facility_stock(f, c)
    assert r["data_available"] is False and "no stock records" in r["error"]


def test_at_risk_matches_direct_pandas():
    _, _, assess = _fac_stock()
    exp = set(assess[(assess.commodity == "paracetamol") & (assess.status == "STOCKOUT_RISK")].facility_id)
    r = tools.get_at_risk_facilities("paracetamol")
    assert {f["facility_id"] for f in r["facilities"]} == exp and r["count"] == len(exp)


def test_include_watch_is_superset():
    a = tools.get_at_risk_facilities("amoxicillin")["count"]
    b = tools.get_at_risk_facilities("amoxicillin", include_watch=True)["count"]
    assert b >= a


def test_facility_stock_has_history_and_explanation():
    r = tools.get_facility_stock("F01")
    assert r["data_available"] and r["items"]
    it = r["items"][0]
    assert len(it["recent_history"]) == 6 and "->" in it["explanation"]


def test_redistribution_respects_distance_and_is_json_safe():
    for c in tools.COMMODITIES:
        r = tools.suggest_redistribution(c, max_km=60)
        json.dumps(r, allow_nan=False)  # raises on NaN/inf
        for t in r["transfers"]:
            assert t["distance_km"] <= 60 and t["quantity"] > 0


def test_all_tool_outputs_are_json_safe():
    json.dumps(tools.get_facility_stock("F05"), allow_nan=False)
    json.dumps(tools.get_at_risk_facilities("ors", "District B", True), allow_nan=False)


# ---- scoring -------------------------------------------------------------
def test_scoring_set_number_missing_status():
    assert score({"kind": "set", "expected": ["F03", "F14"]}, "At risk: F03 and F14.")[0]
    assert not score({"kind": "set", "expected": ["F03", "F14"]}, "Only F03.")[0]
    assert score({"kind": "number", "expected": 0.5, "tol": 0.1}, "About 0.52 months")[0]
    assert not score({"kind": "number", "expected": 3, "tol": 0}, "F03 has 4 facilities")[0]  # 'F03' digits ignored
    assert score({"kind": "missing"}, "F99 was not found in the dataset.")[0]
    assert not score({"kind": "missing"}, "F99 has 500 tablets.")[0]
    q = {"kind": "status", "accept": ["surplus"], "reject": ["stockout_risk"]}
    assert score(q, "It has SURPLUS stock.")[0] and not score(q, "STOCKOUT_RISK")[0]
