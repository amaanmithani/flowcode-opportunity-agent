"""Runs the stages for one company and saves each stage's output to disk.

  resolve -> research (x7 channels) -> extract -> verify -> rank -> brief

Every stage writes data/runs/<slug>/<run_id>/<stage>.json. With --from-stage,
a run copies the earlier stages from a previous run and only pays for the rest.
For example, `--from-stage verify` re-verifies and re-ranks without any new
search or research calls.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import config
from .extract import extract
from .llm import LLM, RunLog
from .models import ExtractedSignal, Resolution, Signal
from .rank import rank
from .report import to_markdown
from .research import research_all
from .resolve import label_account, resolve
from .store import diff_opportunities, mark_signals, remembered_signals
from .verify import drop_summary, verify_signals

STAGES = ["resolve", "research", "extract", "verify", "rank"]


def slugify(s: str) -> str:
    s = re.sub(r"^https?://(www\.)?", "", s.strip().lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def latest_run(slug: str) -> Path | None:
    d = config.DATA / "runs" / slug
    runs = sorted(p for p in d.glob("*") if p.is_dir()) if d.exists() else []
    return runs[-1] if runs else None


def _rel(p: Path) -> str:
    """Repo-relative path for logs, so no machine-specific paths are written or published."""
    try:
        return str(p.resolve().relative_to(config.REPO_ROOT))
    except ValueError:
        return str(p)


def _abs(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else config.REPO_ROOT / q


_LLM_STAGE_TO_PIPELINE = {"resolve": "resolve", "sweep": "research", "research": "research",
                          "extract": "extract", "rank": "rank"}


def stage_totals(run_dir: Path) -> dict[str, dict[str, float]]:
    """Cost and searches per pipeline stage for a run.

    For stages the run reused, the numbers come from the run that originally
    paid for them, following the reuse chain back. That way a brief's total
    cost covers every stage, not just the latest refresh.
    """
    totals: dict[str, dict[str, float]] = {}
    reused_from: Path | None = None
    reused_stages: list[str] = []
    log = run_dir / "run_log.jsonl"
    if not log.exists():
        return totals
    for line in log.read_text().splitlines():
        e = json.loads(line)
        if e.get("type") == "reuse":
            reused_from, reused_stages = _abs(e["from_run"]), e["stages"]
        elif e.get("type") == "llm_call":
            st = _LLM_STAGE_TO_PIPELINE.get(e["stage"], e["stage"])
            t = totals.setdefault(st, {"cost_usd": 0.0, "searches": 0, "fetches": 0})
            t["cost_usd"] += e["cost_usd"]
            t["searches"] += e["searches"]
            t["fetches"] += e["fetches"]
    if reused_from and reused_from.exists():
        earlier = stage_totals(reused_from)
        for st in reused_stages:
            if st in earlier:
                totals[st] = earlier[st]
    return totals


def _save(run_dir: Path, name: str, obj: Any) -> None:
    (run_dir / f"{name}.json").write_text(json.dumps(obj, indent=2, default=str))


def _load(run_dir: Path, name: str) -> Any:
    return json.loads((run_dir / f"{name}.json").read_text())


async def run_company(company: str, *, from_stage: str = "resolve", reuse: Path | None = None) -> dict[str, Any]:
    slug = slugify(company)
    start = STAGES.index(from_stage)
    if start > 0:  # find the run to reuse before creating this run's folder
        reuse = reuse or latest_run(slug)
        if reuse is None:
            raise SystemExit(f"--from-stage {from_stage} needs an earlier run for '{slug}'")
    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = config.DATA / "runs" / slug / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(run_dir / "run_log.jsonl")
    llm = LLM(log)
    today = dt.date.today()

    if start > 0:
        for name in STAGES[:start]:
            src = reuse / f"{name}.json"
            if not src.exists():
                raise SystemExit(f"{src} missing; cannot start at {from_stage}")
            shutil.copy(src, run_dir / f"{name}.json")
        log.event(type="reuse", from_run=_rel(reuse), stages=STAGES[:start])

    log.event(type="run_start", company=company, run_id=run_id, models=config.MODELS, from_stage=from_stage)

    # 1. RESOLVE
    if start <= 0:
        res = await resolve(llm, company)
        account = label_account(res)
        _save(run_dir, "resolve", {"resolution": res.model_dump(), "account": account})
    r = _load(run_dir, "resolve")
    res, account = Resolution(**r["resolution"]), r["account"]
    log.event(type="stage_done", stage="resolve", account=account["label"], name=res.official_name)

    # 2. RESEARCH
    if start <= 1:
        results = await research_all(llm, res, today)
        _save(run_dir, "research", results)
    results = _load(run_dir, "research")
    log.event(type="stage_done", stage="research",
              per_channel={x["channel"]: {"notes_chars": len(x["notes"]), "hits": len(x["hits"]),
                                          "docs": len(x["docs"]), "error": x["error"],
                                          "tool_errors": x["tool_errors"]} for x in results})

    # 3. EXTRACT
    if start <= 2:
        extracted = await extract(llm, results)
        _save(run_dir, "extract", [e.model_dump() for e in extracted])
    extracted = [ExtractedSignal(**e) for e in _load(run_dir, "extract")]
    log.event(type="stage_done", stage="extract", signals=len(extracted))

    # 4. VERIFY (plain code)
    if start <= 3:
        snapshots: dict[str, str] = {}
        for x in results:
            for url, txt in x["docs"].items():
                snapshots[url] = txt
            for url, snippets in x["cited"].items():
                snapshots.setdefault(url, " ".join(snippets))
        signals = await verify_signals(extracted, snapshots, today)
        # Re-verify what earlier runs found but this run missed (free: plain code, no LLM).
        current_ids = {s.id for s in signals}
        remembered = remembered_signals(slug, current_ids)
        if remembered:
            carried = await verify_signals([e for e, _ in remembered], snapshots, today)
            for sig, (_, first_seen) in zip(carried, remembered):
                sig.carried_over, sig.first_seen = True, first_seen
            signals += carried
        _save(run_dir, "verify", [s.model_dump() for s in signals])
    signals = [Signal(**s) for s in _load(run_dir, "verify")]
    drops = drop_summary(signals)
    log.event(type="stage_done", stage="verify", found=len(signals),
              verified=sum(s.verified for s in signals), dropped=drops,
              carried_over=sum(s.carried_over for s in signals),
              carried_over_verified=sum(s.carried_over and s.verified for s in signals))

    # 5. RANK
    if start <= 4:
        ranked = await rank(llm, res, account, signals)
        _save(run_dir, "rank", ranked)
    ranked = _load(run_dir, "rank")
    log.event(type="stage_done", stage="rank", opportunities=len(ranked["opportunities"]),
              rejected=ranked["rejected"])

    # 6. BRIEF: join signals onto opportunities, compare with the last brief, write the outputs
    mark_signals(slug, signals, today.isoformat())
    by_id = {s.id: s.model_dump() for s in signals}
    for o in ranked["opportunities"]:
        o["signals"] = [by_id[i] for i in o["signal_ids"]]
    brief_path = config.DATA / "briefs" / f"{slug}.json"
    prev = json.loads(brief_path.read_text()) if brief_path.exists() else None
    live_hashes = {s.url_hash for s in signals if s.verified}
    expired = diff_opportunities(prev, ranked["opportunities"], live_hashes)

    verified = [s for s in signals if s.verified]
    totals = log.totals()
    per_stage = stage_totals(run_dir)
    all_cost = sum(t["cost_usd"] for t in per_stage.values())
    all_searches = int(sum(t["searches"] for t in per_stage.values()))
    brief = {
        "slug": slug, "input": company, "run_id": run_id,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "account": account, "resolution": res.model_dump(),
        "stats": {
            "signals_found": len(signals), "signals_verified": len(verified),
            "signals_dropped": len(signals) - len(verified), "drop_reasons": drops,
            "new_signals": sum(s.is_new for s in verified),
            "carried_over": sum(s.carried_over for s in signals),
            "carried_over_verified": sum(s.carried_over for s in verified),
            "opportunities": len(ranked["opportunities"]),
            "per_channel": {ch: {"found": sum(s.channel == ch for s in signals),
                                 "verified": sum(s.channel == ch and s.verified for s in signals)}
                            for ch in config.CHANNELS},
            **totals,
            # cost_usd / web_searches above = this run only. These cover the whole brief:
            "run_cost_usd": totals["cost_usd"],
            "total_cost_usd": round(all_cost, 4),
            "total_web_searches": all_searches,
            "stage_costs": {k: {**v, "cost_usd": round(v["cost_usd"], 4)} for k, v in per_stage.items()},
            "reused_stages": STAGES[:start],
        },
        "models": config.MODELS,
        "opportunities": ranked["opportunities"],
        "expired_opportunities": expired,
        "skipped_signal_ids": ranked["skipped_signal_ids"],
        "rejected_opportunities": ranked["rejected"],
        "signals": [s.model_dump() for s in signals],
    }
    _save(run_dir, "brief", brief)
    (run_dir / "brief.md").write_text(to_markdown(brief))
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(json.dumps(brief, indent=2, default=str))
    (brief_path.with_suffix(".md")).write_text(to_markdown(brief))
    if config.WEB_DATA.parent.parent.exists():  # web/ is present
        config.WEB_DATA.mkdir(parents=True, exist_ok=True)
        (config.WEB_DATA / f"{slug}.json").write_text(json.dumps(brief, indent=2, default=str))
    log.event(type="run_done", slug=slug, total_cost_usd=round(all_cost, 4), **totals)
    return brief


async def run_batch(companies: list[str], concurrency: int = 3) -> list[dict[str, Any]]:
    """Run many companies with a concurrency limit. One failure does not stop the batch."""
    sem = asyncio.Semaphore(concurrency)

    async def one(c: str):
        async with sem:
            try:
                b = await run_company(c)
                return {"company": c, "ok": True, "opportunities": b["stats"]["opportunities"],
                        "verified": b["stats"]["signals_verified"], "cost_usd": b["stats"]["cost_usd"]}
            except Exception as e:
                return {"company": c, "ok": False, "error": repr(e)}

    return await asyncio.gather(*(one(c) for c in companies))
