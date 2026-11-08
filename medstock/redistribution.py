"""Simple, explainable redistribution: move surplus stock to nearby at-risk facilities.

Suggestions are for human review, not orders.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def suggest_transfers(assessment: pd.DataFrame, facilities: pd.DataFrame, commodity: str,
                      max_km: float = 60.0, keep_months: float = 3.0, target_months: float = 3.0,
                      recipient_statuses: tuple[str, ...] = ("STOCKOUT_RISK",)):
    """Greedy nearest-donor allocation. Returns (transfers, unmet_need) DataFrames.

    Donors (SURPLUS) keep at least `keep_months` of stock. Recipients are topped up
    towards `target_months` of stock.
    """
    a = assessment[assessment.commodity == commodity].merge(
        facilities[["facility_id", "lat", "lon"]], on="facility_id")
    donors = a[a.status == "SURPLUS"].copy()
    donors["available"] = np.floor(
        donors.stock_on_hand - keep_months * donors.avg_monthly_consumption).clip(lower=0)
    donors = donors.set_index("facility_id")
    transfers, unmet = [], []
    for _, r in a[a.status.isin(recipient_statuses)].sort_values("months_of_stock").iterrows():
        need = int(math.floor(target_months * r.avg_monthly_consumption - r.stock_on_hand))
        if need <= 0:
            continue
        dist = donors.apply(lambda d: haversine_km(r.lat, r.lon, d.lat, d.lon), axis=1) \
            if len(donors) else pd.Series(dtype=float)
        for did in dist[dist <= max_km].sort_values().index:
            if need <= 0:
                break
            qty = int(min(need, donors.at[did, "available"]))
            if qty <= 0:
                continue
            donors.at[did, "available"] -= qty
            need -= qty
            transfers.append({
                "commodity": commodity, "from_facility": did, "to_facility": r.facility_id,
                "quantity": qty, "distance_km": round(float(dist[did]), 1),
                "recipient_months_before": r.months_of_stock,
            })
        if need > 0:
            unmet.append({"commodity": commodity, "facility_id": r.facility_id, "unmet_quantity": need})
    return pd.DataFrame(transfers), pd.DataFrame(unmet)
