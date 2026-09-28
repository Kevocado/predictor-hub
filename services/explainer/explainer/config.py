"""Settings, from the environment. OPENROUTER_API_KEY lives only here."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SPORTS = ("pl", "f1", "nfl", "cfb", "nba")

#: The sports this service answers for.
#:
#: **F1 is configured and reachable but not served, and that is a product
#: decision.** A win probability *is* the explanation: a model that says
#: "Norris 71%" has said the whole thing, and prose over a field of twenty drivers
#: is the model restating its own input at greater length, which is the failure
#: this product exists to avoid. F1 also has no line, so a model-vs-market tile
#: would have nothing honest to show.
#:
#: **NBA serves, and it used to be on this list's other side for the wrong
#: reason.** It was refused alongside F1 because "the v2 panel is specified for the
#: three sports whose facts carry the markets it draws" — a claim checked for F1
#: and assumed for NBA. NBA's `/facts` carries `moneyline`, `spread` and `total`,
#: so every component the panel draws is fed.
#:
#: **The shape is NOT the same as NFL and CFB's, and that difference is why serving
#: NBA was not a one-line change.** NFL and CFB put the MARKET's line in `line`.
#: NBA puts the MODEL's own projected margin there -- `"BOS by 4.2"`, or the literal
#: `"Toss-up"` -- and the market's in a separate `market_line`, which it emits only
#: when a pre-tip market row exists. A panel that reads `line` as the market's
#: renders the model compared with itself, and renders it silently in the no-quote
#: case that NBA hits most often.
#:
#: An earlier version of this comment said "the same three keys in the same shape
#: as NFL and CFB". That sentence is what the refusal was justified on, and it was
#: false in the one respect that mattered -- so the comment that a future session
#: reads first is now the one that is true. The code carrying the difference is
#: `template.MARKET_LINE_KEY`; `tests/test_template_quoted_line.py` pins it.
#:
#: Kept beside SPORTS so the "configured" set and the "answered" set are read
#: together — a new sport has to be added to both deliberately rather than by
#: omission.
SERVED_SPORTS = ("pl", "nfl", "cfb", "nba")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    openrouter_api_key: str | None = Field(default=None, repr=False)
    # Both defaults were verified answering from the VPS, which has egress; the
    # previous pair (deepseek/deepseek-chat-v3-0324:free and
    # meta-llama/llama-3.3-70b-instruct:free) was withdrawn from the free tier.
    # A dead model does not fail loudly: the service stores a template row and
    # carries on, so the panel degrades to the template for every fixture and
    # nothing alerts. tests/test_free_models.py pins this, and
    # tests/test_unknown_model_falls_back.py covers the unknown-id case.
    model: str = Field(default="nvidia/nemotron-3.5-lightning:free", validation_alias="EXPLAINER_MODEL")
    fallback_model: str = Field(default="poolside/laguna-s-2.1:free",
                                validation_alias="EXPLAINER_FALLBACK_MODEL")
    daily_cap: int = Field(default=900, validation_alias="EXPLAINER_DAILY_CAP")
    db_path: str = Field(default="/data/explainer.sqlite", validation_alias="EXPLAINER_DB_PATH")
    enabled: bool = Field(default=True, validation_alias="EXPLAINER_ENABLED")
    #: Part of the cache key (`Cache.key`, called from `service.explain`) and a
    #: hit is served verbatim, so this is a deploy precondition rather than a
    #: label: a change to how a body is WRITTEN under a version the deployed
    #: cache already holds ships nothing a reader sees. The frame was changed in
    #: the same commit as this move, so the two are one change.
    #:
    #: What the deployed cache holds was measured on the VPS on 2026-09-27 and is
    #: `v1`/`v2`, so both are spent. `tests/test_prompt_version.py` holds that
    #: floor and fails if this stops being above it, and
    #: `tests/test_prompt_version_moves_with_the_prompt.py` fails if the prompt
    #: text moves without this moving. Two rules, two files: one bounds the
    #: version against production, the other against the writer.
    prompt_version: str = "v3"
    sport_api_pl: str | None = None
    sport_api_f1: str | None = None
    sport_api_nfl: str | None = None
    sport_api_cfb: str | None = None
    sport_api_nba: str | None = None

    @property
    def sport_api(self) -> dict[str, str]:
        """Base URL per sport, from SPORT_API_PL … SPORT_API_NBA; unset sports are left out."""
        return {s: url.rstrip("/") for s in SPORTS if (url := getattr(self, f"sport_api_{s}"))}
