"""Thin wrapper around the Anthropic SDK: cost accounting, run log, pause_turn, refusals."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from . import config


class RunCapExceeded(RuntimeError):
    pass


class Refused(RuntimeError):
    pass


def usage_cost(model: str, usage: Any) -> float:
    """USD cost of one response from its usage block."""
    p = config.PRICES[model]
    uncached = usage.input_tokens or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    out = usage.output_tokens or 0
    prompt_total = uncached + cache_read + cache_write

    p_in, p_out = p["in"], p["out"]
    if "long_over" in p and prompt_total > p["long_over"]:  # Haiku's long-prompt rate card
        p_in, p_out = p["in_long"], p["out_long"]
    read_price = p.get("cache_read_abs", p_in * config.CACHE_READ_MULT)

    tokens_usd = (
        uncached * p_in + cache_write * p_in * config.CACHE_WRITE_MULT
        + cache_read * read_price + out * p_out
    ) / 1_000_000
    return tokens_usd + server_tool_counts(usage)[0] * config.WEB_SEARCH_USD


def server_tool_counts(usage: Any) -> tuple[int, int]:
    stu = getattr(usage, "server_tool_use", None)
    if not stu:
        return 0, 0
    return (getattr(stu, "web_search_requests", 0) or 0, getattr(stu, "web_fetch_requests", 0) or 0)


@dataclass
class RunLog:
    """Writes one JSON line per event and keeps running totals for the header strip."""

    path: Path
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    searches: int = 0
    fetches: int = 0
    calls: int = 0
    started: float = field(default_factory=time.monotonic)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, **fields: Any) -> None:
        fields.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        line = json.dumps(fields, default=str)
        with self.path.open("a") as f:
            f.write(line + "\n")
        if os.environ.get("OA_PROGRESS"):  # live progress for the web page's "Research a brand" box
            print("PROGRESS " + line, file=sys.stderr, flush=True)

    def totals(self) -> dict[str, Any]:
        return {
            "cost_usd": round(self.cost_usd, 4),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cache_read_tokens": self.cache_read,
            "web_searches": self.searches,
            "web_fetches": self.fetches,
            "llm_calls": self.calls,
            "elapsed_s": round(time.monotonic() - self.started, 1),
        }


class LLM:
    def __init__(self, log: RunLog):
        self.client = anthropic.AsyncAnthropic(max_retries=3)
        self.log = log

    async def call(
        self,
        *,
        stage: str,
        label: str,
        system: str | list[dict],
        user: str,
        tools: list[dict] | None = None,
        output_format: type | None = None,
        max_tokens: int = 16000,
    ):
        """One logical call. Resumes pause_turn and returns the final message.

        Each response is billed into the run log. The run stops if it crosses RUN_CAP_USD.
        """
        model = config.MODELS[stage]
        if self.log.cost_usd >= config.RUN_CAP_USD:
            raise RunCapExceeded(f"run cost ${self.log.cost_usd:.2f} >= cap ${config.RUN_CAP_USD}")

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "output_config": {"effort": config.EFFORT[stage]},
        }
        if model in config.FALLBACK_MODELS:
            kwargs["betas"] = [config.FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        if tools:
            kwargs["tools"] = tools

        messages: list[dict] = [{"role": "user", "content": user}]
        all_content: list[Any] = []
        t0 = time.monotonic()

        for attempt in range(config.MAX_PAUSE_CONTINUATIONS + 1):
            if output_format is not None:
                resp = await self.client.beta.messages.parse(
                    messages=messages, output_format=output_format, **kwargs
                )
            else:
                resp = await self.client.beta.messages.create(messages=messages, **kwargs)
            await self._bill(stage, label, model, resp, time.monotonic() - t0, attempt)
            all_content.extend(resp.content)

            if resp.stop_reason == "refusal":
                cat = getattr(resp.stop_details, "category", None) if resp.stop_details else None
                raise Refused(f"{stage}/{label} refused (category={cat})")
            if resp.stop_reason != "pause_turn":
                break
            # Server tool loop hit its iteration limit: resend so it resumes. No extra user text.
            messages = [messages[0], {"role": "assistant", "content": resp.content}]
        resp._all_content = all_content  # every block across continuations
        return resp

    async def _bill(self, stage: str, label: str, model: str, resp: Any, latency: float, attempt: int) -> None:
        u = resp.usage
        cost = usage_cost(model, u)
        searches, fetches = server_tool_counts(u)
        async with self.log._lock:
            self.log.cost_usd += cost
            self.log.tokens_in += (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
            self.log.tokens_out += u.output_tokens or 0
            self.log.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
            self.log.searches += searches
            self.log.fetches += fetches
            self.log.calls += 1
        self.log.event(
            type="llm_call", stage=stage, label=label, model=resp.model, attempt=attempt,
            stop_reason=resp.stop_reason, input_tokens=u.input_tokens,
            cache_read=getattr(u, "cache_read_input_tokens", 0),
            cache_write=getattr(u, "cache_creation_input_tokens", 0),
            output_tokens=u.output_tokens, searches=searches, fetches=fetches,
            cost_usd=round(cost, 5), latency_s=round(latency, 2), request_id=resp._request_id,
        )


def web_tools(stage: str, *, searches: int, fetches: int) -> list[dict]:
    if config.DYNAMIC_FILTERING.get(stage, True):
        search_type, fetch_type = config.WEB_TOOL_VERSIONS[config.MODELS[stage]]
    else:
        search_type, fetch_type = config.BASIC_WEB_TOOLS
    tools = [{"type": search_type, "name": "web_search", "max_uses": searches}]
    if fetches:
        tools.append({
            "type": fetch_type, "name": "web_fetch", "max_uses": fetches,
            "max_content_tokens": config.FETCH_MAX_CONTENT_TOKENS,
        })
    return tools


def text_of(resp: Any) -> str:
    blocks = getattr(resp, "_all_content", resp.content)
    return "\n".join(b.text for b in blocks if getattr(b, "type", "") == "text").strip()
