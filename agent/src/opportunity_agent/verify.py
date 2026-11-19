"""Stage 4: plain-code verification. No LLM. Every signal must pass or it is dropped.

Checks, in order:
  source_allowed  - not a social platform we cannot read
  fetch           - the page loads (our own fetch; falls back to the page text
                    Anthropic's web_fetch tool returned, which is real page data)
  quote_found     - the quote is on the page (normalized exact match, else fuzzy >= threshold)
  fresh           - the page or claimed date is within FRESHNESS_DAYS (undated pages pass, flagged)
  unique          - not a duplicate of an earlier signal (same url + same quote)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import re
import unicodedata
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from . import config
from .models import ExtractedSignal, Signal

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
_TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|ref_src$)")


# --- normalization -----------------------------------------------------------
def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()[:12]


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                                   "–": "-", "—": "-", " ": " ", "…": "..."}))
    s = re.sub(r"[^a-z0-9$%' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_score(quote: str, page_text: str) -> float:
    q, p = normalize_text(quote), normalize_text(page_text)
    if not q or not p:
        return 0.0
    if q in p:
        return 100.0
    return float(fuzz.partial_ratio(q, p))


# --- page fetching and parsing -----------------------------------------------
_DATE_PATTERNS = [
    r'property=["\'](?:article:published_time|og:published_time)["\'][^>]*content=["\']([^"\']+)',
    r'content=["\']([^"\']+)["\'][^>]*property=["\'](?:article:published_time|og:published_time)',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'name=["\'](?:date|pubdate|publish-date|parsely-pub-date|sailthru\.date|dc\.date)["\'][^>]*content=["\']([^"\']+)',
    r'<time[^>]+datetime=["\']([^"\']+)',
]


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return dt.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def page_date(html: str, url: str) -> dt.date | None:
    for pat in _DATE_PATTERNS:
        m = re.search(pat, html, flags=re.I)
        if m and (d := parse_date(m.group(1))):
            return d
    m = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/", url)
    if m:
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    return None


def html_to_text(html: str) -> str:
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, svg"):
        tag.decompose()
    body = tree.body or tree.root
    return body.text(separator=" ") if body else ""


async def fetch_page(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    try:
        r = await client.get(url, follow_redirects=True, timeout=config.FETCH_TIMEOUT_S)
    except httpx.HTTPError as e:
        return {"ok": False, "reason": f"fetch_error:{type(e).__name__}"}
    if r.status_code >= 400:
        return {"ok": False, "reason": f"http_{r.status_code}"}
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        return {"ok": False, "reason": f"non_html:{ctype.split(';')[0]}"}
    html = r.text
    text = html_to_text(html)
    if len(text) < 300:
        return {"ok": False, "reason": "empty_or_js_rendered", "html": html}
    return {"ok": True, "text": text, "date": page_date(html, str(r.url))}


# --- main ----------------------------------------------------------------------
def signal_id(url: str, quote: str) -> str:
    return hashlib.sha1(f"{normalize_url(url)}|{normalize_text(quote)}".encode()).hexdigest()[:10]


async def verify_signals(
    extracted: list[ExtractedSignal],
    snapshots: dict[str, str],
    today: dt.date | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[Signal]:
    """Return every signal with verified True/False and the reason. Callers filter."""
    today = today or dt.date.today()
    cutoff = today - dt.timedelta(days=config.FRESHNESS_DAYS)
    snap_by_norm = {normalize_url(u): t for u, t in snapshots.items()}

    urls = {s.url for s in extracted}
    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept-Language": "en-US"}, transport=transport) as client:
        sem = asyncio.Semaphore(8)

        async def get(u: str):
            if any(d in urlsplit(u).netloc.lower() for d in config.BLOCKED_SOURCE_DOMAINS):
                return u, {"ok": False, "reason": "blocked_domain"}
            async with sem:
                return u, await fetch_page(client, u)

        pages = dict(await asyncio.gather(*(get(u) for u in urls)))

    out: list[Signal] = []
    seen: set[str] = set()
    for s in extracted:
        checks: dict[str, str] = {}
        sid = signal_id(s.url, s.quote)
        page = pages[s.url]
        drop: str | None = None
        via: str | None = None
        text: str | None = None
        pdate: dt.date | None = None

        if page.get("reason") == "blocked_domain":
            checks["source_allowed"] = "social platform, not readable"
            drop = "blocked_domain"
        else:
            checks["source_allowed"] = "pass"
            if page["ok"]:
                text, via, pdate = page["text"], "live_fetch", page["date"]
                checks["fetch"] = "pass"
            elif (snap := snap_by_norm.get(normalize_url(s.url))):
                text, via = snap, "tool_fetch_snapshot"
                checks["fetch"] = f"live fetch failed ({page['reason']}); used web_fetch snapshot"
            else:
                checks["fetch"] = page["reason"]
                drop = f"fetch_failed:{page['reason']}"

        score = 0.0
        if text is not None:
            if len(normalize_text(s.quote).split()) < 6:
                checks["quote_found"] = "quote too short to verify"
                drop = "quote_too_short"
            else:
                score = quote_score(s.quote, text)
                snap = snap_by_norm.get(normalize_url(s.url))
                if score < config.QUOTE_MATCH_THRESHOLD and via == "live_fetch" and snap:
                    # Live HTML may hide JS-rendered text; the tool snapshot is the rendered page.
                    snap_score = quote_score(s.quote, snap)
                    if snap_score > score:
                        score, via = snap_score, "tool_fetch_snapshot"
                if score >= config.QUOTE_MATCH_THRESHOLD:
                    checks["quote_found"] = "pass" if score == 100 else f"pass (fuzzy {score:.0f})"
                else:
                    checks["quote_found"] = f"not on page (best match {score:.0f})"
                    drop = "quote_not_found"

        claimed = parse_date(s.published_date)
        effective = pdate or claimed
        undated = effective is None
        if not drop:
            if undated:
                checks["fresh"] = "no date found; treated as currently live"
            elif effective < cutoff and not (s.channel == "email_loyalty" and s.source_type == "brand_owned"):
                checks["fresh"] = f"stale ({effective.isoformat()})"
                drop = "stale"
            else:
                note = "" if not (pdate and claimed and abs((pdate - claimed).days) > 7) else f" (page date {pdate}, claimed {claimed})"
                checks["fresh"] = f"pass{note}"

        if not drop:
            if sid in seen:
                checks["unique"] = "duplicate"
                drop = "duplicate"
            else:
                checks["unique"] = "pass"
                seen.add(sid)

        out.append(Signal(
            **s.model_dump(), id=sid, url_hash=url_hash(s.url), verified=drop is None,
            checks=checks, match_score=round(score, 1), verified_via=via,
            page_date=pdate.isoformat() if pdate else None,
            effective_date=effective.isoformat() if effective else None,
            undated=undated, drop_reason=drop,
        ))
    return out


def drop_summary(signals: list[Signal]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in signals:
        if not s.verified:
            key = (s.drop_reason or "unknown").split(":")[0]
            counts[key] = counts.get(key, 0) + 1
    return counts


def dumps(signals: list[Signal]) -> str:
    return json.dumps([s.model_dump() for s in signals], indent=2)
