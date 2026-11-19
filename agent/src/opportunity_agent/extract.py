"""Stage 3: turn free-text research notes into typed signals (one structured-output call)."""

from __future__ import annotations

from typing import Any

from .llm import LLM
from .models import ExtractedSignal, ExtractedSignals

SYSTEM = (
    "You convert research notes into structured signals. Rules:\n"
    "- One signal per FINDING in the notes. Do not invent findings and do not merge them.\n"
    "- Copy the quote character-for-character from the notes. Never rephrase it.\n"
    "- The url must be the URL given for that finding.\n"
    "- channel = the channel heading the finding appears under.\n"
    "- Skip findings that have no URL or no quote."
)


def _render(results: list[dict[str, Any]]) -> str:
    parts = []
    for r in results:
        if r["channel"] == "sweep":  # a list of leads, not findings
            continue
        notes = r["notes"].strip() or "NO FINDINGS"
        parts.append(f"=== channel: {r['channel']} ===\n{notes}")
    return "\n\n".join(parts)


async def extract(llm: LLM, results: list[dict[str, Any]]) -> list[ExtractedSignal]:
    if not any(r["notes"].strip() for r in results if r["channel"] != "sweep"):
        return []
    resp = await llm.call(
        stage="extract", label="all_channels", system=SYSTEM,
        user=_render(results), output_format=ExtractedSignals, max_tokens=12000,
    )
    return resp.parsed_output.signals
