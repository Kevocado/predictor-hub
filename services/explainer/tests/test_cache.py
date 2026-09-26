from explainer.cache import Cache


def test_roundtrip_and_new_facts_mean_new_key(tmp_path):
    c = Cache(str(tmp_path / "x.sqlite"))
    k1 = Cache.key("nfl", "g1", '{"p":0.62}', "[]", "v1", "m")
    k2 = Cache.key("nfl", "g1", '{"p":0.64}', "[]", "v1", "m")
    assert k1 != k2
    c.put(k1, "nfl", "g1", {"headline": "h", "sections": []}, "llm", "m", "v1")
    got = c.get(k1)
    assert got["body"]["headline"] == "h"
    assert got["source"] == "llm" and got["model"] == "m" and got["prompt_version"] == "v1"
    assert c.get(k2) is None


def test_key_changes_with_news_prompt_and_model():
    base = Cache.key("nfl", "g1", "{}", "[]", "v1", "m")
    assert base != Cache.key("nfl", "g1", "{}", '["x"]', "v1", "m")
    assert base != Cache.key("nfl", "g1", "{}", "[]", "v2", "m")
    assert base != Cache.key("nfl", "g1", "{}", "[]", "v1", "m2")
    assert base != Cache.key("cfb", "g1", "{}", "[]", "v1", "m")


def test_latest_for_returns_newest_row(tmp_path):
    c = Cache(str(tmp_path / "x.sqlite"))
    c.put("a", "nfl", "g1", {"headline": "old"}, "template", "", "v1")
    c.put("b", "nfl", "g1", {"headline": "new"}, "llm", "m", "v1")
    assert c.latest_for("nfl", "g1")["body"]["headline"] == "new"
    assert c.latest_for("nfl", "g2") is None
