"""Aggregate per-claim verdicts into one confidence score and the ranked
"worth your read" source list."""
from .judge import DISTORTION_LABELS

_VERDICT_WEIGHT = {"SUPPORTED": 1.0, "OVERSTATED": 0.4,
                   "INSUFFICIENT": 0.0, "UNSUPPORTED": 0.0}
_VERDICT_RANK = {"SUPPORTED": 0, "OVERSTATED": 1,
                 "INSUFFICIENT": 2, "UNSUPPORTED": 3}


def score_answer(results: list) -> dict:
    """results: list of per-claim dicts from verify_claim.

    Returns overall_confidence (0-1), a letter grade, counts by verdict, and
    worth_your_read: sources that genuinely support claims, best first.
    """
    if not results:
        return {"overall_confidence": 0.0, "grade": "N/A", "counts": {},
                "worth_your_read": [], "n_claims": 0}

    counts = {}
    score_sum = 0.0
    for r in results:
        v = r.get("verdict", "INSUFFICIENT")
        counts[v] = counts.get(v, 0) + 1
        w = _VERDICT_WEIGHT.get(v, 0.0) * float(r.get("confidence", 0.0))
        score_sum += w
    overall = score_sum / len(results)

    worth = []
    for r in results:
        if r.get("verdict") not in ("SUPPORTED", "OVERSTATED"):
            continue
        if r.get("retracted"):
            continue
        res = r.get("resolved", {})
        worth.append({
            "title": res.get("title") or r.get("reference"),
            "doi": res.get("doi"),
            "verdict": r.get("verdict"),
            "confidence": r.get("confidence", 0.0),
            "has_results": r.get("has_results", False),
            "reason": _why(r),
            "_sort": (_VERDICT_RANK.get(r.get("verdict"), 9),
                      -float(r.get("confidence", 0.0)),
                      0 if r.get("has_results") else 1),
        })
    worth.sort(key=lambda x: x.pop("_sort"))

    return {
        "overall_confidence": round(overall, 2),
        "grade": _grade(overall),
        "counts": counts,
        "n_claims": len(results),
        "worth_your_read": worth,
    }


def _why(r: dict) -> str:
    v = r.get("verdict")
    src = "results-level" if r.get("has_results") else "abstract-only"
    if v == "SUPPORTED":
        return f"Directly supported at {src} with verified quotes."
    if v == "OVERSTATED":
        d = DISTORTION_LABELS.get(r.get("distortion_type"), "overstated")
        return f"Supports a weaker claim ({src}); read for context ({d})."
    return "Read with caution."


def _grade(x: float) -> str:
    if x >= 0.85:
        return "A"
    if x >= 0.7:
        return "B"
    if x >= 0.5:
        return "C"
    if x >= 0.3:
        return "D"
    return "F"
