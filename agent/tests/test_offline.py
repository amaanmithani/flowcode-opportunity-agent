"""Offline tests: no API key, no network. They cover the code that decides what ships."""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

import httpx

from opportunity_agent import config
from opportunity_agent.llm import usage_cost
from opportunity_agent.models import ExtractedSignal, Resolution
from opportunity_agent.rank import CASES, PLAYS, PRODUCTS, final_score
from opportunity_agent.resolve import label_account
from opportunity_agent.store import diff_opportunities
from opportunity_agent.verify import normalize_url, parse_date, quote_score, verify_signals

TODAY = dt.date(2026, 11, 18)

PAGE = """<html><head><meta property="article:published_time" content="2026-11-05T09:00:00Z"></head>
<body><nav>menu</nav><p>The Hershey Company today unveiled its festive lineup for the 2026 holiday season,
including KIT KAT® Santa and REESE’S Reindeer Mix, available at retailers nationwide starting this week.</p>
<p>""" + ("Filler text about the company. " * 30) + "</p></body></html>"

OLD_PAGE = PAGE.replace("2026-11-05", "2025-06-01")


def _sig(**kw) -> ExtractedSignal:
    base = dict(
        claim="Hershey launched holiday packaging.", url="https://example.com/news/holiday",
        quote="unveiled its festive lineup for the 2026 holiday season, including KIT KAT Santa and REESE'S Reindeer Mix",
        published_date="2026-11-05", channel="packaging", touchpoint="holiday packaging",
        source_type="brand_owned", uses_qr_or_links=False,
    )
    base.update(kw)
    return ExtractedSignal(**base)


def _transport(routes: dict[str, tuple[int, str]]):
    def handler(req: httpx.Request) -> httpx.Response:
        status, body = routes.get(str(req.url), (404, "not found"))
        return httpx.Response(status, text=body, headers={"content-type": "text/html"})
    return httpx.MockTransport(handler)


def _verify(sigs, routes, snapshots=None):
    return asyncio.run(verify_signals(sigs, snapshots or {}, TODAY, transport=_transport(routes)))


# --- verification ----------------------------------------------------------------
def test_quote_normalization_handles_curly_quotes_and_symbols():
    assert quote_score("REESE'S Reindeer Mix", "REESE’S® Reindeer   Mix") == 100


def test_verified_signal_passes_all_checks():
    [s] = _verify([_sig()], {"https://example.com/news/holiday": (200, PAGE)})
    assert s.verified, s.checks
    assert s.page_date == "2026-11-05" and s.verified_via == "live_fetch"


def test_fabricated_quote_is_dropped():
    [s] = _verify([_sig(quote="Hershey will put QR codes on every bar sold in America next spring for sure")],
                  {"https://example.com/news/holiday": (200, PAGE)})
    assert not s.verified and s.drop_reason == "quote_not_found"


def test_stale_page_is_dropped_even_if_model_claims_recent_date():
    [s] = _verify([_sig()], {"https://example.com/news/holiday": (200, OLD_PAGE)})
    assert not s.verified and s.drop_reason == "stale"


def test_blocked_fetch_falls_back_to_tool_snapshot():
    [s] = _verify([_sig()], {"https://example.com/news/holiday": (403, "denied")},
                  snapshots={"https://www.example.com/news/holiday/": PAGE})
    assert s.verified and s.verified_via == "tool_fetch_snapshot"


def test_unreachable_page_without_snapshot_is_dropped():
    [s] = _verify([_sig()], {})
    assert not s.verified and s.drop_reason.startswith("fetch_failed")


def test_social_sources_are_rejected():
    [s] = _verify([_sig(url="https://www.tiktok.com/@hersheys/video/1")], {})
    assert not s.verified and s.drop_reason == "blocked_domain"


def test_duplicates_are_dropped():
    a, b = _verify([_sig(), _sig(claim="Same thing again")], {"https://example.com/news/holiday": (200, PAGE)})
    assert a.verified and not b.verified and b.drop_reason == "duplicate"


def test_url_normalization_strips_tracking():
    assert normalize_url("http://www.x.com/a/?utm_source=t&id=3#top") == normalize_url("https://x.com/a?id=3")


def test_parse_date_formats():
    assert parse_date("November 5, 2026") == dt.date(2026, 11, 5)
    assert parse_date("2026-11-05T09:00:00Z") == dt.date(2026, 11, 5)
    assert parse_date("unknown") is None


