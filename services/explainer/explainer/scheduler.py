"""Pre-generation: every few hours, explain what starts in the next three
days, so most visitors get a cached answer. Keeps RESERVE requests of the
daily budget for on-demand explanations."""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

RESERVE = 50
INTERVAL_SECONDS = 3 * 3600


async def pregenerate(explainer, client: httpx.AsyncClient, sports: list[str], hours: int = 72) -> int:
    cap = explainer.settings.daily_cap
    done = 0
    for sport in sports:
        base = explainer.settings.sport_api.get(sport)
        if not base:
            continue
        try:
            res = await client.get(f"{base}/facts/upcoming", params={"hours": hours}, timeout=15.0)
            res.raise_for_status()
            ids = [str(i) for i in res.json().get("ids", [])]
        except Exception as exc:
            logger.info("pre-generation skipped %s: %s", sport, type(exc).__name__)
            continue
        for id in ids:
            if explainer.ledger.used_today() >= cap - RESERVE:
                logger.info("pre-generation stopped at the on-demand reserve")
                return done
            try:
                await explainer.explain(sport, id)
                done += 1
            except Exception as exc:
                logger.info("pre-generation failed for %s/%s: %s", sport, id, type(exc).__name__)
    return done


async def run_forever(explainer, client: httpx.AsyncClient, sports: list[str]) -> None:
    while True:
        try:
            n = await pregenerate(explainer, client, sports)
            logger.info("pre-generated %d explanations", n)
        except Exception:
            logger.exception("pre-generation run failed")
        await asyncio.sleep(INTERVAL_SECONDS)
