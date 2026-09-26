"""The explain flow: facts from the sport API, headlines from ESPN, then a
cached answer, or one model call (and one retry on the fallback model)
within the daily budget, validated, else the template."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from .cache import Cache
from .facts import Facts, render
from .ledger import Ledger
from .llm import LLMError, complete
from .news import headlines
from .prompts import messages
from .template import explain_from_template
from .validate import validate

logger = logging.getLogger(__name__)

# A template stored because the model was unavailable (budget, outage) is
# served for this long, then the model gets another go at the same facts.
TEMPLATE_RETRY_SECONDS = 3 * 3600
SECTION_KEYS = ("market", "title", "text", "numbers_used")


class NotFound(Exception):
    pass


class Upstream(Exception):
    pass


def _news_terms(f: Facts) -> list[str]:
    if f.sport == "f1":
        return [d["name"] for d in f.drivers[:3] if d.get("name")]
    return [t.strip() for t in re.split(r"\s+(?:at|v|vs\.?|@)\s+", f.title) if t.strip()]


def _clean(body: dict) -> dict:
    return {"headline": body["headline"],
            "sections": [{k: s[k] for k in SECTION_KEYS if k in s} for s in body["sections"]]}


class Explainer:
    def __init__(self, settings, cache: Cache, ledger: Ledger, client: httpx.AsyncClient):
        self.settings, self.cache, self.ledger, self.client = settings, cache, ledger, client
        self._locks: dict[str, asyncio.Lock] = {}

    async def _facts(self, sport: str, id: str) -> Facts:
        base = self.settings.sport_api.get(sport)
        if not base:
            raise NotFound(f"no sport API configured for {sport!r}")
        try:
            res = await self.client.get(f"{base}/facts/{id}", timeout=15.0)
        except httpx.HTTPError as exc:
            raise Upstream(f"{sport} API unreachable: {type(exc).__name__}") from None
        if res.status_code == 404:
            raise NotFound(f"{sport} has no facts for {id!r}")
        if res.status_code != 200:
            raise Upstream(f"{sport} API returned {res.status_code}")
        try:
            return Facts(**res.json())
        except (ValueError, ValidationError, TypeError) as exc:
            raise Upstream(f"{sport} facts failed the contract: {type(exc).__name__}") from None

    def _answer(self, sport: str, id: str, row: dict) -> dict:
        return {"sport": sport, "id": id, **row["body"], "source": row["source"], "model": row["model"],
                "generated_at": row["created_at"], "prompt_version": row["prompt_version"]}

    def _usable(self, row: dict | None) -> bool:
        if row is None:
            return False
        if row["source"] != "template":
            return True
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])).total_seconds()
        return age < TEMPLATE_RETRY_SECONDS

    async def explain(self, sport: str, id: str) -> dict:
        facts = await self._facts(sport, id)
        news = await headlines(self.client, sport, _news_terms(facts))
        facts_json = render(facts)
        news_json = json.dumps(news, sort_keys=True, ensure_ascii=False)
        s = self.settings
        key = Cache.key(sport, id, facts_json, news_json, s.prompt_version, s.model)

        row = self.cache.get(key)
        if self._usable(row):
            return self._answer(sport, id, row)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            row = self.cache.get(key)  # another caller may have just made it
            if self._usable(row):
                return self._answer(sport, id, row)
            body, source, model = await self._generate(sport, facts, facts_json, news_json)
            self.cache.put(key, sport, id, body, source, model, s.prompt_version)
        self._locks.pop(key, None)
        return self._answer(sport, id, self.cache.get(key))

    async def _generate(self, sport: str, facts: Facts, facts_json: str, news_json: str) -> tuple[dict, str, str]:
        s = self.settings
        if s.enabled and s.openrouter_api_key:
            msgs = messages(sport, facts_json, news_json)
            for model in (s.model, s.fallback_model):
                if not self.ledger.try_spend():
                    logger.info("daily cap reached; using the template")
                    break
                try:
                    out = await complete(self.client, s, model, msgs)
                except LLMError as exc:
                    logger.info("model %s failed: %s", model, exc)
                    continue
                problems = validate(out, facts_json, news_json)
                if not problems:
                    return _clean(out), "llm", model
                logger.info("model %s output rejected: %s", model, "; ".join(problems)[:300])
        return explain_from_template(facts.model_dump()), "template", ""
