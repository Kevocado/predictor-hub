from explainer.config import Settings


def test_sport_urls_and_budget_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("SPORT_API_NFL", "http://nfl:8000/api/")
    monkeypatch.setenv("EXPLAINER_DAILY_CAP", "10")
    s = Settings()
    assert s.sport_api == {"nfl": "http://nfl:8000/api"}
    assert s.daily_cap == 10


def test_the_key_never_shows_in_repr(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret")
    s = Settings()
    assert s.openrouter_api_key == "sk-or-secret"
    assert "sk-or-secret" not in repr(s)
