"""plan_search: the clarify-then-optimize step.

Stateless and two-phase, so any agent/client gets the same scaffold:
  1) given a question with no answers -> clarifying questions that actually
     change the search (study type, population, recency, evidence bar, breadth).
  2) given the question + answers -> an optimized search plan: query variants,
     filters, a confidence threshold, and a target candidate count for the
     agent to execute with verify_claim / score_answer.

No LLM call — deterministic. The agent presents the questions, collects
answers, and calls back; the plan then drives a broad gather that the
min_confidence threshold prunes.
"""
import re
from datetime import date

_STOP = set((
    "a an the of to from in on for and or with without how does do is are be "
    "what which who whom whose why when where into onto over under about as at "
    "by it its this that these those can could would should may might will "
    "impact affect effect probability likelihood using use between among per"
).split())

CLARIFIERS = [
    {"id": "study_type",
     "question": "Which study types should count as evidence?",
     "options": ["RCTs / clinical trials only",
                 "Include observational & cohort studies",
                 "Include preclinical / animal studies too",
                 "Any design"]},
    {"id": "population",
     "question": "Focus on a specific population, disease, or setting? (free text, or 'general')",
     "options": ["General (no restriction)"], "free_text": True},
    {"id": "recency",
     "question": "How recent must the evidence be?",
     "options": ["Last 5 years", "Last 10 years", "Any time"]},
    {"id": "min_confidence",
     "question": "Minimum confidence to include a source?",
     "options": ["0.50 (lenient)", "0.70 (balanced)", "0.85 (strict)"]},
    {"id": "breadth",
     "question": "How many candidate sources should I gather before filtering?",
     "options": ["~8 (fast)", "~15 (balanced)", "~25 (exhaustive)"]},
]


def _key_terms(question: str):
    words = re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", (question or "").lower())
    seen, out = set(), []
    for w in words:
        if w in _STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def _num(s, default):
    m = re.search(r"\d+(?:\.\d+)?", str(s or ""))
    return type(default)(m.group(0)) if m else default


def _since_year(recency: str):
    y = date.today().year
    r = (recency or "").lower()
    if "5" in r:
        return y - 5
    if "10" in r:
        return y - 10
    return None


def clarify(question: str) -> dict:
    return {
        "mode": "clarify",
        "question": question,
        "key_terms": _key_terms(question),
        "clarifying_questions": CLARIFIERS,
        "next": ("Present these to the user, then call plan_search again with "
                 "`answers` keyed by each id (e.g. {\"study_type\": \"...\", "
                 "\"min_confidence\": \"0.70\"}) to get the optimized plan."),
        "card": _clarify_card(question),
    }


def plan(question: str, answers: dict) -> dict:
    answers = answers or {}
    terms = _key_terms(question)
    core = " ".join(terms[:6])

    study = answers.get("study_type", "") or "any"
    population = answers.get("population", "") or ""
    if population.lower() in ("general", "general (no restriction)", "no", "none", ""):
        population = ""
    min_conf = _num(answers.get("min_confidence"), 0.7)
    breadth = _num(answers.get("breadth"), 15)
    since_year = _since_year(answers.get("recency", ""))

    base = (core + (" " + population if population else "")).strip()
    design_term = ("randomized controlled trial"
                   if ("rct" in study.lower() or "trial" in study.lower())
                   else "cohort OR observational"
                   if "observational" in study.lower() or "cohort" in study.lower()
                   else "")
    variants = [base, f"{base} predictors",
                f"{base} systematic review meta-analysis"]
    if design_term:
        variants.append(f"{base} {design_term}")
    queries = list(dict.fromkeys(q.strip() for q in variants if q.strip()))

    return {
        "mode": "plan",
        "question": question,
        "answers": answers,
        "key_terms": terms,
        "queries": queries,
        "filters": {"study_type": study,
                    "population": population or "any",
                    "since_year": since_year},
        "min_confidence": min_conf,
        "target_sources": breadth,
        "recommended_workflow": (
            f"Gather ~{breadth} candidate references using `queries` (apply the "
            f"filters), draft one claim per candidate, call verify_claim on "
            f"each, then score_answer(min_confidence={min_conf})."),
        "card": _plan_card(queries, study, population, since_year,
                           min_conf, breadth),
    }


def plan_search(question: str, answers: dict = None) -> dict:
    """Entry point: clarify when no answers, otherwise return the plan."""
    if not answers:
        return clarify(question)
    return plan(question, answers)


def _clarify_card(question: str) -> str:
    lines = [f"**Before I search** — *{question}*", "",
             "A few choices that will shape the search:"]
    for c in CLARIFIERS:
        opts = " / ".join(c["options"]) + (" / <free text>" if c.get("free_text") else "")
        lines.append(f"- **{c['question']}**  ({opts})")
    return "\n".join(lines)


def _plan_card(queries, study, population, since_year, min_conf, breadth) -> str:
    return "\n".join([
        "**Search plan**",
        f"- Gather ~{breadth} candidates, keep only confidence ≥ {min_conf}",
        f"- Study type: {study} · Population: {population or 'any'}"
        + (f" · since {since_year}" if since_year else ""),
        "- Queries:",
        *[f"    {i+1}. {q}" for i, q in enumerate(queries)],
    ])
