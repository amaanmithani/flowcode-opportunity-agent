"""Render the final brief as Markdown for the README sample and for reps who want text."""

from __future__ import annotations

from typing import Any

STRONG_SCORE = 30  # keep in sync with web/app/[slug]/page.tsx

DROP_LABELS = {
    "quote_not_found": "quote not on page", "stale": "older than 90 days", "fetch_failed": "site blocked our fetch",
    "blocked_domain": "social platform", "duplicate": "duplicate", "quote_too_short": "quote too short",
}

LABELS = {"prospect": "Prospect", "expansion": "Existing customer (expansion)", "possible_expansion": "Possible expansion"}


def to_markdown(b: dict[str, Any]) -> str:
    st = b["stats"]
    lines = [
        f"# {b['resolution']['official_name']}: Flowcode opportunity brief",
        "",
        f"_{b['resolution']['one_liner']}_",
        "",
        f"**Account:** {LABELS.get(b['account']['label'], b['account']['label'])}  ",
        f"**Generated:** {b['generated_at']} · run `{b['run_id']}`",
        "",
        f"**{st['signals_found']} found · {st['signals_verified']} verified · {st['signals_dropped']} dropped · "
        f"${st.get('total_cost_usd', st['cost_usd']):.2f} total · {st.get('total_web_searches', st['web_searches'])} searches**"
        + (f" (last refresh ${st['run_cost_usd']:.2f}, reused: {', '.join(st['reused_stages'])})" if st.get("reused_stages") else ""),
        "",
    ]
    if st.get("drop_reasons"):
        lines += ["Dropped because: " + ", ".join(f"{DROP_LABELS.get(k, k)} ({v})" for k, v in st["drop_reasons"].items()), ""]

    strong = [o for o in b["opportunities"] if o["score"] >= STRONG_SCORE]
    watch = [o for o in b["opportunities"] if o["score"] < STRONG_SCORE]
    lines += [f"## {len(strong)} worth chasing now", ""]
    for o in strong:
        tag = " · new" if o.get("status") == "new" else ""
        cs = o["case_study"]
        lines += [
            f"### {o['rank']}. {o['title']} (score {o['score']}){tag}",
            "",
            f"- **Happening:** {o['what_is_happening']}",
            f"- **Why Flowcode:** {o['why_flowcode']} ({', '.join(p['name'] for p in o['products'])})",
            f"- **Proof:** [{cs['brand']}]({cs['url']}): {cs['metrics'][0]}",
            f"- **First step:** {o['first_step']}",
            "",
            "<details><summary>Details</summary>",
            "",
            f"- **The play:** {o['suggested_play']}",
            f"- **Contact:** {', '.join(o['contact_roles'])}",
            f"- **Score:** confidence {o['confidence']} ({o['confidence_why']}) × size {o['size']} ({o['size_why']}) "
            f"× timing {o['timing']} ({o['timing_why']})",
        ]
        for a in o.get("adjustments", []):
            lines.append(f"- Adjusted: {a}")
        for sig in o["signals"]:
            lines.append(f"- [{sig['effective_date'] or 'undated'}] \"{sig['quote']}\" ([source]({sig['url']}))")
        lines += ["", "</details>", ""]

    if watch:
        lines += ["## Also worth watching", ""]
        lines += [f"- **{o['title']}** (score {o['score']}): {o['timing_why']}" for o in watch]
        lines.append("")

    if b.get("expired_opportunities"):
        lines += ["## No longer active since last run", ""]
        lines += [f"- {e['title']} ({e['play_id']})" for e in b["expired_opportunities"]]
        lines.append("")
    return "\n".join(lines)
