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
                "enabled": bool(settings.enabled and settings.openrouter_api_key), "model": settings.model}

    return app
