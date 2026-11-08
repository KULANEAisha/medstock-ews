"""Synthetic stock data generator.

ALL DATA PRODUCED HERE IS SYNTHETIC. It is not real facility data and must never be
presented as such. Facility names, districts and coordinates are invented.

Run:  python -m medstock.data_gen
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_FACILITIES = 24
N_MONTHS = 24
LAST_MONTH = "2026-10-01"  # most recent reporting month in the synthetic data

COMMODITIES = {
    "amoxicillin_dt": {"label": "Amoxicillin 250mg dispersible tablets", "unit": "tablets", "base": 900},
    "al_6x4": {"label": "Artemether-lumefantrine 20/120mg (6x4)", "unit": "packs", "base": 150},
    "ors_zinc": {"label": "ORS + zinc co-pack", "unit": "kits", "base": 120},
    "paracetamol": {"label": "Paracetamol 500mg tablets", "unit": "tablets", "base": 1500},
}
# Invented district centres (roughly 100 km apart) so "nearby" is meaningful.
DISTRICT_CENTRES = {"District A": (-1.25, 36.80), "District B": (-0.40, 37.10), "District C": (-1.00, 35.90)}
LEVEL_SIZE = {"dispensary": 0.6, "health_centre": 1.0, "sub_county_hospital": 2.2}

P_SCENARIO = {"normal": 0.70, "risk": 0.15, "surplus": 0.15}
P_STOCKED = 0.93  # some facilities simply do not stock a commodity -> "data missing" cases
DISRUPTION_MONTHS = 3


def make_facilities(rng: np.random.Generator) -> pd.DataFrame:
    districts = list(DISTRICT_CENTRES)
    rows = []
    for i in range(N_FACILITIES):
        d = districts[i % len(districts)]
        lat0, lon0 = DISTRICT_CENTRES[d]
        rows.append(
            {
                "facility_id": f"F{i + 1:02d}",
                "name": f"Synthetic Facility {i + 1:02d}",
                "district": d,
                "level": str(rng.choice(list(LEVEL_SIZE), p=[0.5, 0.4, 0.1])),
                "lat": round(lat0 + rng.normal(0, 0.12), 4),
                "lon": round(lon0 + rng.normal(0, 0.12), 4),
            }
        )
    return pd.DataFrame(rows)


def simulate_series(rng: np.random.Generator, base: float, months: pd.DatetimeIndex, scenario: str) -> list[dict]:
    n = len(months)
    phase = rng.uniform(0, 2 * np.pi)
    cycle = int(rng.choice([1, 2, 3]))  # resupply every 1-3 months
    offset = int(rng.integers(0, cycle))
    order_up_to = (cycle + rng.uniform(2.0, 3.0)) * base
    stock = int(rng.uniform(1.5, 3.0) * base)
    out = []
    for t, month in enumerate(months):
        demand = base * (1 + 0.2 * np.sin(2 * np.pi * t / 12 + phase)) * rng.lognormal(0, 0.15)
        if scenario == "surplus" and t >= n - 3:
            demand *= 0.6  # demand drops after an over-delivery
        if scenario == "risk" and t >= n - DISRUPTION_MONTHS:
            demand *= 1.15
        resupply = t % cycle == offset
        if scenario == "risk" and t >= n - DISRUPTION_MONTHS:
            resupply = False  # supply disruption
        received = max(0.0, order_up_to - stock) if resupply else 0.0
        if scenario == "surplus" and t == n - 3:
            received += rng.uniform(5, 8) * base  # large over-delivery
        received = int(round(received))
        consumed = int(min(round(demand), stock + received))  # cannot dispense what is not there
        stock = stock + received - consumed
        out.append(
            {"month": month.strftime("%Y-%m-%d"), "received": received, "consumed": consumed, "stock_on_hand": stock}
        )
    return out


def generate(seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (facilities, stock_monthly, planted_scenarios)."""
    rng = np.random.default_rng(seed)
    facilities = make_facilities(rng)
    months = pd.date_range(end=LAST_MONTH, periods=N_MONTHS, freq="MS")
    stock_rows, planted = [], []
    for _, fac in facilities.iterrows():
        size = LEVEL_SIZE[fac["level"]]
        for code, meta in COMMODITIES.items():
            if rng.random() > P_STOCKED:
                continue
            scenario = str(rng.choice(list(P_SCENARIO), p=list(P_SCENARIO.values())))
            base = meta["base"] * size * rng.uniform(0.7, 1.3)
            for row in simulate_series(rng, base, months, scenario):
                stock_rows.append({"facility_id": fac["facility_id"], "commodity": code, **row})
            planted.append({"facility_id": fac["facility_id"], "commodity": code, "planted_scenario": scenario})
    cols = ["month", "facility_id", "commodity", "received", "consumed", "stock_on_hand"]
    return facilities, pd.DataFrame(stock_rows)[cols], pd.DataFrame(planted)


def main(out_dir: str = "data") -> None:
    facilities, stock, planted = generate()
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    facilities.to_csv(out / "facilities.csv", index=False)
    stock.to_csv(out / "stock_monthly.csv", index=False)
    # Debug-only: the scenarios the generator planted. Evaluation answers must be computed
    # from stock_monthly.csv by the forecast code, not read from this file.
    planted.to_csv(out / "planted_scenarios.csv", index=False)
    print(f"SYNTHETIC data written to {out}/: {len(facilities)} facilities, "
          f"{stock.commodity.nunique()} commodities, {len(stock)} stock rows")


if __name__ == "__main__":
    main()
