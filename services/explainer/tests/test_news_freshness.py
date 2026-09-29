"""A summary must not outlive the news it was written from.

`service.py` says, in a comment, that news "isn't in the key: a fresh headline
alone must not cost another generation". That is a real budget concern and it is
the wrong trade for injury news: a summary written on Tuesday saying a
quarterback is starting is served on Wednesday, after a midweek injury, and the
reader is told something that is no longer true.

The rule this pins: the newest MATCHED headline's DATE is in the key, and nothing
else about the news is. So a genuinely newer headline regenerates once, and a
summary already citing today's news is reused at no cost. A fixture with no
matched news puts "" in the key and is therefore unaffected.
"""
from explainer.cache import Cache
from explainer.service import news_fingerprint


def _key(news):
    return Cache.key("nfl", "g1", "{}", news_fingerprint(news), "v3", "m")


def test_no_news_puts_nothing_in_the_key():
    assert news_fingerprint([]) == ""


def test_a_summary_written_before_todays_news_gets_a_different_key():
    """The midweek case, exactly as it happens."""
    before = [{"headline": "Bears quarterback listed questionable", "published": "2026-10-13T14:00:00Z"}]
    after = [{"headline": "Bears quarterback ruled out", "published": "2026-10-14T11:00:00Z"},
             {"headline": "Bears quarterback listed questionable", "published": "2026-10-13T14:00:00Z"}]
    assert _key(before) != _key(after), (
        "a newer headline did not change the key, so Tuesday's summary survives "
        "Wednesday's injury"
    )


def test_more_headlines_on_the_same_day_cost_nothing():
    """The cost bound. Two headlines published the same day are one regeneration,
    not two -- and a day with no new news is free."""
    a = [{"headline": "one", "published": "2026-10-14T09:00:00Z"}]
    b = [{"headline": "two", "published": "2026-10-14T18:00:00Z"},
         {"headline": "one", "published": "2026-10-14T09:00:00Z"}]
    assert _key(a) == _key(b), "a same-day second headline cost a regeneration"


def test_unmatched_news_is_absent_entirely():
    """`headlines()` already returns only matched items, so an empty list is the
    signal. This asserts the fingerprint does not invent a date from nothing."""
    assert news_fingerprint([{"headline": "x", "published": ""}]) == ""