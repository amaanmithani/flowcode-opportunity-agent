# Flowcode Opportunity Agent

Give it a company name or website. It researches what the brand is doing **right now** across TV, social, email, events, packaging and retail. It returns a short, ranked list of where Flowcode can help. Each opportunity says what's happening, why Flowcode fits, and where the fact came from. Every fact is checked against its source page before it is shown.

**Sample output:** [The Hershey Company](data/briefs/hershey.md) ([JSON](data/briefs/hershey.json)). Two more brands were run to test that the approach generalizes: [e.l.f. Beauty](data/briefs/e-l-f-beauty.md) and [Starbucks](data/briefs/starbucks.md).

| Brand | Claims found | Verified | Opportunities (strong) | Cost | Time |
|---|---|---|---|---|---|
| The Hershey Company | 17 | 13 | 5 (2) | $1.11 | ~90s |
| e.l.f. Beauty | 15 | 12 | 5 (4) | $1.08 | 124s |
| Starbucks | 12 | 7 | 4 (3) | $0.99 | 106s |

On average a brand costs **about $1.06**, which works out to **about $0.35 per strong opportunity** (score 30 or higher).

---

## How it works

```
company name or URL
  │
  1. RESOLVE    official domain, newsroom, sub-brands. Checked against Flowcode's public
  │             customer list → labeled prospect / expansion / possible expansion
  2. SWEEP      read the brand's own newsroom and press wires first (last 90 days)
  3. RESEARCH   7 workers in parallel, one per channel: TV & broadcast, social, email & loyalty,
  │             events, packaging, retail, company-wide. Each gets the sweep's leads plus its
  │             own search plan (references/search_plans.md)
  4. EXTRACT    notes → typed claims: {claim, url, exact quote, date, channel}
  5. VERIFY     plain code, no LLM: fetch the page, find the exact quote, reject anything
  │             older than 90 days, remove duplicates. Anything that fails is dropped.
  6. RANK       map each verified claim to a Flowcode product, play and the closest case
  │             study (references/capabilities.json), then score and rank
  7. BRIEF      JSON + Markdown + web page, and a run log (tokens, searches, cost per stage)
```

**Every fact is checked in code against its source.** The model never gets the last word on what is true. The page shows the exact quote, the link, the date and the checks each fact passed, and it lists what was thrown out and why.

**Scoring is simple and visible.** The model rates each opportunity from 1 to 5 on three things, using a written rubric, and gives a one-line reason for each:

- **Confidence:** how solid the evidence is, and how closely a Flowcode case study matches.
- **Size:** the reach of the touchpoint (national TV versus a local event).
- **Timing:** is there still time for Flowcode to get on it? This is not the same as whether the campaign is live. Packaging already on shelves is a pitch for the next run.

The final score is calculated in code: `confidence × size × timing`, scaled to 100. Multiplying means a bet needs all three: a huge, certain opportunity that's too late still ranks low. Code also enforces the rubric. For example, confidence 5 requires the brand's own announcement or two agreeing sources, and an opportunity that cites a claim that failed verification is removed.

**The output is built for a rep.** Each card shows four lines: what's happening, why Flowcode, proof (the closest case study and its result), and the first step. The play, contacts, scoring and sources are one click away. Opportunities scoring under 30 move to a one-line "also worth watching" list. Reps can accept an opportunity, or dismiss it with a reason, and those choices are recorded as events.

**Reference files the agent reads:**
- `references/capabilities.json`: Flowcode's 5 products, 14 case studies with metrics copied from flowcode.com, 7 plays (signal → product → case study → who to contact) and the scoring rubric.
- `references/search_plans.md`: queries and sources per channel.
- `references/flowcode_customers.json`: brands Flowcode names publicly. These are labeled "expansion", not "prospect".

## Where I spent the time

On **research quality and sourcing**, and on **an output someone can act on**. Ranking is deliberately simple and transparent.

- **Sourcing.** The agent reads the brand's own newsroom first, quotes from pages it read in full, and verifies every quote in code. Search effort is weighted toward the channels where Flowcode has the most proof (packaging, TV and events get the most searches).
- **Actionable output.** Each card is about 60 words. It names a real Flowcode product and the closest case study, gives a concrete first step, and has accept/dismiss buttons.

## Tradeoffs

