"""Smoke test. Retrieval parts run offline (no API key). The full verify_claim
path runs only if ANTHROPIC_API_KEY is set.

Run from the project root:
    ./worth_your_read/.venv/bin/python -m worth_your_read.smoke_test
"""
import asyncio
import sys

from . import resolve as R
from . import fetch as F
from . import judge as J

# (label, claim, reference, expected-ish verdict)
CASES = [
    ("supported", "The Pfizer COVID-19 vaccine is about 95% effective.",
     "10.1056/NEJMoa2034577"),
    ("overstated/animal", "Drinking red wine extends your life.",
     "10.1038/nature05354"),
    ("retracted", "The MMR vaccine causes autism.",
     "10.1016/S0140-6736(97)11096-0"),
    # An open-access PLOS paper, to exercise the PMC BioC full-text path.
    ("oa-fulltext", "Handwashing reduces respiratory infection.",
     "10.1371/journal.pmed.0030442"),
]


def main():
    print("=" * 70)
    print("RESOLVE + FETCH (offline, no API key needed)")
    print("=" * 70)
    for label, claim, ref in CASES:
        print(f"\n[{label}] {ref}")
        res = R.resolve(ref)
        print(f"  resolved={res['resolved']} citation_ok={res['citation_ok']} "
              f"retracted={res['retracted']} concern={res['concern']}")
        print(f"  title: {str(res['title'])[:72]}")
        print(f"  authors: {str(res['authors'])[:60]}  year={res['year']}")
        print(f"  ids: doi={res['doi']} pmcid={res['pmcid']} pmid={res['pmid']}")
        if res["notices"]:
            print(f"  notices: {res['notices']}")
        fetched = F.fetch_text(res)
        print(f"  fetch: source={fetched['source']} open_access={fetched['open_access']} "
              f"has_results={fetched['has_results']}")
        print(f"  sections: {fetched['sections_available']} "
              f"(full_text={len(fetched['full_text'])} chars)")

    print("\n" + "=" * 70)
    print("QUOTE-VERIFICATION GUARD (offline, no backend needed)")
    print("=" * 70)
    # Fetch a real abstract, then feed the judge TWO synthetic JSON verdicts:
    # one quoting the paper verbatim (kept) and one with a fabricated quote
    # (rejected -> verdict forced to INSUFFICIENT).
    res = R.resolve("10.1038/nature05354")
    fetched = F.fetch_text(res)
    src = fetched["full_text"][:300].replace("\n", " ")
    real_quote = " ".join(src.split()[3:14])  # a genuine span from the text
    print(f"  (using a real span as the 'good' quote: “{real_quote[:70]}…”)")

    good = ('{"verdict":"SUPPORTED","confidence":0.8,'
            '"evidence":[{"quote":"%s","section":"abstract","stance":"ENTAILS"}],'
            '"rationale":"quotes the paper"}') % real_quote.replace('"', "'")
    bad = ('{"verdict":"SUPPORTED","confidence":0.9,'
           '"evidence":[{"quote":"this exact sentence is not in the paper at all",'
           '"section":"results","stance":"ENTAILS"}],"rationale":"fabricated"}')

    gr = J.parse_json_verdict(good, fetched)
    br = J.parse_json_verdict(bad, fetched)
    print(f"  verbatim quote  -> verdict={gr['verdict']} "
          f"verified={gr['quotes_verified']} downgraded={gr['downgraded']}")
    print(f"  fabricated quote-> verdict={br['verdict']} "
          f"verified={br['quotes_verified']} downgraded={br['downgraded']} "
          "(forced to INSUFFICIENT ✓)")

    print("\n" + "=" * 70)
    print("FULL verify_claim via server (retracted path needs no backend)")
    print("=" * 70)
    from .server import _verify
    r = asyncio.run(_verify("The MMR vaccine causes autism.",
                            "10.1016/S0140-6736(97)11096-0"))
    print(r["card"])
    print(f"\n  judge_backend={r.get('judge_backend')}")
    print("\n(The live judge runs through the HOST model via MCP sampling when "
          "this is loaded as an MCP server; ctx=None here, so non-retracted "
          "cases would fall back to api/bedrock.)")


if __name__ == "__main__":
    sys.exit(main())
