"""The explain flow: facts from the sport API, headlines from ESPN, then a
cached answer, or one model call (and one retry on the fallback model)
within the daily budget, validated, else the template."""
from __future__ import annotations

from collections import Counter

import asyncio
import json
import logging
import re
from urllib.parse import quote
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from .cache import Cache
from .config import SERVED_SPORTS
from .contract import band_for, clean_verdict, market_shape, pick_for, pick_prob
from .facts import Facts, PickTiming, render
from .ledger import Ledger
from .llm import LLMError, complete
from .news import headlines
from .prompts import messages
from .template import explain_from_template, minimal
from .validate import validate

logger = logging.getLogger(__name__)

# A template stored because the model was unavailable (budget, outage) is
# served for this long, then the model gets another go at the same facts.
TEMPLATE_RETRY_SECONDS = 3 * 3600
# Stored in the model column of a template row the model may retry later.
UNAVAILABLE = "unavailable"


class NotFound(Exception):
    pass


class Upstream(Exception):
    pass


def _news_terms(f: Facts) -> list[str]:
    if f.sport == "f1":
        return [d["name"] for d in f.drivers[:3] if d.get("name")]
    return [t.strip() for t in re.split(r"\s+(?:at|v|vs\.?|@)\s+", f.title) if t.strip()]


def _clean(body: dict) -> dict:
    """Coerce a model body to the v2 shape, and refuse a body that is not one.

    The cache key covers `prompt_version`, so a v1 row cannot reach here. Asserting
    anyway: a reused version must fail loudly rather than render an empty panel,
    and this is the only place that can notice. A missing `verdict` means a shape
    we do not understand, not a shape we can render.
    """
    if not isinstance(body.get("verdict"), str) or not isinstance(body.get("factors"), list):
        raise ValueError(f"cached body is not a v2 verdict: {sorted(body)}")
    return clean_verdict(body)



