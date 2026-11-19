"""Flowcode Opportunity Agent."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    from .pipeline import STAGES, run_batch, run_company

    ap = argparse.ArgumentParser(prog="opportunity-agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="research one company")
    r.add_argument("company")
    r.add_argument("--from-stage", choices=STAGES, default="resolve",
                   help="reuse earlier stages from the latest run (no repeat spend)")
    r.add_argument("--reuse", type=Path, help="run directory to reuse (default: latest)")

    b = sub.add_parser("batch", help="research many companies from a CSV (column: company)")
    b.add_argument("csv", type=Path)
    b.add_argument("--concurrency", type=int, default=3)

    args = ap.parse_args()
    if args.cmd == "run":
        brief = asyncio.run(run_company(args.company, from_stage=args.from_stage, reuse=args.reuse))
        st = brief["stats"]
        print(f"\n{brief['resolution']['official_name']} [{brief['account']['label']}]")
        print(f"{st['signals_found']} found · {st['signals_verified']} verified · {st['signals_dropped']} dropped "
              f"· ${st['cost_usd']:.2f} · {st['elapsed_s']:.0f}s · {st['web_searches']} searches")
        if st["drop_reasons"]:
            print("dropped:", st["drop_reasons"])
        for o in brief["opportunities"]:
            print(f"  {o['rank']}. [{o['score']:>3}] {o['title']}  ({o['status']})")
        print(f"\nbrief: data/briefs/{brief['slug']}.md")
    else:
        with args.csv.open() as f:
            companies = [row["company"] for row in csv.DictReader(f) if row.get("company")]
        results = asyncio.run(run_batch(companies, args.concurrency))
        json.dump(results, sys.stdout, indent=2)
        print()
