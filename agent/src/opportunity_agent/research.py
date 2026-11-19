"""Stage 2: one research worker per channel, launched from code (fixed fan-out)."""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from typing import Any

from . import config
from .llm import LLM, text_of, web_tools
from .models import Resolution

_PLANS = (config.REFERENCES / "search_plans.md").read_text()


def _section(channel: str) -> str:
    m = re.search(rf"^## {channel}\b.*?(?=^## |\Z)", _PLANS, flags=re.S | re.M)
    if not m:
        raise KeyError(f"no search plan for {channel}")
    return m.group(0).strip()


_GENERAL = re.search(r"^## General rules.*?(?=^## )", _PLANS, flags=re.S | re.M).group(0).strip()

# Identical across all workers and runs, so it is cacheable. Never put dates or brand names here.
SYSTEM = [{
    "type": "text",
    "text": (
        "You are a market researcher for Flowcode, an enterprise platform that turns "
        "physical and digital touchpoints (packaging, retail, TV, events, social, email) "
        "into measurable mobile conversion funnels. Your job is to find what a brand is "
        "doing RIGHT NOW in one channel. Another system will verify every quote against "
        "the live page, so accuracy matters more than volume.\n\n"
        f"{_GENERAL}\n\n"
        "Output format: for each finding, write exactly:\n"
        "FINDING\nClaim: <one sentence>\nURL: <exact url>\nDate: <YYYY-MM-DD or unknown>\n"
        "Source type: <brand_owned|press_wire|trade_press|news|other>\n"
        "Quote: \"<verbatim text copied from the page, 12-40 words>\"\n"
        "Uses QR/links: <yes|no|unknown>\n\n"
        "Quotes must be copied from a page you read in full with web_fetch whenever possible; "
        "search snippets are often truncated or reworded and will fail verification. "
        "Use your page reads on the 2-3 most promising URLs (press releases first).\n\n"
        "Report 0 to 4 findings, best first. If nothing current exists for this channel, write NO FINDINGS."
    ),
    "cache_control": {"type": "ephemeral"},
}]


def _user_prompt(res: Resolution, channel: str, today: dt.date, sweep_notes: str = "") -> str:
    plan = _section(channel).replace("{year+1}", str(today.year + 1)).replace("{year}", str(today.year))
    plan = plan.replace("{brand}", res.official_name)
    brands = ", ".join(res.sub_brands[:10]) or "n/a"
    return (
        f"Today is {today.isoformat()}. Only report items from the last {config.FRESHNESS_DAYS} days "
        f"or announced for the future.\n\n"
        f"Brand: {res.official_name}\nDomain: {res.domain}\nNewsroom: {res.newsroom_url or 'unknown'}\n"
        f"Sub-brands: {brands}\n\n"
        f"Your channel plan:\n{plan}\n\n"
        "Searching for the sub-brands as well as the parent is fine."
        + (f"\n\nRecent releases from the brand's own newsroom and press wires (already found; "
           f"web_fetch any that fit your channel):\n{sweep_notes}" if sweep_notes else "")
        + f"\n\nThis list is a starting point, not your whole answer. Run at least "
          f"{min(2, config.SEARCHES_BY_CHANNEL[channel])} searches of your own from your channel plan; "
          f"coverage outside press releases (trade press, ad trackers, retailer news) is the point."
    )