class Explainer:
    def __init__(self, settings, cache: Cache, ledger: Ledger, client: httpx.AsyncClient):
        self.settings, self.cache, self.ledger, self.client = settings, cache, ledger, client
        self._locks: dict[str, asyncio.Lock] = {}
        # Failure kinds since start, on /status. A dead default model is
        # otherwise invisible: every call degrades to the template, the reader
        # gets a panel, and nothing says why. This is the only place a
        # withdrawn model, a rate limit and a bad key become distinguishable
        # without reading logs.
        #
        # A Counter, not a dict, and that is not a style choice. `d[k] += 1` on
        # a plain dict raises KeyError on the first sighting of a key, and the
        # caller swallows every exception into a template row -- so the first
        # failure of each kind would have thrown, degraded the whole response,
        # and left no counter at all. A Counter reads a missing key as zero.
        self.failures: Counter[str] = Counter()

    async def _facts(self, sport: str, id: str) -> Facts:
        base = self.settings.sport_api.get(sport)
        if not base:
            raise NotFound(f"no sport API configured for {sport!r}")
        try:
            res = await self.client.get(f"{base}/facts/{quote(id, safe='/')}", timeout=15.0)
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

    def _answer(self, sport: str, id: str, row: dict, facts: Facts) -> dict:
        # pick_timing rides along from the facts rather than being read out of
        # the prose: the panel has to repeat the site's own "Rebuilt after
        # kickoff" status, and neither the model nor the template is a reliable
        # source for that label. The cache key covers the facts, so a hit and
        # the miss that filled it always agree on it.
        model = "" if row["source"] == "template" else row["model"]
        out = {"sport": sport, "id": id, **row["body"],
               # The band is computed, never asked for (spec §13a). A word is
               # the same defect as a number when nothing ties it to anything:
               # a model can call a 52% pick "strong" and there is no fact to
               # contradict it. Unconditional, so this is the only place the
               # response's band is decided and the template path cannot drift.
               "band": band_for(pick_prob(facts), market_shape(facts)),
               "source": row["source"], "model": model,
               "generated_at": row["created_at"], "prompt_version": row["prompt_version"],
               "pick_timing": facts.pick_timing}
        # The pick, derived from the facts for the same reason the band is: the
        # panel has to know which segment of a bar to emphasise, and a model
        # asked to name its own pick can disagree with the facts this verdict was
        # computed from. `pick_for` is the only reader of it, and it agrees with
        # the template's own "is there a pick" test, so the response cannot point
        # the panel at a pick the verdict does not name.
        #
        # The key is OMITTED when there is no pick rather than set to null: the
        # renderer acts on its absence, and `null` would be one more thing to
        # check for instead of the one thing to check.
        pick = pick_for(facts)
        if pick is not None:
            out["pick"] = pick
        return out

    def _usable(self, row: dict | None) -> bool:
        if row is None:
            return False
        # Only a template made while the model was unavailable is retried;
        # one made after the model's answers failed validation stands.
        if row["source"] != "template" or row["model"] != UNAVAILABLE:
            return True
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])).total_seconds()
        return age < TEMPLATE_RETRY_SECONDS

    async def explain(self, sport: str, id: str) -> dict:
        if sport not in SERVED_SPORTS:
            # First line, before the facts fetch and before try_spend(): a
            # refused request must cost nothing and must not touch the upstream.
            #
            # A refusal, not a template. A template here would render a panel
            # and spend nothing, which reads as success — and F1 and NBA are
            # still configured, so nothing else would ever say they had gone.
            raise NotFound(f"{sport} is not served")
        facts = await self._facts(sport, id)
        news = await headlines(self.client, sport, _news_terms(facts))
        facts_json = render(facts)
        news_json = json.dumps(news, sort_keys=True, ensure_ascii=False)
        s = self.settings
        # News feeds the first write-up but isn't in the key: a fresh
        # headline alone must not cost another generation.
        key = Cache.key(sport, id, facts_json, "", s.prompt_version, f"{s.model}|{s.fallback_model}")

        row = self.cache.get(key)
        if self._usable(row):
            return self._answer(sport, id, row, facts)
        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                row = self.cache.get(key)  # another caller may have just made it
                if self._usable(row):
                    return self._answer(sport, id, row, facts)
                try:
                    body, source, model = await self._generate(sport, facts, facts_json, news_json)
                except Exception:
                    logger.exception("explanation failed for %s/%s", sport, id)
                    body, source, model = minimal(facts.model_dump()), "template", UNAVAILABLE
                self.cache.put(key, sport, id, body, source, model, s.prompt_version)
        finally:
            self._locks.pop(key, None)
        return self._answer(sport, id, self.cache.get(key), facts)

    async def _generate(self, sport: str, facts: Facts, facts_json: str, news_json: str) -> tuple[dict, str, str]:
        s = self.settings
        reason = UNAVAILABLE  # no key, disabled, over budget or erroring: retry later
        if s.enabled and s.openrouter_api_key:
            msgs = messages(sport, facts_json, news_json)
            for model in (s.model, s.fallback_model):
                if not self.ledger.try_spend():
                    logger.info("daily cap reached; using the template")
                    break
                try:
                    out = await complete(self.client, s, model, msgs)
                except LLMError as exc:
                    self.failures[exc.kind] += 1
                    logger.warning("model %s failed (%s): %s", model, exc.kind, exc)
                    # A 429 is the provider throttling THIS ACCOUNT, not this
                    # model, so the fallback is the same request again. A 404 is
                    # specific to the model named, so the other one may well
                    # work -- which is the case that matters most, because a
                    # withdrawn default must not cost the product its summaries.
                    if exc.kind == "rate_limited":
                        logger.info("rate limited; not retrying the fallback model")
                        break
                    continue
                problems = validate(out, facts_json, news_json)
                if not problems:
                    return _clean(out), "llm", model
                reason = ""  # the model answered but not honestly enough: don't pay again
                logger.info("model %s output rejected: %s", model, "; ".join(problems)[:300])
        try:
            body = explain_from_template(facts.model_dump())
        except Exception:
            logger.exception("template failed")
            body = minimal(facts.model_dump())
        return body, "template", reason
