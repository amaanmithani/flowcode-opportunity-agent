"""Stage 1: resolve the brand (domain, newsroom, sub-brands) and label it as a customer or a prospect."""

from __future__ import annotations

import json
import re
import unicodedata

from rapidfuzz import fuzz

from . import config
from .llm import LLM, text_of, web_tools
from .models import Resolution

SYSTEM = (
    "You identify companies for a B2B research pipeline. Use web search to confirm "
    "the official website domain, the newsroom or press page, the parent company, "
    "and the main consumer brands it owns. Be brief and factual."
)


async def resolve(llm: LLM, company: str) -> Resolution:
    found = await llm.call(
        stage="resolve", label="lookup", system=SYSTEM,
        user=f"Company or website: {company}\n\nFind: official name, official domain, "
             "newsroom/press URL, parent company (if any), category, up to 10 major consumer "
             "brands it owns, and a one-line description.",
        tools=web_tools("resolve", searches=2, fetches=0), max_tokens=4000,
    )
    parsed = await llm.call(
        stage="resolve", label="structure", system="Convert notes into the requested JSON. Use only facts in the notes.",
        user=text_of(found), output_format=Resolution, max_tokens=2000,
    )
    return parsed.parsed_output


# --- Customer / prospect labelling (plain code) ------------------------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9+ ]", " ", s)
    s = re.sub(r"\b(the|inc|co|company|corp|corporation|llc|ltd|brands?)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _matches(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Short names (e.g. "NFL", "AMC") only match exactly. Fuzzy matching would
    # wrongly link them to any name that contains those letters.
    if min(len(na), len(nb)) <= 4:
        return False
    return fuzz.ratio(na, nb) >= 92


def label_account(res: Resolution) -> dict:
    """Return {'label': prospect|expansion|possible_expansion, 'evidence': [...]}."""
    data = json.loads((config.REFERENCES / "flowcode_customers.json").read_text())
    evidence: list[str] = []

    direct_names = [res.official_name] + res.sub_brands
    for name in direct_names:
        for cust, source in data["customers"]:
            if _matches(name, cust):
                evidence.append(f"'{name}' matches Flowcode customer '{cust}' ({source})")
    if evidence:
        return {"label": "expansion", "evidence": evidence}

    for name in filter(None, [res.parent_company, res.official_name]):
        for rel, note in data["related"]:
            if _matches(name, rel):
                evidence.append(f"'{name}' matches '{rel}' ({note})")
        for cust, source in data["customers"]:
            if _matches(name, cust):
                evidence.append(f"parent '{name}' matches customer '{cust}' ({source})")
    if evidence:
        return {"label": "possible_expansion", "evidence": evidence}
    return {"label": "prospect", "evidence": ["No match in Flowcode's public customer list (checked 2026-11-18)."]}