def collect_sources(resp: Any) -> dict[str, Any]:
    """Pull what the server tools actually returned. This is real page data, not model output.

    - search hits: url, title, page_age
    - fetched documents: url -> full text (used as a backup when our own fetch is blocked)
    - citations: url -> cited_text snippets
    """
    hits: list[dict] = []
    docs: dict[str, str] = {}
    cited: dict[str, list[str]] = {}
    errors: list[str] = []
    for block in getattr(resp, "_all_content", resp.content):
        b = block.to_dict() if hasattr(block, "to_dict") else dict(block)
        t = b.get("type")
        if t == "web_search_tool_result":
            content = b.get("content")
            if isinstance(content, list):
                for r in content:
                    if r.get("type") == "web_search_result":
                        hits.append({"url": r.get("url"), "title": r.get("title"), "page_age": r.get("page_age")})
            elif isinstance(content, dict):
                errors.append(f"search:{content.get('error_code')}")
        elif t == "web_fetch_tool_result":
            content = b.get("content") or {}
            if content.get("type") == "web_fetch_result":
                doc = content.get("content") or {}
                data = (doc.get("source") or {}).get("data")
                if isinstance(data, str) and content.get("url"):
                    docs[content["url"]] = data
            else:
                errors.append(f"fetch:{content.get('error_code')}")
        elif t == "text":
            for c in b.get("citations") or []:
                url, txt = c.get("url"), c.get("cited_text")
                if url and txt:
                    cited.setdefault(url, []).append(txt)
    return {"hits": hits, "docs": docs, "cited": cited, "tool_errors": errors}


SWEEP_SYSTEM = (
    "You collect a brand's recent official announcements for a research pipeline. "
    "List only items you actually saw, with exact URLs. No commentary."
)


async def newsroom_sweep(llm: LLM, res: Resolution, today: dt.date) -> dict[str, Any]:
    """Read the brand's own sources first: newsroom page + press wires, last 90 days.

    Runs once, before the channel workers, and its list is handed to all of them.
    """
    since = (today - dt.timedelta(days=config.FRESHNESS_DAYS)).isoformat()
    user = (
        f"Today is {today.isoformat()}. Brand: {res.official_name} (sub-brands: {', '.join(res.sub_brands[:10])}).\n"
        f"Newsroom: {res.newsroom_url or 'unknown'}\n\n"
        f"1. If a newsroom URL is given, web_fetch it.\n"
        f"2. Search press wires for releases since {since}, e.g. "
        f"\"{res.official_name} site:prnewswire.com\" and \"{res.official_name} announces\".\n"
        f"Output up to 12 releases from since {since} (or announced for the future), newest first, one per line:\n"
        f"YYYY-MM-DD | title | exact URL\n"
        f"If none, write NONE."
    )
    try:
        resp = await llm.call(
            stage="sweep", label="newsroom", system=SWEEP_SYSTEM, user=user,
            tools=web_tools("sweep", searches=config.SWEEP_SEARCHES, fetches=config.SWEEP_FETCHES),
            max_tokens=4000,
        )
    except Exception as e:
        llm.log.event(type="research_error", channel="sweep", error=repr(e))
        return {"channel": "sweep", "notes": "", "error": repr(e), "hits": [], "docs": {}, "cited": {}, "tool_errors": []}
    return {"channel": "sweep", "notes": text_of(resp), "error": None, **collect_sources(resp)}


async def research_channel(llm: LLM, res: Resolution, channel: str, today: dt.date, sweep_notes: str = "") -> dict[str, Any]:
    try:
        resp = await llm.call(
            stage="research", label=channel, system=SYSTEM,
            user=_user_prompt(res, channel, today, sweep_notes),
            tools=web_tools("research", searches=config.SEARCHES_BY_CHANNEL[channel], fetches=config.FETCHES_PER_WORKER),
            max_tokens=8000,
        )
    except Exception as e:  # one failed channel must not kill the run
        llm.log.event(type="research_error", channel=channel, error=repr(e))
        return {"channel": channel, "notes": "", "error": repr(e), "hits": [], "docs": {}, "cited": {}, "tool_errors": []}
    return {"channel": channel, "notes": text_of(resp), "error": None, **collect_sources(resp)}


async def research_all(llm: LLM, res: Resolution, today: dt.date | None = None) -> list[dict[str, Any]]:
    today = today or dt.date.today()
    sweep = await newsroom_sweep(llm, res, today)
    sweep_notes = "" if sweep["notes"].strip().upper().endswith("NONE") else sweep["notes"].strip()
    sem = asyncio.Semaphore(config.RESEARCH_CONCURRENCY)

    async def one(ch: str):
        async with sem:
            return await research_channel(llm, res, ch, today, sweep_notes)

    channels = await asyncio.gather(*(one(ch) for ch in config.CHANNELS))
    return [sweep, *channels]
