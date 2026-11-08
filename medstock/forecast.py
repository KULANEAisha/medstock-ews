"""Explainable months-of-stock forecast and risk/surplus rules.

Method: forecast next month's consumption from recent history (moving average by default),
then months_of_stock = stock_on_hand / forecast_monthly_consumption.

Run:  python -m medstock.forecast
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

WEEKS_PER_MONTH = 52 / 12


@dataclass(frozen=True)
class Thresholds:
    risk_months: float = 1.0      # months_of_stock <  1  -> STOCKOUT_RISK
    watch_months: float = 2.0     # 1 <= months     <  2  -> WATCH (inside the 8-week window)
    surplus_months: float = 6.0   # months_of_stock >  6  -> SURPLUS


def forecast_consumption(history, method: str = "ma", window: int = 3, alpha: float = 0.5) -> float:
    """Forecast monthly consumption from past monthly values (oldest first)."""
    h = [float(x) for x in history if pd.notna(x)]
    if not h:
        return float("nan")
    if method == "ma":
        return float(np.mean(h[-window:]))
    if method == "ses":  # simple exponential smoothing, written out so it is easy to explain
        level = h[0]
        for x in h[1:]:
            level = alpha * x + (1 - alpha) * level
        return float(level)
    raise ValueError(f"unknown method: {method!r}")


def months_of_stock(stock: float, monthly_consumption: float) -> float:
    if stock is None or monthly_consumption is None or math.isnan(monthly_consumption):
        return float("nan")
    if monthly_consumption <= 0:
        return float("inf") if stock > 0 else float("nan")
    return float(stock) / monthly_consumption


def classify(mos: float, t: Thresholds = Thresholds()) -> str:
    if math.isnan(mos):
        return "UNKNOWN"
    if math.isinf(mos):
        return "NO_RECENT_DEMAND"
    if mos < t.risk_months:
        return "STOCKOUT_RISK"
    if mos < t.watch_months:
        return "WATCH"
    if mos > t.surplus_months:
        return "SURPLUS"
    return "OK"


def assess_latest(stock_df: pd.DataFrame, method: str = "ma", window: int = 3, alpha: float = 0.5,
                  thresholds: Thresholds = Thresholds()) -> pd.DataFrame:
    """One row per facility x commodity, using the latest reported month."""
    rows = []
    for (fid, com), g in stock_df.sort_values("month").groupby(["facility_id", "commodity"]):
        latest = g.iloc[-1]
        cons = forecast_consumption(g["consumed"], method, window, alpha)
        mos = months_of_stock(latest["stock_on_hand"], cons)
        status = classify(mos, thresholds)
        label = f"avg of last {window} months" if method == "ma" else f"exp. smoothed (alpha={alpha})"
        rows.append(
            {
                "facility_id": fid,
                "commodity": com,
                "as_of": latest["month"],
                "stock_on_hand": int(latest["stock_on_hand"]),
                "avg_monthly_consumption": round(cons, 1),
                "months_of_stock": round(mos, 2) if math.isfinite(mos) else mos,
                "weeks_of_stock": round(mos * WEEKS_PER_MONTH, 1) if math.isfinite(mos) else mos,
                "status": status,
                "method": method,
                "explanation": (f"Stock {int(latest['stock_on_hand'])} / consumption {cons:.0f} per month "
                                f"({label}) = {mos:.2f} months -> {status}"),
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values("months_of_stock", ignore_index=True)


def main() -> None:
    stock = pd.read_csv("data/stock_monthly.csv")
    res = assess_latest(stock)
    print("SYNTHETIC DATA\n", res.status.value_counts().to_string(), "\n")
    cols = ["facility_id", "commodity", "stock_on_hand", "avg_monthly_consumption", "months_of_stock"]
    print(res[res.status == "STOCKOUT_RISK"].head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
