"""The explain flow: facts from the sport API, headlines from ESPN, then a
cached answer, or one model call (and one retry on the fallback model)
within the daily budget, validated, else the template."""
from __future__ import annotations

from collections import Counter

import asyncio
import json
import logging
import re
import time
from urllib.parse import quote
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from .cache import Cache
from .config import SERVED_SPORTS
from .contract import band_for, market_shape, pick_for, pick_prob
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
# How long a fixture's matchup context is reused before the sport API is asked again.
CONTEXT_TTL_SECONDS = 300


class NotFound(Exception):
    pass


class Upstream(Exception):
    pass


def _news_terms(f: Facts) -> list[str]:
    if f.sport == "f1":
        return [d["name"] for d in f.drivers[:3] if d.get("name")]
    return [t.strip() for t in re.split(r"\s+(?:at|v|vs\.?|@)\s+", f.title) if t.strip()]


def news_fingerprint(news: list[dict]) -> str:
    """The newest matched headline's date, or ``""`` when there is no news.

    A DATE and not the headline text: the question this answers is "is the news I
    was written from still the newest news?", and a headline rewritten for
    clarity on the same day has not changed the answer.
    """
    for item in news:
        published = str(item.get("published") or "")[:10]
        if published:
            return published
    return ""


def _clean(body: dict, facts) -> dict:
    """Coerce a model body to the v9 shape: a verdict and a read, no factors.

    The cache key covers `prompt_version`, so an older row cannot reach here.
    A body without a string `verdict` and `read` is a shape we do not
    understand, not one we can render. `factors` stays in the response as an
    empty list so an older panel renders the verdict and nothing else.
    """
    if not isinstance(body.get("verdict"), str) or not isinstance(body.get("read"), str):
        raise ValueError(f"model body is not a v9 verdict: {sorted(body)}")
    return {"verdict": body["verdict"].strip(), "read": body["read"].strip(), "factors": []}


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
        self._context_cache: dict[tuple[str, str], tuple[float, dict]] = {}

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
        # No band for unknown timing: a confidence word on a pick that cannot be
        # placed in time is a confidence claim the facts do not support. The
        # template returns None for this case; the model path is validated to
        # disclose it, so we also withhold the band here.
        if facts.pick_timing == "unknown":
            band = None
        else:
            band = band_for(pick_prob(facts), market_shape(facts))
        out = {"sport": sport, "id": id, **row["body"],
               "band": band,
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

    async def context(self, sport: str, id: str) -> dict:
        """The matchup context of one fixture, for the always-visible Matchup section.

        No model call, no ledger spend, no news fetch: the facts are fetched the
        same way `explain` does (so the same NotFound/Upstream sanitisation) and
        only the three tactical lists are returned, absent keys omitted. Cached
        briefly in memory so a page of fixtures does not hammer the sport API.
        """
        if sport not in SERVED_SPORTS:
            raise NotFound(f"{sport} is not served")
        key = (sport, id)
        hit = self._context_cache.get(key)
        if hit and time.monotonic() - hit[0] < CONTEXT_TTL_SECONDS:
            return hit[1]
        ctx = (await self._facts(sport, id)).context or {}
        out = {k: ctx[k] for k in ("matchups", "form_rows", "player_context") if ctx.get(k)}
        self._context_cache[key] = (time.monotonic(), out)
        return out

    async def explain(self, sport: str, id: str) -> dict:
        if sport not in SERVED_SPORTS:
            # First line, before the facts fetch and before try_spend(): a
            # refused request must cost nothing and must not touch the upstream.
            #
            # A refusal, not a template. A template here would render a panel
            # and spend nothing, which reads as success.
            #
            # **This used to end "and F1 is still configured, so nothing else
            # would ever say it had gone", which stopped being true when F1 was
            # un-refused.** The sentence was about how a refusal would be
            # noticed: F1 is a sport `config` still knew about, so a guard that
            # stopped refusing it would have had no other signal. With every
            # configured sport served there is no longer such a sport, so
            # `UNSERVED` is empty and this branch is currently unreachable --
            # which is the state `tests/test_unserved_sport.py` exists to hold,
            # since the last time it was empty the file emptied itself. What is
            # left worth saying is the part that does not depend on which sport
            # is refused: `SPORTS` is the set of sports with a configurable API,
            # and anything in it can be asked for, so a refusal here is the only
            # place a "this sport has no panel" answer is produced.
            raise NotFound(f"{sport} is not served")
        facts = await self._facts(sport, id)
        news = await headlines(self.client, sport, _news_terms(facts))
        facts_json = render(facts)
        news_json = json.dumps(news, sort_keys=True, ensure_ascii=False)
        s = self.settings
        # News feeds the first write-up but isn't in the key: a fresh
        # headline alone must not cost another generation.
        key = Cache.key(sport, id, facts_json, news_fingerprint(news),
                        s.prompt_version, f"{s.model}|{s.fallback_model}")

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
                    return _clean(out, facts), "llm", model
                reason = ""  # the model answered but not honestly enough: don't pay again
                logger.info("model %s output rejected: %s", model, "; ".join(problems)[:300])
        try:
            body = {**explain_from_template(facts.model_dump()), "factors": []}
        except Exception:
            logger.exception("template failed")
            body = minimal(facts.model_dump())
        return body, "template", reason
