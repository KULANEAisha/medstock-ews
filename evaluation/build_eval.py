"""Build the evaluation set. Ground truth is computed straight from the CSVs with plain pandas
(NOT by calling the assistant's tools), so the evaluation can catch tool bugs as well as LLM mistakes.

Run:  python -m evaluation.build_eval
"""
import json
import random
from pathlib import Path

import pandas as pd

from medstock.redistribution import haversine_km

ROOT = Path(__file__).resolve().parent.parent
NAMES = {"amoxicillin_dt": "amoxicillin", "al_6x4": "artemether-lumefantrine (malaria treatment)",
         "ors_zinc": "ORS and zinc", "paracetamol": "paracetamol"}
STATUS_WORDS = {
    "STOCKOUT_RISK": (["stockout", "stock-out", "risk", "critical", "low"], ["surplus", "overstock"]),
    "SURPLUS": (["surplus", "overstock", "overstocked", "excess"], ["stockout_risk"]),
    "OK": (["ok", "adequate", "sufficient", "healthy", "fine"], ["stockout_risk", "surplus", "watch"]),
}


def truth_table(stock, fac):
    rows = []
    for (f, c), g in stock.sort_values("month").groupby(["facility_id", "commodity"]):
        stk = int(g.iloc[-1].stock_on_hand)
        avg = g.consumed.tail(3).mean()
        mos = stk / avg if avg > 0 else float("inf")
        status = "STOCKOUT_RISK" if mos < 1 else "WATCH" if mos < 2 else "SURPLUS" if mos > 6 else "OK"
        rows.append({"facility_id": f, "commodity": c, "stock": stk, "avg": avg, "mos": mos, "status": status})
    t = pd.DataFrame(rows).merge(fac, on="facility_id")
    return t


def build():
    fac = pd.read_csv(ROOT / "data" / "facilities.csv")
    stock = pd.read_csv(ROOT / "data" / "stock_monthly.csv")
    t = truth_table(stock, fac)
    rng = random.Random(7)
    qs = []

    def add(category, text, **kw):
        qs.append({"id": f"Q{len(qs) + 1:02d}", "category": category, "question": text, **kw})

    coms = list(NAMES)
    # A: at-risk lists by district (3 strict "under 1 month", 1 "within 8 weeks" incl. WATCH)
    used = 0
    for c in coms:
        for d in sorted(t.district.unique()):
            ids = sorted(t[(t.commodity == c) & (t.district == d) & (t.status == "STOCKOUT_RISK")].facility_id)
            if ids and used < 3:
                add("at_risk_list", f"Which facilities in {d} are at high risk of stocking out of {NAMES[c]} "
                    f"(less than 1 month of stock)?", kind="set", expected=ids)
                used += 1
                break
    for c in reversed(coms):
        for d in sorted(t.district.unique()):
            ids = sorted(t[(t.commodity == c) & (t.district == d) & t.status.isin(["STOCKOUT_RISK", "WATCH"])].facility_id)
            if len(ids) >= 2:
                add("at_risk_8wk", f"Which facilities in {d} could run out of {NAMES[c]} within the next 8 weeks?",
                    kind="set", expected=ids)
                break
        else:
            continue
        break
    # B: months-of-stock values
    finite = t[t.mos.apply(lambda x: x != float("inf")) & (t.mos > 0.2)]
    for _, r in finite.sample(4, random_state=3).iterrows():
        add("value", f"How many months of {NAMES[r.commodity]} does {r.facility_id} have left?",
            kind="number", expected=round(float(r.mos), 2), tol=0.1)
    # C: status
    for s in ["STOCKOUT_RISK", "SURPLUS", "OK"]:
        r = t[t.status == s].sample(1, random_state=5).iloc[0]
        acc, rej = STATUS_WORDS[s]
        add("status", f"What is the stock status of {NAMES[r.commodity]} at {r.facility_id}?",
            kind="status", accept=acc, reject=rej, expected_status=s)
    # D: surplus lists
    n = 0
    for c in coms:
        ids = sorted(t[(t.commodity == c) & (t.status == "SURPLUS")].facility_id)
        if ids and n < 2:
            add("surplus_list", f"Which facilities have surplus stock (more than 6 months) of {NAMES[c]}?",
                kind="set", expected=ids)
            n += 1
    # E: nearest donor for an at-risk facility
    n = 0
    for c in coms:
        risk = t[(t.commodity == c) & (t.status == "STOCKOUT_RISK")].sort_values("mos")
        don = t[(t.commodity == c) & (t.status == "SURPLUS")]
        for _, r in risk.iterrows():
            ds = {d.facility_id: haversine_km(r.lat, r.lon, d.lat, d.lon) for _, d in don.iterrows()}
            ds = {k: v for k, v in ds.items() if v <= 60}
            if ds and n < 2:
                near = min(ds, key=ds.get)
                add("redistribution", f"{r.facility_id} is about to run out of {NAMES[c]}. Which nearby facility "
                    f"(within 60 km) has surplus and could supply it?", kind="contains_id", expected=near)
                n += 1
                break
    # F: counts
    n = 0
    for c in coms:
        k = int((t[(t.commodity == c)].status == "STOCKOUT_RISK").sum())
        if k >= 2 and n < 2:
            add("count", f"How many facilities across all districts are at high risk of stocking out of {NAMES[c]}?",
                kind="number", expected=k, tol=0)
            n += 1
    # G: missing data
    have = set(zip(stock.facility_id, stock.commodity))
    gaps = [(f, c) for f in fac.facility_id for c in coms if (f, c) not in have]
    f, c = gaps[0]
    add("missing", f"What is the stock level of {NAMES[c]} at {f}?", kind="missing")
    add("missing", "What is the stock level of amoxicillin at F99?", kind="missing")
    add("missing", "How much insulin does F03 have in stock?", kind="missing")
    return qs


if __name__ == "__main__":
    qs = build()
    out = Path(__file__).resolve().parent / "questions.json"
    out.write_text(json.dumps(qs, indent=2), encoding="utf-8")
    print(f"Wrote {len(qs)} questions to {out}")
    for q in qs:
        print(q["id"], q["category"], "|", q["question"])
