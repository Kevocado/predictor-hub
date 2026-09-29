"""HTTP API. Sites reach it through their own proxy; nothing here returns
key material."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException

from .cache import Cache
from .config import Settings
from .ledger import Ledger
from .service import Explainer, NotFound, Upstream


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as client:
            app.state.explainer = Explainer(settings, Cache(settings.db_path),
                                            Ledger(settings.db_path, cap=settings.daily_cap), client)
            # No pre-generation. A summary is made when a reader asks for one.
            # The timer used to walk 72 hours across five sports every 3h, which
            # was the main consumer of the daily cap and kept spending on the one
            # sport this service does not serve. The hard cap is unchanged and
            # is enforced by the Ledger at spend time, not here; what goes is the
            # scheduler's own RESERVE headroom, which existed only to stop
            # pre-generation starving on-demand readers.
            yield

    app = FastAPI(title="Predictor explainer", lifespan=lifespan)

    @app.get("/explain/{sport}/{id:path}")
    async def explain(sport: str, id: str):
        try:
            return await app.state.explainer.explain(sport, id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except Upstream as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None

    @app.get("/status")
    def status():
        return {"used_today": app.state.explainer.ledger.used_today(), "cap": settings.daily_cap,
                "enabled": bool(settings.enabled and settings.openrouter_api_key), "model": settings.model,
                # Every kind is present with a zero rather than only the ones
                # seen, so a dashboard can plot them without filling gaps, and
                # so "no failures" and "not being read" cannot be confused.
                # `cut_off` is here for the same reason as the rest: a token
                # budget that is silently too small looks identical to a model
                # that is not being used at all unless the count is published.
                "failures": {kind: app.state.explainer.failures.get(kind, 0)
                             for kind in ("rate_limited", "not_found", "unauthorized",
                                          "bad_response", "cut_off", "transport",
                                          "provider_error")}}

    return app
