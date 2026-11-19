"""Single place for models, caps, prices and paths. Change a stage's model here."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCES = REPO_ROOT / "references"
DATA = REPO_ROOT / "data"
WEB_DATA = REPO_ROOT / "web" / "data" / "briefs"  # the web page reads briefs from here at build time

# --- Models per stage -------------------------------------------------------
# Verification is done in code, so the research model doesn't have to be the
# strongest: a bad quote is dropped, not shipped. Ranking is the judgment step.
# Change any stage here, e.g. research -> "claude-haiku-5-5" to cut cost.
MODELS = {
    "resolve": "claude-sonnet-5-5",
    "sweep": "claude-sonnet-5-5",
    "research": "claude-sonnet-5-5",
    "extract": "claude-sonnet-5-5",
    "rank": "claude-opus-5-5",
}
EFFORT = {"resolve": "low", "sweep": "low", "research": "low", "extract": "low", "rank": "high"}

# Server-side refusal fallback (beta). Haiku 5.5 has none, so it is skipped there.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}

# Web tool versions. The dynamic-filtering versions (_20260209) are listed for
# Sonnet/Opus; Haiku uses the basic versions.
WEB_TOOL_VERSIONS = {
    "claude-haiku-5-5": ("web_search_20250305", "web_fetch_20250910"),
    "claude-sonnet-5-5": ("web_search_20260209", "web_fetch_20260209"),
    "claude-opus-5-5": ("web_search_20260209", "web_fetch_20260209"),
}
# Measured on the first Hershey run (2026-11-18): with dynamic filtering, the
# research workers used up their search budget without getting readable results
# and never fetched a page. The basic versions put results straight into context.
BASIC_WEB_TOOLS = ("web_search_20250305", "web_fetch_20250910")
DYNAMIC_FILTERING = {"resolve": False, "sweep": False, "research": False}

# --- Research caps ----------------------------------------------------------
CHANNELS = [
    "tv_broadcast",
    "social_digital",
    "email_loyalty",
    "events",
    "packaging",
    "retail",
    "company_wide",
]
# Search budget follows where Flowcode's proof is strongest (see capabilities.json case studies):
# packaging, TV and events have the most wins, so they get the most searching.
SEARCHES_BY_CHANNEL = {
    "packaging": 4, "tv_broadcast": 4, "events": 4, "retail": 3,
    "company_wide": 2, "social_digital": 2, "email_loyalty": 2,
}
FETCHES_PER_WORKER = 3
SWEEP_SEARCHES = 3
SWEEP_FETCHES = 2
FETCH_MAX_CONTENT_TOKENS = 5000
RESEARCH_CONCURRENCY = 4
MAX_PAUSE_CONTINUATIONS = 3

# --- Verification -----------------------------------------------------------
FRESHNESS_DAYS = 90
QUOTE_MATCH_THRESHOLD = 90  # rapidfuzz partial_ratio, 0-100
FETCH_TIMEOUT_S = 15.0
BLOCKED_SOURCE_DOMAINS = (
    "instagram.com", "tiktok.com", "facebook.com", "x.com", "twitter.com", "linkedin.com",
)

# --- Prices (USD per 1M tokens), from the Claude API reference, 2026-11 ---------
# cache_read / cache_write are multipliers on the input price.
PRICES = {
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "in_long": 0.50, "out_long": 2.50, "long_over": 100_000},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read_abs": 0.10},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read_abs": 0.20},
}
CACHE_READ_MULT = 0.10
CACHE_WRITE_MULT = 1.25
WEB_SEARCH_USD = 0.01  # $10 per 1,000 searches; web fetch has no extra fee

# --- Safety ---------------------------------------------------------------
RUN_CAP_USD = 3.00  # abort a single run past this (guards against runaway loops)
