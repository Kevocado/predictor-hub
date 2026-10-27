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


#: Who produced a fact. The site's own `/facts` builder is the only producer
#: today, but the field is required so a future source cannot arrive unnamed and
#: be mistaken for the model's own arithmetic.
SITE_SOURCE = "site /facts context.matchups"


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


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

    @model_validator(mode="after")
    def _rating_facts(self) -> "Facts":
        """Turn each drawable matchup into a fact with a source and a GAP.

        The fixture detail draws the two ranks; it does not draw the difference
        between them, and the prompt forbids the model computing one. So the gap
        is computed here, once, and handed over as a fact the validator's number
        pool can see. Rows missing a rank are dropped rather than guessed: a gap
        needs two real ranks and a league size.

        The source is not decoration. A fact without one is a number with no
        provenance, and this bundle is the only thing the model may cite.
        """
        context = self.context if isinstance(self.context, dict) else {}
        rows = context.get("matchups")
        if not isinstance(rows, list):
            return self
        facts = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            attack_rank, defence_rank, n_teams = (
                _int(row.get("attacker_rank")), _int(row.get("defender_rank")), _int(row.get("n_teams")))
            if attack_rank is None or defence_rank is None or n_teams is None or n_teams < 2:
                continue
            if not (1 <= attack_rank <= n_teams and 1 <= defence_rank <= n_teams):
                continue
            if not all(isinstance(row.get(k), str) and row.get(k).strip()
                       for k in ("id", "attacker", "defender", "stat", "foil")):
                continue
            facts.append({
                "id": row["id"],
                "attacker": row["attacker"],
                "defender": row["defender"],
                "attack_stat": row["stat"],
                "defence_stat": row["foil"],
                "attack_rank": attack_rank,
                "defence_rank": defence_rank,
                "n_teams": n_teams,
                "gap": abs(attack_rank - defence_rank),
                "source": SITE_SOURCE,
            })
        if facts:
            context["rating_facts"] = facts
        return self


def render(f: Facts) -> str:
    """Stable JSON: the same facts always render (and so hash) the same."""
    return json.dumps(f.model_dump(), sort_keys=True, ensure_ascii=False)