- **A fixed pipeline, not an agent framework.** The email names the channels, so code starts one worker per channel. That gives full coverage, a predictable cost, a separate evaluation per channel, and it batches easily. Model-chosen subagents fit open-ended work better; they are the next step for deep dives on the top leads.
- **Research and extraction are separate calls.** Research returns free-text notes; a second call turns them into typed claims; code then verifies the quotes. I don't rely on model citations alone.
- **Models.** Sonnet 5.5 for research and extraction, Opus 5.5 for ranking (the judgment step). Each stage's model is one setting in `agent/src/opportunity_agent/config.py`. Because verification catches bad quotes, research can move to a cheaper model (Haiku 5.5) to cut cost further, and the verified-claim rate shows whether quality holds.
- **Search.** Claude's built-in web search and fetch: no extra vendor and no extra key. Some publishers block automated fetches (7 of the 12 dropped claims across the three brands). When that happens, verification falls back to the page text Claude's fetch tool returned. A hosted fetcher such as Firecrawl is the next step for those sites.
- **Social platforms.** Instagram, TikTok and similar sites block automated reading, so social activity comes from press coverage of the campaigns.
- **Search-quality check.** For Hershey I ran the searches a rep would do by hand (about 15 minutes). The manual search surfaced 5 current items; the agent found 4 of them plus 3 the manual search missed (a Twizzlers CFL sponsorship, a Reese's bakery expansion, a Nitro Bar pop-up). It correctly left out the Winter Olympics campaign as older than 90 days.

## Running across thousands of companies

The pipeline already works one account at a time, saves each stage to disk, and has a batch command (`opportunity-agent batch companies.csv`). Scaling it is mostly scheduling and storage.

**Cost.** Measured at about $1.06 per account per full run, of which research is about 80%.
- **Tiers:** customers refresh weekly, active prospects every two weeks, the long tail monthly.
- **Batch API:** scheduled refreshes run through it at 50% off.
- **Research on Haiku:** cuts the largest cost further.
- **Prompt caching:** system prompts and the capability sheet are kept byte-stable so they cache, and the run log tracks cache hits.
- **Deep research only on change** (see Freshness). This is the biggest saving.

Worked example: 10,000 accounts, refreshed weekly, about 20% changing in a given week, run through the Batch API, is roughly 10,000 × 20% × $0.53 ≈ **$1,060 a week**. That's an estimate, not a measurement.

**Speed.** A full run takes 1.5–2 minutes, mostly the parallel research. At scale, accounts go onto a job queue with many workers. API rate limits are the ceiling, not compute.

**Keeping data fresh.**
- **Cheap change detection first:** newsroom RSS feeds, press wires, ad libraries and page diffs. Full research runs only when something changed.
- **Signals are remembered across runs.** Each claim is keyed by its URL and quote. Every refresh re-verifies past claims for free (plain code), so one researcher missing an item doesn't make it disappear. A claim only drops off when its page goes stale or the quote is gone.
- **Change tracking:** each opportunity is marked **new**, **still active** or **expired**. An opportunity expires only when none of its evidence still passes.

**Checking quality.**
- **Automatic:** quote verification on every claim; drop reasons tracked by type; the verified-claim rate tracked per channel and per model.
- **Evaluation set:** about 20 labeled brands across industries, re-run whenever prompts or models change.
- **LLM judge:** "Does the opportunity follow from its quoted evidence?" Quotes are verified today; the text written around them is the next thing to check.
- **Human spot checks,** plus the rep accept/dismiss data.

## Always-on agent

1. **A scheduler** runs each account at its tier's interval, starting with the cheap change detection.
2. **Compare with the last brief.** New or materially changed opportunities above a score threshold are routed out.
3. **Route to the account owner** (from the CRM) via Slack or a CRM task, with the card and its sources.
4. **A rep approves before anything reaches the brand.** In Flowcode's own words: *"Most companies automate this part. We prefer to keep it human."*
5. **Accept and dismiss decisions feed back into scoring.** After a few hundred decisions, the rubric weights can be tuned. With deal outcomes, a learned ranking model becomes possible.

## Measuring success

- **Precision:** the share of opportunities that hold up on rep review (the accept rate, plus dismissal reasons like "Source looks wrong" or "Bad fit").
- **Usefulness:** meetings booked and pipeline created from accepted opportunities.
- **Coverage and freshness:** the verified-claim rate per channel, and the time from a brand's announcement to the opportunity appearing.
- **Cost:** dollars per account and per accepted opportunity.

The page already records accept/dismiss events with reasons (stored in the browser for this prototype). In production they go to product analytics and the CRM.

## Where MCP fits

- **CRM in.** Read account owner, stage and customer status from Flowcode's HubSpot or Salesforce through their MCP servers. That replaces the public customer list.
- **Opportunities out.** An MCP server exposing `get_account_brief` and `whats_new` lets reps ask from Claude or their own tools ("what's new with Hershey this week?").
- **New sources plug in as MCP tools** (an ad library, a press-wire feed, a hosted fetcher) without changing the pipeline.

## What I'd build next

1. A hosted fetcher (e.g. Firecrawl) as a fallback for publishers that block automated reads.
2. An LLM judge that checks each card's text against its quoted evidence.
3. A CRM connection: account owner and status in, opportunities out as tasks.
4. A watchlist with change detection and a weekly Slack digest.
5. An adaptive deep-dive subagent for the top 2–3 leads.
6. Running live research from the hosted site (today it runs locally).

---

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20+, an Anthropic API key in `.env` (see `.env.example`).

```bash
# Research a brand from the command line
cd agent
uv sync
uv run opportunity-agent run "Hershey"            # about 90s, about $1
uv run opportunity-agent run "Hershey" --from-stage rank   # re-rank using saved research, a few cents
uv run opportunity-agent batch companies.csv       # many companies (CSV column: company)
uv run pytest                                      # offline tests, no API key needed

# The web page (with a working "Research a brand" box when run locally)
cd web
npm install
npm run dev
```

**Layout:**
- `agent/`: the Python pipeline (`resolve`, `research`, `extract`, `verify`, `rank`, `store`, `pipeline`).
- `references/`: the capability sheet, search plans and customer list.
- `data/`: run outputs, briefs and the signal store.
- `web/`: the Next.js account brief page.
