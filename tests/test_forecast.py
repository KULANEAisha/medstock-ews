import math

import pandas as pd
import pytest

from medstock.data_gen import generate
from medstock.forecast import (Thresholds, assess_latest, classify, forecast_consumption,
                               months_of_stock)
from medstock.redistribution import haversine_km, suggest_transfers


# ---- forecast primitives -------------------------------------------------
def test_moving_average_uses_last_window_only():
    assert forecast_consumption([100, 100, 10, 20, 30], "ma", window=3) == 20


def test_moving_average_short_history():
    assert forecast_consumption([40, 60], "ma", window=3) == 50


def test_ses_known_value():
    # level: 10 -> 0.5*20+0.5*10=15 -> 0.5*30+0.5*15=22.5
    assert forecast_consumption([10, 20, 30], "ses", alpha=0.5) == pytest.approx(22.5)


def test_empty_history_is_nan_and_bad_method_raises():
    assert math.isnan(forecast_consumption([]))
    with pytest.raises(ValueError):
        forecast_consumption([1, 2], "magic")


def test_months_of_stock_basic_and_zero_demand():
    assert months_of_stock(300, 100) == 3
    assert months_of_stock(50, 0) == math.inf
    assert math.isnan(months_of_stock(0, 0))


# ---- rules ---------------------------------------------------------------
@pytest.mark.parametrize("mos,expected", [
    (0.0, "STOCKOUT_RISK"), (0.99, "STOCKOUT_RISK"),
    (1.0, "WATCH"), (1.99, "WATCH"),
    (2.0, "OK"), (6.0, "OK"),
    (6.01, "SURPLUS"),
    (math.inf, "NO_RECENT_DEMAND"), (math.nan, "UNKNOWN"),
])
def test_classify_boundaries(mos, expected):
    assert classify(mos) == expected


def test_custom_thresholds():
    assert classify(2.5, Thresholds(risk_months=3)) == "STOCKOUT_RISK"


def _frame(rows):
    return pd.DataFrame(rows, columns=["month", "facility_id", "commodity", "consumed", "stock_on_hand"])


def test_assess_latest_hand_computed():
    df = _frame([
        ("2026-08-01", "F1", "x", 100, 500),
        ("2026-09-01", "F1", "x", 100, 400),
        ("2026-10-01", "F1", "x", 100, 50),    # 50 / 100 = 0.5 months -> risk
        ("2026-10-01", "F2", "x", 10, 100),    # 100 / 10 = 10 months -> surplus
    ])
    res = assess_latest(df).set_index("facility_id")
    assert res.loc["F1", "months_of_stock"] == 0.5
    assert res.loc["F1", "status"] == "STOCKOUT_RISK"
    assert res.loc["F2", "status"] == "SURPLUS"
    assert res.loc["F1", "weeks_of_stock"] == pytest.approx(0.5 * 52 / 12, abs=0.05)


def test_assess_latest_uses_latest_month_even_if_unsorted():
    df = _frame([("2026-10-01", "F1", "x", 100, 900), ("2026-08-01", "F1", "x", 100, 10)])
    assert assess_latest(df).iloc[0].stock_on_hand == 900


# ---- synthetic data ------------------------------------------------------
def test_generation_is_reproducible():
    a = generate(1)[1]
    b = generate(1)[1]
    pd.testing.assert_frame_equal(a, b)


def test_stock_is_never_negative_and_balances():
    _, stock, _ = generate()
    assert (stock.stock_on_hand >= 0).all()
    for _, g in stock.groupby(["facility_id", "commodity"]):
        g = g.sort_values("month")
        expected = g.stock_on_hand.shift(1) + g.received - g.consumed
        assert (expected.iloc[1:] == g.stock_on_hand.iloc[1:]).all()


def test_planted_scenarios_are_detected():
    """Sanity check on the generator + rules together (not on real-world accuracy)."""
    _, stock, planted = generate()
    res = assess_latest(stock).merge(planted, on=["facility_id", "commodity"])
    risk = res[res.planted_scenario == "risk"]
    surplus = res[res.planted_scenario == "surplus"]
    assert len(risk) and len(surplus)
    assert risk.status.isin(["STOCKOUT_RISK", "WATCH"]).mean() >= 0.9
    assert (surplus.status == "SURPLUS").mean() >= 0.7


# ---- redistribution ------------------------------------------------------
def _redis_fixture():
    fac = pd.DataFrame([
        {"facility_id": "R", "lat": 0.0, "lon": 0.0},
        {"facility_id": "NEAR", "lat": 0.0, "lon": 0.1},   # ~11 km
        {"facility_id": "FAR", "lat": 0.0, "lon": 2.0},    # ~222 km
    ])
    a = pd.DataFrame([
        dict(facility_id="R", commodity="x", stock_on_hand=20, avg_monthly_consumption=100, months_of_stock=0.2, status="STOCKOUT_RISK"),
        dict(facility_id="NEAR", commodity="x", stock_on_hand=1000, avg_monthly_consumption=100, months_of_stock=10, status="SURPLUS"),
        dict(facility_id="FAR", commodity="x", stock_on_hand=5000, avg_monthly_consumption=100, months_of_stock=50, status="SURPLUS"),
    ])
    return a, fac


def test_haversine_known_distance():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.2, abs=0.5)


def test_transfer_respects_distance_and_donor_floor():
    a, fac = _redis_fixture()
    t, unmet = suggest_transfers(a, fac, "x", max_km=60, keep_months=3, target_months=3)
    assert list(t.from_facility) == ["NEAR"]          # FAR is out of range
    assert t.quantity.iloc[0] == 280                  # need = 3*100-20
    assert 1000 - t.quantity.sum() >= 3 * 100         # donor keeps 3 months
    assert unmet.empty


def test_unmet_need_reported_when_no_donor_in_range():
    a, fac = _redis_fixture()
    t, unmet = suggest_transfers(a, fac, "x", max_km=5)
    assert t.empty and unmet.iloc[0].unmet_quantity == 280
