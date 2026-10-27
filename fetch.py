"""Fetch the publication's actual text, section by section.

Primary source: PMC BioC JSON — passages pre-tagged by section_type, no key,
no XML parsing. Fallbacks: Europe PMC abstract, then the Crossref abstract.
We always report which sections we actually obtained so the judge (and the
reader) never mistake an abstract-only check for a results-level one.
"""
import re
import requests

from . import config

BIOC = ("https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/"
        "pmcoa.cgi/BioC_json/{pmcid}/unicode")
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

# BioC section_type -> our normalized bucket.
_SECTION_MAP = {
    "TITLE": "title", "ABSTRACT": "abstract", "INTRO": "introduction",
    "METHODS": "methods", "RESULTS": "results", "DISCUSS": "discussion",
    "CONCL": "conclusion", "CASE": "results", "SUPPL": "supplement",
}
# Order we feed sections to the judge: evidence-bearing first.
_PRIORITY = ["results", "conclusion", "abstract", "methods", "discussion",
             "introduction", "title", "supplement", "other"]


def _headers():
    return {"User-Agent": config.USER_AGENT}


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _from_bioc(pmcid: str) -> dict:
    """Return {sectionbucket: text} from PMC BioC, or {} if unavailable."""
    pmcid = pmcid if pmcid.upper().startswith("PMC") else "PMC" + pmcid
    r = requests.get(BIOC.format(pmcid=pmcid), headers=_headers(),
                     timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    # BioC comes back either as a list or as {documents: [...]}.
    docs = data if isinstance(data, list) else data.get("documents", [])
    sections = {}
    for doc in docs:
        for d in (doc.get("documents", [doc]) if "documents" in doc else [doc]):
            for p in d.get("passages", []):
                infons = p.get("infons", {})
                stype = (infons.get("section_type") or infons.get("type")
                         or "OTHER").upper()
                bucket = _SECTION_MAP.get(stype, "other")
                txt = _strip(p.get("text", ""))
                if txt:
                    sections.setdefault(bucket, []).append(txt)
    return {k: "\n".join(v) for k, v in sections.items()}


def _epmc_abstract(resolved: dict) -> str:
    """Last-resort abstract from Europe PMC (covers most of PubMed)."""
    q = None
    if resolved.get("doi"):
        q = f'DOI:"{resolved["doi"]}"'
    elif resolved.get("pmid"):
        q = f'EXT_ID:{resolved["pmid"]} AND SRC:MED'
    if not q:
        return ""
    try:
        r = requests.get(EPMC, params={"query": q, "format": "json",
                                       "resultType": "core"},
                         headers=_headers(), timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        results = r.json().get("resultList", {}).get("result", [])
        if results:
            return _strip(results[0].get("abstractText", ""))
    except Exception:
        pass
    return ""


def fetch_text(resolved: dict) -> dict:
    """Given a resolved reference, return the paper text we could obtain.

    Returns: {sections: {bucket: text}, sections_available: [..],
              has_results(bool), open_access(bool), source: str,
              full_text: str (capped, priority order)}.
    """
    out = {"sections": {}, "sections_available": [], "has_results": False,
           "open_access": False, "source": "none", "full_text": ""}

    pmcid = resolved.get("pmcid")
    if pmcid:
        try:
            secs = _from_bioc(pmcid)
            if secs:
                out["sections"] = secs
                out["open_access"] = True
                out["source"] = "pmc_bioc"
        except Exception:
            pass

    # Fallback: abstract only.
    if not out["sections"]:
        abs = _epmc_abstract(resolved)
        if abs:
            out["sections"] = {"abstract": abs}
            out["source"] = "abstract_only"

    out["sections_available"] = [s for s in _PRIORITY
                                 if s in out["sections"] and out["sections"][s]]
    out["has_results"] = "results" in out["sections_available"]

    # Assemble capped full text in priority order with headers.
    parts, budget = [], config.MAX_TEXT_CHARS
    for bucket in _PRIORITY:
        txt = out["sections"].get(bucket)
        if not txt:
            continue
        header = f"\n## {bucket.upper()}\n"
        chunk = (header + txt)[:budget]
        parts.append(chunk)
        budget -= len(chunk)
        if budget <= 0:
            break
    out["full_text"] = "".join(parts).strip()
    return out
