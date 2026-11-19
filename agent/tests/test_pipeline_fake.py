"""End-to-end pipeline run with a fake LLM and fake web pages. No API spend, no network."""

from __future__ import annotations

import asyncio
import functools
import json
from types import SimpleNamespace

import httpx
import pytest

from opportunity_agent import config, pipeline
from opportunity_agent.models import ExtractedSignals, Resolution
from opportunity_agent.rank import RankedOpportunity, RankOutput

URL = "https://news.example.com/2026/11/05/holiday"
URL2 = "https://news.example.com/2026/11/10/tv"
PAGE = ("<html><body><p>The Hershey Company unveiled its festive lineup for the 2026 holiday season "
        "including KIT KAT Santa and REESE'S Reindeer Mix at retailers nationwide.</p>"
        "<p>A new national TV spot featuring the Grinch begins airing this week across major networks.</p>"
        + "<p>filler words here</p>" * 40 + "</body></html>")
Q1 = "unveiled its festive lineup for the 2026 holiday season including KIT KAT Santa and REESE'S Reindeer Mix"
Q2 = "A new national TV spot featuring the Grinch begins airing this week across major networks"


class Block:
    def __init__(self, **d):
        self.__dict__.update(d)

    def to_dict(self):
        return dict(self.__dict__)


def fake_resp(text="", parsed=None):
    usage = SimpleNamespace(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0,
                            server_tool_use=SimpleNamespace(web_search_requests=1, web_fetch_requests=0))
    content = [Block(type="text", text=text, citations=None)]
    r = SimpleNamespace(content=content, usage=usage, stop_reason="end_turn", model="fake",
                        _request_id="req_fake", parsed_output=parsed, stop_details=None)
    r._all_content = content
    return r


def make_fake_call(rank_ids: list[list[str]]):
    calls = {"rank": 0}

    async def fake_call(self, *, stage, label, system, user, tools=None, output_format=None, max_tokens=0):
        await self._bill(stage, label, config.MODELS[stage], fake_resp(), 0.1, 0)
        if stage == "resolve" and label == "lookup":
            return fake_resp("Hershey notes")
        if stage == "resolve":
            return fake_resp(parsed=Resolution(
                official_name="The Hershey Company", domain="thehersheycompany.com",
                newsroom_url="https://www.thehersheycompany.com/en_us/home/newsroom.html",
                parent_company=None, category="confectionery", sub_brands=["Reese's", "Kit Kat"], one_liner="Candy maker"))
        if stage == "sweep":
            return fake_resp("2026-11-05 | Holiday lineup | " + URL)
        if stage == "research":
            return fake_resp(f"FINDING for {label}")
        if stage == "extract":
            return fake_resp(parsed=ExtractedSignals(signals=[
                dict(claim="Holiday lineup", url=URL, quote=Q1, published_date="2026-11-05", channel="packaging",
                     touchpoint="holiday packs", source_type="brand_owned", uses_qr_or_links=False),
                dict(claim="Grinch TV spot", url=URL2, quote=Q2, published_date="2026-11-10", channel="tv_broadcast",
                     touchpoint="national TV", source_type="trade_press", uses_qr_or_links=False),
                dict(claim="Made up", url=URL, quote="Hershey will print QR codes on every single bar sold next year",
                     published_date="2026-11-05", channel="packaging", touchpoint="x",
                     source_type="news", uses_qr_or_links=True),
            ]))
        if stage == "rank":
            ids = rank_ids[min(calls["rank"], len(rank_ids) - 1)]
            calls["rank"] += 1
            opps = [RankedOpportunity(
                title=f"Opp {i}", what_is_happening="x", why_flowcode="y", play_id=play, product_ids=["flowcodes"],
                case_study_id="love_corn", signal_ids=sids, confidence=5, confidence_why="a", size=5, size_why="b",
                timing=4, timing_why="c", suggested_play="d", contact_roles=["Brand Manager"], first_step="e",
            ) for i, (play, sids) in enumerate(ids)]
            return fake_resp(parsed=RankOutput(opportunities=opps, skipped_signal_ids=[]))
        raise AssertionError(stage)

    return fake_call


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-real")
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "WEB_DATA", tmp_path / "web" / "data" / "briefs")
    routes = {URL: PAGE, URL2: PAGE}
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200 if str(req.url) in routes else 404, text=routes.get(str(req.url), ""), headers={"content-type": "text/html"}))
    monkeypatch.setattr(pipeline, "verify_signals",
                        functools.partial(pipeline.verify_signals, transport=transport))
    return tmp_path


def _ids(tmp):
    signals = json.loads(next((tmp / "runs").rglob("verify.json")).read_text())
    return {s["claim"]: s["id"] for s in signals}


def test_full_run_then_cached_rerun(sandbox, monkeypatch):
    from opportunity_agent import llm as llm_mod

    # First pass to learn the deterministic signal ids
    monkeypatch.setattr(llm_mod.LLM, "call", make_fake_call([[]]))
    asyncio.run(pipeline.run_company("Hershey"))
    ids = _ids(sandbox)

    plan = [
        [("on_pack_crm", [ids["Holiday lineup"]]),
         ("tv_scan_to_act", [ids["Grinch TV spot"]]),
         ("event_capture", ["deadbeef00"])],          # cites an unknown signal -> must be rejected
    ]
    monkeypatch.setattr(llm_mod.LLM, "call", make_fake_call(plan))
    brief = asyncio.run(pipeline.run_company("Hershey", from_stage="verify"))

    st = brief["stats"]
    assert st["signals_found"] == 3 and st["signals_verified"] == 2 and st["signals_dropped"] == 1
    assert st["drop_reasons"] == {"quote_not_found": 1}
    assert st["reused_stages"] == ["resolve", "research", "extract"]
    assert [o["play_id"] for o in brief["opportunities"]] == ["on_pack_crm", "tv_scan_to_act"]
    assert brief["rejected_opportunities"][0]["reason"].startswith("no verified signals")
    # Single trade-press signal cannot be confidence 5; brand-owned can.
    tv = next(o for o in brief["opportunities"] if o["play_id"] == "tv_scan_to_act")
    pack = next(o for o in brief["opportunities"] if o["play_id"] == "on_pack_crm")
    assert tv["confidence"] == 4 and pack["confidence"] == 5
    assert pack["score"] == 80 and tv["score"] == 64
    assert pack["signals"][0]["quote"] == Q1
    assert (sandbox / "briefs" / "hershey.md").read_text().startswith("# The Hershey Company")
    # The first run produced no opportunities, so both count as new on this run.
    assert all(o["status"] == "new" for o in brief["opportunities"])

    # Third run (rank only): the same opportunities now show as continuing.
    monkeypatch.setattr(llm_mod.LLM, "call", make_fake_call([plan[0][:1]]))
    brief3 = asyncio.run(pipeline.run_company("Hershey", from_stage="rank"))
    assert brief3["opportunities"][0]["status"] == "continuing"
    # The TV opportunity was not re-ranked, but its signal is still verified, so it is not "expired".
    assert brief3["expired_opportunities"] == []