# --- account labelling ---------------------------------------------------------
def _res(name, parent=None, subs=()):
    return Resolution(official_name=name, domain="x.com", newsroom_url=None, parent_company=parent,
                      category="cpg", sub_brands=list(subs), one_liner="")


def test_customer_brand_is_expansion():
    assert label_account(_res("Kraft Heinz", subs=["Lunchables", "Oscar Mayer"]))["label"] == "expansion"


def test_parent_of_customer_is_possible_expansion():
    assert label_account(_res("PepsiCo", subs=["Gatorade"]))["label"] == "possible_expansion"


def test_hershey_is_prospect():
    out = label_account(_res("The Hershey Company", subs=["Hershey's", "Reese's", "Kit Kat", "Ice Breakers"]))
    assert out["label"] == "prospect", out


def test_short_names_do_not_fuzzy_match():
    assert label_account(_res("AMCO Foods", subs=["NFLX Snacks"]))["label"] == "prospect"


# --- ranking, scoring and capabilities -------------------------------------------
def test_score_formula():
    assert final_score(5, 5, 5) == 100 and final_score(4, 5, 3) == 48


def test_capability_sheet_references_are_consistent():
    for p in PLAYS.values():
        assert all(x in PRODUCTS for x in p["products"]), p["id"]
        assert all(x in CASES for x in p["case_studies"]), p["id"]
    for c in CASES.values():
        assert c["url"].startswith("https://www.flowcode.com/case-study/")
        assert c["metrics"], c["id"]


# --- change tracking ---------------------------------------------------------------
def test_diff_marks_new_continuing_expired():
    prev = {"generated_at": "2026-11-01", "opportunities": [
        {"title": "Old pack", "play_id": "on_pack_crm", "signals": [{"url_hash": "a"}]},
        {"title": "Gone", "play_id": "event_capture", "signals": [{"url_hash": "z"}]},
    ]}
    now = [
        {"title": "Pack", "play_id": "on_pack_crm", "signals": [{"url_hash": "a"}, {"url_hash": "b"}]},
        {"title": "TV", "play_id": "tv_scan_to_act", "signals": [{"url_hash": "c"}]},
    ]
    expired = diff_opportunities(prev, now)
    assert [o["status"] for o in now] == ["continuing", "new"]
    assert [e["title"] for e in expired] == ["Gone"]


# --- cost accounting ---------------------------------------------------------------
def test_usage_cost_includes_search_fee_and_cache():
    u = SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000, cache_read_input_tokens=0,
                        cache_creation_input_tokens=0,
                        server_tool_use=SimpleNamespace(web_search_requests=3, web_fetch_requests=2))
    # Sonnet 5.5: $2 in + $1 out + 3 searches x $0.01
    assert abs(usage_cost("claude-sonnet-5-5", u) - 3.03) < 1e-9


def test_models_are_configured_for_every_stage():
    assert set(config.MODELS) == {"resolve", "sweep", "research", "extract", "rank"}
    for m in config.MODELS.values():
        assert m in config.PRICES and m in config.WEB_TOOL_VERSIONS


def test_carry_over_remembers_signals_missed_by_later_research(tmp_path, monkeypatch):
    from opportunity_agent.store import mark_signals, remembered_signals
    monkeypatch.setattr(config, "DATA", tmp_path)
    [s] = _verify([_sig()], {"https://example.com/news/holiday": (200, PAGE)})
    mark_signals("brand", [s], "2026-11-01")
    # A later run did not find it again: it comes back for re-verification with its first_seen date.
    [(again, first_seen)] = remembered_signals("brand", exclude_ids=set())
    assert again.quote == s.quote and first_seen == "2026-11-01"
    assert remembered_signals("brand", exclude_ids={s.id}) == []
    # Re-verification is real: if the page goes stale, the carried signal is dropped.
    [stale] = _verify([again], {"https://example.com/news/holiday": (200, OLD_PAGE)})
    assert not stale.verified and stale.drop_reason == "stale"


def test_regrouped_opportunity_is_not_expired():
    prev = {"generated_at": "2026-11-01", "opportunities": [
        {"title": "Social", "play_id": "social_links", "signals": [{"url_hash": "k"}]},
        {"title": "Truly gone", "play_id": "event_capture", "signals": [{"url_hash": "z"}]},
    ]}
    now = [{"title": "TV + social", "play_id": "tv_scan_to_act", "signals": [{"url_hash": "t"}, {"url_hash": "k"}]}]
    expired = diff_opportunities(prev, now, live_url_hashes={"t", "k"})
    assert [e["title"] for e in expired] == ["Truly gone"]
