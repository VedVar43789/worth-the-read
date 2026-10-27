# Worth Your Read

Worth Your Read is an [MCP](https://modelcontextprotocol.io) server any AI agent can call to check whether a cited paper actually supports the claim being made. The agent passes a claim and a reference. The tool resolves the link, checks for retraction, pulls the paper's Results section, and asks Claude for one of four verdicts: **SUPPORTED**, **OVERSTATED**, **UNSUPPORTED**, or **INSUFFICIENT**. Every quote in the verdict is checked against the source text. A quote that is not in the paper is dropped. A verdict with no verified quotes is forced to **INSUFFICIENT**.

Built for agents that cite scientific literature: Claude Desktop, Claude Code, and any in-house MCP client.

## The lab

**Claude Impact Lab**, Part II of the Claude Community Biotech and Life Sciences series. Hosted at Kiln, San Diego, on October 26, 2026.

Part I of the series surfaced three concerns from the biotech community. This project was built in the first track: **preventing hallucinations and confidently wrong outputs**, especially on scientific data.

**Team.** Vedant Vardhaan, Cecilia Hahn, Fedor Kuzminov.

**Result.** Best project in the preventing-hallucinations track.

The server was scoped to be assembled in about an hour: a resolver, a fetcher, a retraction check, a quote-verified judge, a scorer, and a card renderer. No database, no embeddings, no paywall scraping.

## Why this track

Hallucinated and confidently wrong citations are a known failure mode for AI in science. Three independent things routinely go wrong:

1. The link is wrong, dead, or points at a different paper than the one named.
2. The paper does not say what the agent claims, or says a weaker version of it.
3. A press release or headline distorted the finding before it reached the model.

Worth Your Read checks all three in one call. The guardrail is mechanical, not a prompt instruction: every returned quote must occur in the source text. The tool cannot assert a quote the paper does not contain.

## What the agent does

1. The agent drafts an answer with citations.
2. For each claim it calls `verify_claim` with the claim and a DOI, PMID, PMCID, or URL.
3. The tool resolves the identifier, confirms the paper, checks retraction status, fetches the Results section, and returns a structured verdict plus a markdown card. A failed verdict comes back with the gap spelled out: distortion type, the claim aspects the text does not establish, and a rationale. The agent uses that to decide what kind of source to look for next.
4. The agent revises weak claims and loops. When every claim is grounded or honestly marked **INSUFFICIENT**, it calls `score_answer` for one confidence score and a ranked "worth your read" source list.

`plan_search` sits in front of that loop when the question itself is still vague. It is deterministic: no model call. The first call returns clarifying questions (study type, population, recency, confidence bar, breadth). The second call, with those answers, returns query variants, filters, a `min_confidence` threshold, and a target number of candidates.

## Tools

| Tool | What it takes | What it returns |
| --- | --- | --- |
| `verify_claim(claim, reference, expected_title="")` | One claim and a DOI, PMID, PMCID, or URL. Optional claimed title, to catch a citation that resolves to the wrong paper. | Structured fields plus a markdown `card`: verdict, confidence band, link and retraction status, verified quotes, distortion type, and aspects the text does not establish. |
| `score_answer(claims, min_confidence=0.0)` | A list of `{claim, reference}` objects, optionally with `expected_title`. | Per-claim verdicts, an overall confidence score and letter grade, and a ranked source list. Sources below `min_confidence` are left off the list. |
| `plan_search(question, answers=None)` | A research question, then the same question plus answers keyed by clarifier id. | Clarifying questions, then an optimized search plan for the agent to execute with the two tools above. |

`score_answer` weights verdicts as SUPPORTED 1.0, OVERSTATED 0.4, and UNSUPPORTED or INSUFFICIENT 0.0, each multiplied by that claim's confidence, then averaged. The ranked list keeps only non-retracted sources judged SUPPORTED or OVERSTATED at or above `min_confidence`, best first. A paper that supports several claims appears once.

## Verdicts

| Verdict | Meaning |
| --- | --- |
| **SUPPORTED** | The paper's results establish the claim as stated. |
| **OVERSTATED** | The paper supports a weaker version. The claim exaggerates it. |
| **UNSUPPORTED** | The paper does not support the claim, or contradicts it. A retracted source is **UNSUPPORTED** without calling the judge. |
| **INSUFFICIENT** | The available text cannot settle the claim. This includes "no open text," "the text does not address the claim," and "the model quoted something that is not in the paper." |

**INSUFFICIENT** is a first-class outcome. LLM judges tend to sit near the top of a confidence scale while being wrong. An honest "the text cannot settle this" is the result the agent should be able to keep.

Confidence is also capped. Abstract-only checks (no Results section) cannot score above 0.5. A verdict downgraded because no quote survived verification cannot score above 0.3. Bands are High (≥ 0.75), Med (≥ 0.45), and Low.

### Distortion types

An **OVERSTATED** verdict names how the claim outruns the paper. The categories follow the press-release spin types in Sumner et al., *BMJ* 2014 ([doi:10.1136/bmj.g7015](https://doi.org/10.1136/bmj.g7015)): the study of how academic press releases exaggerate health findings before they reach headlines.

| Type | What went wrong |
| --- | --- |
| `correlation_causation` | An association is stated as a cause. |
| `animal_to_human` | An animal or preclinical result is stated for people. |
| `dropped_caveats` | Limits the paper stated are gone from the claim. |
| `effect_size_spin` | A small, uncertain, or non-significant effect is stated as established. |
| `cherry_picking` | A subgroup or secondary outcome is presented as the main finding. |
| `other` | A distortion that does not fit the types above. |

## How a check runs

| Stage | What happens |
| --- | --- |
| Resolve | Crossref, plus the NCBI ID Converter. Title match when `expected_title` is set. Retraction comes from Crossref `updated-by` and related notices. |
| Fetch | PMC BioC JSON, section-tagged, so Results and Conclusion outweigh the title and abstract. If no open-access full text exists, Europe PMC supplies the abstract. That path is labelled, and confidence is capped. |
| Judge | Claude, with forced structured output on the API and Bedrock paths. The server prefers the MCP host's own model via sampling, then falls back to the API or Bedrock. |
| Guard | Every quote is checked as a substring of the fetched text. Quotes that fail are dropped. SUPPORTED, OVERSTATED, or UNSUPPORTED with zero surviving quotes is rewritten to INSUFFICIENT. |

The judge is told to use only the provided text, weigh Results and Conclusion above the abstract, and quote verbatim. The substring check does not trust that instruction. It runs on every backend, including sampling.

Text handed to the judge is truncated (48,000 characters by default). There is no chunking and no retrieval index.

## Design principles

- **Quotes are a hard check.** Verification is a string match against the source, applied after the model responds.
- **INSUFFICIENT is a real verdict.** Absence of usable evidence is reported as such.
- **Distortion types are named.** An overstated claim is classified against a published taxonomy of spin, so the label can be inspected.
- **A failed check tells the agent what to do next.** Distortion type, unmet claim aspects, and the rationale describe the gap: which population, which effect, which study design is still missing.

## Where it sits

Existing tools cover part of this and stop.

- **Citation checkers** such as doi-mcp confirm that a reference exists. They do not say whether the paper supports the claim.
- **Synthesis tools** such as Scite, Consensus, and Elicit aggregate citation sentiment or pull findings, typically from abstracts.
- **Acurio** checks claim support against supplied manuscripts. It is built for a person reading a manuscript, and it does not type the distortion.
- **MCP verifiers** such as eleata-verify-mcp and groundcheck-mcp compare a claim to text the caller already supplied. They do not fetch a paper's Results section, and they do not type how a claim was spun.

Worth Your Read combines Results-section grounding, distortion typing, and delivery as MCP tools an agent calls on its own citations.

## Demo cases

Five headlines from the lab, one for each way a citation goes wrong. Retracted papers are judged from the notice alone.

| Headline | Verdict | Paper |
| --- | --- | --- |
| The Pfizer-BioNTech COVID-19 vaccine is about 95% effective. | SUPPORTED | Polack et al., *NEJM* 2020. [10.1056/NEJMoa2034577](https://doi.org/10.1056/NEJMoa2034577) |
| Bacon is as dangerous as smoking. | OVERSTATED | Bouvard et al., IARC, *Lancet Oncology* 2015. Hazard is stated as if it were risk. [10.1016/S1470-2045(15)00444-1](https://doi.org/10.1016/S1470-2045(15)00444-1) |
| Red wine extends your life. | OVERSTATED | Baur et al., *Nature* 2006. Mouse data and very high doses, stated for people. [10.1038/nature05354](https://doi.org/10.1038/nature05354) |
| The MMR vaccine causes autism. | UNSUPPORTED | Wakefield et al., *Lancet* 1998. Retracted. [10.1016/S0140-6736(97)11096-0](https://doi.org/10.1016/S0140-6736(97)11096-0) |
| A mild acid bath turns adult cells into stem cells. | UNSUPPORTED | Obokata et al., *Nature* 2014. Retracted. [10.1038/nature12968](https://doi.org/10.1038/nature12968) |

`python -m worth_your_read.smoke_test` resolves and fetches a subset of these (the vaccine, the red-wine paper, and the Wakefield retraction) plus an open-access full-text case, and runs the quote guard on a verbatim quote and a fabricated one. The fabricated quote is forced to INSUFFICIENT.

## Stack

Python 3.10+. [FastMCP](https://github.com/modelcontextprotocol/python-sdk) server. Claude as the judge: Anthropic API by default, AWS Bedrock as an alternative, or the MCP client's model via sampling. Crossref and the NCBI ID Converter for resolution. PMC BioC JSON for full text. Europe PMC for the abstract fallback. Markdown cards from `render.py`.

One citation per claim. Open-access full text only; paywalled papers fall back to the abstract. No PDF parsing, no database, no embeddings.

## Install

From GitHub, no clone:

```bash
pip install "git+https://github.com/VedVar43789/worth-the-read.git"
```

That installs the `worth-your-read` command. Point an MCP client at it. For Claude Desktop, in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "worth-your-read": {
      "command": "worth-your-read",
      "env": { "ANTHROPIC_API_KEY": "sk-ant-...", "WYR_USE_BEDROCK": "0" }
    }
  }
}
```

Restart the client. The three tools appear. If `worth-your-read` is not on `PATH`, use the path from `pip show -f worth-your-read`, or `python -m worth_your_read.server`.

If the client supports MCP sampling, the judge runs on the client's model. Omit `ANTHROPIC_API_KEY` and do not set `WYR_USE_BEDROCK`.

From a clone:

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Python 3.10 or newer. Put `ANTHROPIC_API_KEY` in `.env` for the API judge.

Smoke test, from the repo root:

```bash
./.venv/bin/python -m worth_your_read.smoke_test
```

Resolution, fetch, retraction detection, and the quote guard run with no key. The live judge runs when a backend is configured.

Run the server on stdio:

```bash
./.venv/bin/python -m worth_your_read.server
```

```json
{
  "mcpServers": {
    "worth-your-read": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "worth_your_read.server"],
      "cwd": "/absolute/path/to/worth-the-read",
      "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

## Judge backends

The quote guard is the same on every path. The server tries them in this order:

1. **MCP sampling.** The host model, through the client. No API key.
2. **Anthropic API.** `ANTHROPIC_API_KEY`. Default model is `claude-sonnet-5-5`; override with `WYR_MODEL`.
3. **AWS Bedrock.** Set `WYR_USE_BEDROCK=1`. `CLAUDE_CODE_USE_BEDROCK=1` is honored too. Uses the standard AWS credential chain. Set `WYR_AWS_PROFILE` to pick a profile and `AWS_REGION` for the region (default `us-east-1`). Set `WYR_BEDROCK_MODEL` to an inference-profile id the account can invoke:

   ```bash
   aws bedrock list-foundation-models --by-provider anthropic
   export WYR_USE_BEDROCK=1
   export WYR_BEDROCK_MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0
   export AWS_REGION=us-east-1
   ```

   Set `WYR_USE_BEDROCK=0` to force the API-key path under Claude Code. The IAM principal needs `bedrock:InvokeModel`. Calls bill the AWS account.

If sampling fails and no API or Bedrock credentials are set, the tool still returns resolution and retraction results, with verdict **INSUFFICIENT** and a note that no judge ran.

Optional environment variables, also listed in `.env.example`:

| Variable | Role |
| --- | --- |
| `WYR_CONTACT_EMAIL` | Sent to Crossref and NCBI polite pools. |
| `WYR_HTTP_TIMEOUT` | Outbound HTTP timeout in seconds. Default 20. |
| `WYR_MAX_TEXT_CHARS` | Cap on text sent to the judge. Default 48000. |

## Web surfaces

Two extra ways to run the same pipeline. The lab deliverable is the MCP server.

**Static site** in `docs/`. No server. The visitor supplies their own Anthropic API key, stored in that browser's `localStorage`. Retrieval uses the CORS-enabled Crossref and Europe PMC endpoints. The judge calls the Anthropic API from the browser (`anthropic-dangerous-direct-browser-access`), so the key is visible to the page. Link checks and retraction detection work without a key. To publish: GitHub → Settings → Pages → Deploy from a branch → `main` / `docs`.

**FastAPI app** in `web/`. The key stays on the server.

```bash
pip install "worth-your-read[web] @ git+https://github.com/VedVar43789/worth-the-read.git"
export ANTHROPIC_API_KEY=sk-ant-...
export WYR_USE_BEDROCK=0
uvicorn worth_your_read.web.app:app --reload
```

Open `http://127.0.0.1:8000`.

## Status

At the end of the evening, resolution, retraction detection, scoring, and card rendering had been run against the live Crossref, NCBI, and PMC APIs. The Claude judging path and the quote-substring guard are written and wired. The guard is exercised offline by the smoke test. A full judging run still needs a sampling client or an API or Bedrock credential.

## Limitations

- Open-access full text only (PMC OA). Paywalled papers are judged on the abstract, labelled as such, with confidence capped.
- No PDF parsing. Text is truncated rather than embedded or retrieved in chunks.
- One citation per claim.
- The judge locates what the provided text supports. It is not peer review, and it will say when a claim needs domain expertise the text does not supply.

## Who it is for

The caller is an agent. The check matters wherever that agent's answer is used: a literature review, a story being fact-checked, or a policy or clinical workflow that depends on the primary finding rather than the headline.
