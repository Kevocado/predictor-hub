"""The facts bundle each sport API serves at /facts/{id}: the only thing the
model is allowed to talk about."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Market(BaseModel):
    market: str
    model_config = ConfigDict(extra="allow")  # sport-specific fields pass through


class Facts(BaseModel):
    sport: Literal["pl", "f1", "nfl", "cfb", "nba"]
    id: str
    title: str
    starts_at: str
    status: Literal["upcoming", "live", "final"]
    pick_timing: Literal["pre_kickoff", "rebuilt", "none"]
    pick: dict | None = None
    markets: list[Market] = []
    drivers: list[dict] = []
    context: dict = {}
    players: list[dict] = []
    record: dict | None = None
    result: dict | None = None

    @model_validator(mode="after")
    def _rebuilt_never_won(self) -> "Facts":
        # A pick built after the start is shown, never judged.
        if self.pick_timing == "rebuilt" and self.result and "pick_won" in self.result:
            raise ValueError("a rebuilt pick cannot carry result.pick_won")
        return self


def render(f: Facts) -> str:
    """Stable JSON: the same facts always render (and so hash) the same."""
    return json.dumps(f.model_dump(), sort_keys=True, ensure_ascii=False)
