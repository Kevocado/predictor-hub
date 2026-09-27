"""Settings, from the environment. OPENROUTER_API_KEY lives only here."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SPORTS = ("pl", "f1", "nfl", "cfb", "nba")


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
    prompt_version: str = "v1"
    sport_api_pl: str | None = None
    sport_api_f1: str | None = None
    sport_api_nfl: str | None = None
    sport_api_cfb: str | None = None
    sport_api_nba: str | None = None

    @property
    def sport_api(self) -> dict[str, str]:
        """Base URL per sport, from SPORT_API_PL … SPORT_API_NBA; unset sports are left out."""
        return {s: url.rstrip("/") for s in SPORTS if (url := getattr(self, f"sport_api_{s}"))}
