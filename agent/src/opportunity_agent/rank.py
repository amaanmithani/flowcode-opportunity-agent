"""Stage 5: map verified signals to Flowcode plays and rank them.

The model chooses the play, product, case study and the 1-5 sub-scores. Code
checks every reference, works out the final score, and drops any opportunity
whose signals are not verified.
"""

from __future__ import annotations

import json
from typing import Any

from . import config
from .llm import LLM
from .models import Resolution, Signal, make_rank_models

CAPS = json.loads((config.REFERENCES / "capabilities.json").read_text())
PLAYS = {p["id"]: p for p in CAPS["plays"]}
PRODUCTS = {p["id"]: p for p in CAPS["products"]}
CASES = {c["id"]: c for c in CAPS["case_studies"]}
RankedOpportunity, RankOutput = make_rank_models(list(PLAYS), list(PRODUCTS), list(CASES))

SYSTEM = [{
    "type": "text",
    "text": (
        "You are a senior strategist on Flowcode's revenue team. You turn verified "
        "signals about a brand into opportunities a sales rep would actually chase.\n\n"
        "Rules:\n"
        "- Use ONLY the verified signals provided. Every opportunity must cite the signal ids "
        "it rests on. Never state a fact that is not in a cited signal.\n"
        "- Pick the play, products and case study from the capability sheet below. Choose the "
        "case study closest to the brand's situation (same channel, similar category).\n"
        "- Group signals that point to the same play into one opportunity. Do not repeat "
        "the same idea twice.\n"
        "- Score confidence, size and timing 1-5 using the rubric. Timing means whether Flowcode still has time to get on the touchpoint, not whether the campaign is live. Confidence includes how closely the case study matches. Explain each in one short clause.\n"
        "- Quality over quantity: 3-6 strong opportunities beat 10 weak ones. Put signals "
        "with no real Flowcode fit in skipped_signal_ids.\n"
        "- Write in Flowcode's own terms (touchpoints, conversion funnels, first-party data, "
        "connections). Be concrete; no hype.\n"
        "- contact_roles are job titles at the brand, never invented names.\n"
        "- Be brief. A rep reads each card in 15 seconds. Respect every word limit in the schema. "
        "Say each thing once: the gap goes in why_flowcode, the mechanics in suggested_play, and the "
        "case study is shown separately, so do not restate it.\n\n"
        "CAPABILITY SHEET (JSON):\n" + json.dumps(CAPS, indent=1)
    ),
    "cache_control": {"type": "ephemeral"},
}]


def _signal_view(s: Signal) -> dict[str, Any]:
    return {
        "id": s.id, "channel": s.channel, "claim": s.claim, "quote": s.quote,
        "date": s.effective_date or "undated (live page)", "source_type": s.source_type,
        "touchpoint": s.touchpoint, "uses_qr_or_links": s.uses_qr_or_links, "url": s.url,
    }


def final_score(c: int, s: int, t: int) -> int:
    return round(c * s * t / 125 * 100)


async def rank(llm: LLM, res: Resolution, account: dict, signals: list[Signal]) -> dict[str, Any]:
    verified = [s for s in signals if s.verified]
    if not verified:
        return {"opportunities": [], "skipped_signal_ids": [], "rejected": []}

    user = (
        f"Brand: {res.official_name} ({res.category})\nDescription: {res.one_liner}\n"
        f"Account status: {account['label']}\n\n"
        f"Verified signals ({len(verified)}):\n" + json.dumps([_signal_view(s) for s in verified], indent=1)
    )
    resp = await llm.call(stage="rank", label="rank", system=SYSTEM, user=user,
                          output_format=RankOutput, max_tokens=16000)
    out = resp.parsed_output
    by_id = {s.id: s for s in verified}

    opps: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for o in out.opportunities:
        valid_ids = [i for i in dict.fromkeys(o.signal_ids) if i in by_id]
        bad = [i for i in o.signal_ids if i not in by_id]
        if not valid_ids:
            rejected.append({"title": o.title, "reason": f"no verified signals (cited {o.signal_ids})"})
            continue
        sigs = [by_id[i] for i in valid_ids]

        # Rubric rule, enforced in code: confidence 5 needs the brand's own source or 2+ signals.
        confidence = o.confidence
        strong = any(s.source_type in ("brand_owned", "press_wire") for s in sigs) or len(sigs) >= 2
        adjustments = []
        if confidence == 5 and not strong:
            confidence = 4
            adjustments.append("confidence capped at 4: single secondary source")
        if bad:
            adjustments.append(f"removed unknown signal ids {bad}")

        d = o.model_dump()
        d.update(
            confidence=confidence, signal_ids=valid_ids,
            score=final_score(confidence, o.size, o.timing),
            play=PLAYS[o.play_id], products=[PRODUCTS[p] for p in dict.fromkeys(o.product_ids)],
            case_study=CASES[o.case_study_id], adjustments=adjustments,
            channels=sorted({s.channel for s in sigs}),
            uses_qr_or_links=any(s.uses_qr_or_links for s in sigs),
        )
        opps.append(d)

    opps.sort(key=lambda d: (-d["score"], -d["confidence"]))
    for i, d in enumerate(opps, 1):
        d["rank"] = i
    return {"opportunities": opps, "skipped_signal_ids": out.skipped_signal_ids, "rejected": rejected}
