"""Settings, from the environment. OPENROUTER_API_KEY lives only here."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SPORTS = ("pl", "f1", "nfl", "cfb", "nba")

#: The sports this service answers for.
#:
#: **F1 was refused here on a product decision, and that refusal has been
#: reversed.** The reasoning it was refused on, kept because it is the reasoning
#: the reversal had to answer and not just overrule: a win probability *is* the
#: explanation. A model that says "Norris 71%" has said the whole thing, and prose
#: over a field of twenty drivers is the model restating its own input at greater
#: length, which is the failure this product exists to avoid. F1 also has no line,
#: so a model-vs-market tile would have nothing honest to show. Both halves of that
#: are still true; what the reversal changed is that the first one is a claim about
#: the win probability and was never an argument about the race story around it.
#: The note on the tuple below says what is now served instead.
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
#:
#: F1 was refused here and is now served. The original reason -- "a win
#: probability IS the explanation" -- was true of the win probability and was
#: never an argument against the race story around it, which is what F1's
#: `drivers` and `podium` carry. F1 still gets a REDUCED panel: it has no line,
#: so the spread and total factors must not fire, and that half of the original
#: reason still stands. Reversed by
#: docs/superpowers/specs/2026-09-28-explainer-panel-flow-trigger-and-news-design.md
#: decision 4 and its `## F1` section; the ledger records the reversal alongside
#: the ruling it replaces.
#:
#: **Every configured sport is served, so the refusal list is empty.** That is the
#: end state rather than a gap, and it has a consequence for the tests: the guard
#: in `service.explain` is still live and still decides whether a sport that is
#: added later gets answered, so `tests/test_unserved_sport.py` has to keep asking
#: it its question by taking a sport out of this tuple for the duration. A guard
#: whose subject list is derived from a list that has gone empty is a guard that
#: has stopped being collected, and pytest reports that as a skip.
SERVED_SPORTS = ("pl", "nfl", "cfb", "nba", "f1")


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
    #: cache already holds ships nothing a reader sees. Move it in the same
    #: change as the writer, never on its own.
    #:
    #: `v2` is spent. `tests/test_prompt_version.py` holds what the deployed
    #: cache was MEASURED to hold on the VPS on 2026-09-27 — a `v1`/`v2` pair,
    #: floor `v2` — and fails if this stops being strictly above it. What the bump
    #: puts live under this version is the cached half of a response, `verdict`
    #: and `factors`: the no-pick `neutral` direction default, the frame's rule
    #: that a factor names a market instead of saying which number is bigger, the
    #: second sentence of rule 2 rewritten so the anti-advice ban no longer hands
    #: the model a model-vs-market comparison to imitate, and the spread sentence
    #: that states both figures without naming a side.
    #:
    #: The band is deliberately NOT in that list, and this is the limit of the
    #: rule rather than an oversight: `service._answer` spreads the stored body
    #: and then re-derives `band`, `pick` and `pick_timing` on every read, hit or
    #: miss. A change to the band is therefore not gated on this field, and a
    #: cached `v2` row already gets the right one. §13e withholds the band chip
    #: in `packages/predictor-ui` for the same reason — it is a reader-side
    #: decision about an unsayable claim, not a writer change.
    #:
    #: **One version is recorded and not deployed, and that is deliberate.**
    #: `tests/test_prompt_version_moves_with_the_prompt.py` is append-only: a row
    #: is never edited, because editing one to match a prompt you have just
    #: changed is the guard switching itself off. A prompt edit made while a
    #: version is still undeployed would strictly be allowed to re-record that
    #: version's row — and `v3` is exactly that case, having never been written
    #: under, since the measured floor is `v2`. It is still bumped rather than
    #: re-recorded, because the cost of the rule being absolute is one number and
    #: the cost of it not being is a guard that can be turned off by editing a
    #: table in the same breath as the prompt. A `v3` row that describes a prompt
    #: nobody was ever sent is a harmless oddity in a log; a re-recordable row is
    #: not.
    #:
    #: Two rules, two files, and neither substitutes for the other.
    #: `tests/test_prompt_version.py` bounds this against production; the other
    #: is `tests/test_prompt_version_moves_with_the_prompt.py`, which holds a
    #: digest of everything the writer sends, so the frame cannot move without
    #: this and leave a green suite behind.
    prompt_version: str = "v5"
    sport_api_pl: str | None = None
    sport_api_f1: str | None = None
    sport_api_nfl: str | None = None
    sport_api_cfb: str | None = None
    sport_api_nba: str | None = None

    @property
    def sport_api(self) -> dict[str, str]:
        """Base URL per sport, from SPORT_API_PL … SPORT_API_NBA; unset sports are left out."""
        return {s: url.rstrip("/") for s in SPORTS if (url := getattr(self, f"sport_api_{s}"))}
