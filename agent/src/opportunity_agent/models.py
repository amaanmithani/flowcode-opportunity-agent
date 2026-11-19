"""Typed data that flows between stages."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Channel = Literal[
    "tv_broadcast", "social_digital", "email_loyalty", "events",
    "packaging", "retail", "company_wide",
]
SourceType = Literal["brand_owned", "press_wire", "trade_press", "news", "other"]
Score = Literal[1, 2, 3, 4, 5]


# --- Resolve ----------------------------------------------------------------
class Resolution(BaseModel):
    official_name: str
    domain: str = Field(description="Official website domain, e.g. thehersheycompany.com")
    newsroom_url: Optional[str] = Field(description="Newsroom or press page URL, if found")
    parent_company: Optional[str]
    category: str = Field(description="Short category, e.g. 'confectionery / CPG'")
    sub_brands: list[str] = Field(description="Major consumer brands it owns (max 10)")
    one_liner: str


# --- Extract ----------------------------------------------------------------
class ExtractedSignal(BaseModel):
    claim: str = Field(description="One sentence: what the brand is doing")
    url: str = Field(description="Exact source URL the quote comes from")
    quote: str = Field(description="Verbatim sentence(s) copied from that page, 12-40 words")
    published_date: Optional[str] = Field(description="YYYY-MM-DD if known, else null")
    channel: Channel
    touchpoint: str = Field(description="The physical or digital touchpoint, e.g. 'holiday packaging'")
    source_type: SourceType
    uses_qr_or_links: bool = Field(description="True if the source says the brand already uses QR codes or scannable links here")


class ExtractedSignals(BaseModel):
    signals: list[ExtractedSignal]


# --- Verify -----------------------------------------------------------------
class Signal(ExtractedSignal):
    id: str
    url_hash: str
    verified: bool
    checks: dict[str, str]           # check name -> "pass" / reason
    match_score: float
    verified_via: Optional[str]      # "live_fetch" | "tool_fetch_snapshot"
    page_date: Optional[str]
    effective_date: Optional[str]
    undated: bool
    drop_reason: Optional[str] = None
    first_seen: Optional[str] = None
    is_new: bool = True
    carried_over: bool = False  # found on an earlier run, re-verified on this one


# --- Rank -------------------------------------------------------------------
def make_rank_models(play_ids: list[str], product_ids: list[str], case_ids: list[str]):
    """Build rank output models whose ids are enums taken from capabilities.json.

    Structured outputs then limit the model to ids that really exist.
    """
    PlayId = Literal[tuple(play_ids)]  # type: ignore[valid-type]
    ProductId = Literal[tuple(product_ids)]  # type: ignore[valid-type]
    CaseId = Literal[tuple(case_ids)]  # type: ignore[valid-type]

    class RankedOpportunity(BaseModel):
        title: str = Field(description="4-7 words naming the touchpoint, e.g. 'Grinch holiday packs, 2027 run'. No arrows.")
        what_is_happening: str = Field(description="One sentence, max 25 words, only facts from the cited signals")
        why_flowcode: str = Field(description="One sentence, max 20 words: the gap Flowcode fills. Do not describe the product flow here.")
        play_id: PlayId  # type: ignore[valid-type]
        product_ids: list[ProductId]  # type: ignore[valid-type]
        case_study_id: CaseId  # type: ignore[valid-type]
        signal_ids: list[str] = Field(description="Ids of the verified signals this rests on")
        confidence: Score
        confidence_why: str = Field(description="Max 12 words")
        size: Score
        size_why: str = Field(description="Max 12 words")
        timing: Score
        timing_why: str = Field(description="Max 12 words")
        suggested_play: str = Field(description="Max 35 words: what to put where and what the scan does. Do not repeat the case study or its numbers.")
        contact_roles: list[str] = Field(description="1-3 job titles")
        first_step: str = Field(description="Max 20 words: the single next action for the rep")

    class RankOutput(BaseModel):
        opportunities: list[RankedOpportunity]
        skipped_signal_ids: list[str] = Field(description="Verified signals with no real Flowcode fit")

    return RankedOpportunity, RankOutput
