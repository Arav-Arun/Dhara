"""The one place that talks to the LLM: structured-JSON calls with retries and a cost log.

Every call appends a line to `data/processed/llm_usage.jsonl` (tokens, cost estimate,
purpose), so the $20 budget is visible at all times (`dhara llm-usage`).
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from openai import OpenAI

from dhara.config import settings

# USD per 1M tokens for gpt-6-luna as reported publicly; only used for the running estimate
PRICE_IN, PRICE_OUT = 0.10, 0.50
# calls a visitor can trigger; benchmark building and evaluation are not counted against the daily cap
PUBLIC = {"answer", "agent:followup", "agent:rewrite", "brief", "ask"}
_client: OpenAI | None = None
log = logging.getLogger(__name__)


def client() -> OpenAI:
    global _client
    if _client is None:
        key = settings.openai_api_key
        assert key is not None, "OPENAI_API_KEY missing in .env"
        _client = OpenAI(api_key=key.get_secret_value())
    return _client


def json_call(
    system: str,
    user: str,
    schema: dict[str, Any],
    purpose: str,
    max_tokens: int = 1500,
    on_text: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Chat completion constrained to a JSON schema; returns the parsed object, or {} after 4 tries.

    Empty or cut-off output (the model can spend its budget thinking) is retried with more room.
    With `on_text` the reply is streamed, and the JSON written so far is passed on after every chunk.
    """
    budget = max_tokens
    api = client()  # a missing key fails here, at once, rather than as four silent retries
    for attempt in range(4):
        try:
            request: dict[str, Any] = {
                "model": settings.dhara_llm_model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "out", "schema": schema, "strict": True},
                },
                "max_completion_tokens": budget,
            }
            if on_text:
                text, usage = "", None
                for chunk in api.chat.completions.create(
                    **request, stream=True, stream_options={"include_usage": True}
                ):
                    usage = chunk.usage or usage
                    if chunk.choices and chunk.choices[0].delta.content:
                        text += chunk.choices[0].delta.content
                        on_text(text)
            else:
                r = api.chat.completions.create(**request)
                text, usage = r.choices[0].message.content or "", r.usage
            _log(purpose, usage.prompt_tokens if usage else 0, usage.completion_tokens if usage else 0)
            out = json.loads(text or "{}")
            if all(k in out for k in schema.get("required", [])):
                return dict(out)
        except json.JSONDecodeError:
            pass
        except Exception as e:  # network, rate limit, server: wait and retry; logged so it isn't invisible
            log.warning("model call for %s failed (attempt %d): %s", purpose, attempt + 1, e)
            time.sleep(2**attempt)
        budget *= 2
    return {}


def _log(purpose: str, tokens_in: int, tokens_out: int) -> None:
    cost = tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT
    line = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "purpose": purpose,
        "in": tokens_in,
        "out": tokens_out,
        "usd": round(cost, 6),
    }
    with (settings.processed_dir / "llm_usage.jsonl").open("a") as f:
        f.write(json.dumps(line) + "\n")


def spent_today() -> float:
    """What the public site has spent on the model since midnight (local time)."""
    path = settings.processed_dir / "llm_usage.jsonl"
    if not path.exists():
        return 0.0
    today = datetime.now().date().isoformat()
    rows = (json.loads(x) for x in path.read_text().splitlines())
    return float(sum(r["usd"] for r in rows if r["ts"].startswith(today) and r["purpose"] in PUBLIC))


def usage() -> dict[str, float]:
    path = settings.processed_dir / "llm_usage.jsonl"
    if not path.exists():
        return {"calls": 0, "usd": 0.0}
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    return {
        "calls": len(rows),
        "tokens_in": sum(r["in"] for r in rows),
        "tokens_out": sum(r["out"] for r in rows),
        "usd": round(sum(r["usd"] for r in rows), 4),
    }
