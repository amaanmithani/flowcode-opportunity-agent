"""Memory across runs, so a refresh shows only what changed.

- Signals are keyed by id (normalized url + quote). first_seen and last_seen tell "new" from "seen before".
- Opportunities are compared with the previous brief: new / continuing / expired.

This uses JSON files under data/store. In production the same keys become Postgres tables.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from .models import ExtractedSignal, Signal

_EXTRACTED_FIELDS = list(ExtractedSignal.model_fields)


def _store_dir(slug: str) -> Path:
    d = config.DATA / "store" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def mark_signals(slug: str, signals: list[Signal], run_date: str) -> None:
    """Set is_new and first_seen on each verified signal, then update the index on disk."""
    path = _store_dir(slug) / "signals.json"
    index: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}
    for s in signals:
        if not s.verified:
            continue
        prev = index.get(s.id)
        s.is_new = prev is None and not s.carried_over
        s.first_seen = prev["first_seen"] if prev else (s.first_seen or run_date)
        index[s.id] = {
            "first_seen": s.first_seen, "last_seen": run_date,
            "signal": {k: getattr(s, k) for k in _EXTRACTED_FIELDS},
        }
    path.write_text(json.dumps(index, indent=2))


def remembered_signals(slug: str, exclude_ids: set[str]) -> list[tuple[ExtractedSignal, str]]:
    """Signals verified on earlier runs and not found again this run. They are re-verified, not trusted.

    Research is non-deterministic: a worker can miss something it found last time.
    Carrying signals forward means a refresh adds to what we know. An item only
    expires when its page goes stale or its quote disappears.
    """
    path = _store_dir(slug) / "signals.json"
    if not path.exists():
        return []
    out = []
    for sid, entry in json.loads(path.read_text()).items():
        if sid in exclude_ids or "signal" not in entry:
            continue
        out.append((ExtractedSignal(**entry["signal"]), entry["first_seen"]))
    return out


def _key_signals(opp: dict) -> set[str]:
    return {s["url_hash"] for s in opp.get("signals", [])}


def diff_opportunities(prev_brief: dict | None, opps: list[dict[str, Any]],
                       live_url_hashes: set[str] | None = None) -> list[dict]:
    """Set status on each opportunity. Returns previous opportunities that have really expired.

    A previous opportunity whose signals are still verified this run was only
    regrouped or renamed by the ranker, so it does not count as expired.
    It expires only when none of its evidence still passes verification.
    """
    if not prev_brief:
        for o in opps:
            o["status"] = "new"
        return []
    prev = prev_brief.get("opportunities", [])
    matched: set[int] = set()
    for o in opps:
        o["status"] = "new"
        for i, p in enumerate(prev):
            if i in matched:
                continue
            same_play = p.get("play_id") == o["play_id"]
            overlap = _key_signals(p) & _key_signals(o)
            if same_play and overlap:
                o["status"] = "continuing"
                o["first_seen"] = p.get("first_seen", prev_brief.get("generated_at"))
                matched.add(i)
                break
    expired = []
    live = live_url_hashes if live_url_hashes is not None else set().union(*(_key_signals(o) for o in opps))
    for i, p in enumerate(prev):
        if i not in matched and not (_key_signals(p) & live):
            expired.append({"title": p["title"], "play_id": p["play_id"], "last_seen": prev_brief.get("generated_at")})
    return expired
