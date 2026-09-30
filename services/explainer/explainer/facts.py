"""The facts bundle each sport API serves at /facts/{id}: the only thing the
model is allowed to talk about."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


#: `unknown` is F1's addition, and it is the reason this Literal matters rather
#: than the model. F1's session start comes from the schedule, so when it is
#: absent "made before the session" is a claim about timing relative to a start
#: time the response did not carry — and F1_Predictor#16 now reports `unknown`
#: for exactly that case rather than asserting `pre_kickoff`.
#:
#: Without this value the service did not degrade, it FAILED: `Facts(**...)`
#: raised, `_fetch` turned that into `Upstream("...failed the contract")`, and
#: the reader got a 502 with no summary at all. A contract that rejects the
#: honest answer is worse than one that omits it — the site was fixed to be
#: truthful and the consumer refused to hear it. Confirmed before this change:
#: feeding a bundle carrying `"unknown"` to `Facts(**...)` raises.
#:
#: A named value, not `str`. `Literal[..., str]` would accept `unknown` and also
#: every other string, which validates nothing; the tests assert both that it is
#: allowed and that a nonsense timing is still rejected.
PickTiming = Literal["pre_kickoff", "rebuilt", "none", "unknown"]


class Market(BaseModel):
    market: str
    model_config = ConfigDict(extra="allow")  # sport-specific fields pass through


class Facts(BaseModel):
    sport: Literal["pl", "f1", "nfl", "cfb", "nba"]
    id: str
    title: str
    starts_at: str
    status: Literal["upcoming", "live", "final"]
    pick_timing: PickTiming
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
