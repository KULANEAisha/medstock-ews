"""Automatic scoring of assistant answers against ground truth computed from the data."""
import re

MISSING_PHRASES = ["no data", "not found", "no record", "no stock record", "not available", "unavailable",
                   "not in the dataset", "doesn't", "does not", "cannot", "can't", "unable", "not stock",
                   "no information", "unknown", "isn't", "is not", "don't have", "do not have", "missing"]


def extract_ids(text):
    return set(re.findall(r"\bF\d{2}\b", text.upper()))


def extract_numbers(text):
    return [float(x) for x in re.findall(r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?", text.replace(",", ""))]


def _has_word(text, words):
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def score(q, answer):
    """Return (passed, reason). `q` is a question dict from build_eval."""
    a = answer or ""
    low = a.lower()
    kind = q["kind"]
    if not a.strip():
        return False, "empty answer"
    if kind == "set":
        got, exp = extract_ids(a), set(q["expected"])
        return got == exp, f"expected {sorted(exp)}, answer mentioned {sorted(got)}"
    if kind == "contains_id":
        got = extract_ids(a)
        return q["expected"] in got, f"expected {q['expected']}, answer mentioned {sorted(got)}"
    if kind == "number":
        nums = extract_numbers(a)
        ok = any(abs(n - q["expected"]) <= q.get("tol", 0) for n in nums)
        return ok, f"expected {q['expected']} (+/-{q.get('tol', 0)}), answer numbers {nums[:8]}"
    if kind == "status":
        norm = low.replace("_", " ")  # STOCKOUT_RISK -> "stockout risk" so \b word matching works
        good = _has_word(norm, [w.replace("_", " ") for w in q["accept"]])
        bad = _has_word(norm, [w.replace("_", " ") for w in q["reject"]])
        return good and not bad, f"expected one of {q['accept']} and none of {q['reject']}"
    if kind == "missing":
        ok = any(p in low for p in MISSING_PHRASES)
        return ok, "expected the answer to say the data is missing"
    raise ValueError(f"unknown kind {kind}")