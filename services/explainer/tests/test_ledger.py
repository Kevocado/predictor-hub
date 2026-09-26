from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from explainer.ledger import Ledger


def test_cap_and_utc_rollover(tmp_path):
    t = [datetime(2026, 10, 1, 23, 59, tzinfo=timezone.utc)]
    led = Ledger(str(tmp_path / "l.sqlite"), cap=2, now=lambda: t[0])
    assert led.try_spend() and led.try_spend() and not led.try_spend()
    t[0] += timedelta(minutes=2)
    assert led.try_spend() and led.used_today() == 1


def test_never_exceeds_cap_under_concurrency(tmp_path):
    led = Ledger(str(tmp_path / "l.sqlite"), cap=50)
    with ThreadPoolExecutor(16) as pool:
        results = list(pool.map(lambda _: led.try_spend(), range(200)))
    assert sum(results) == 50


def test_count_survives_a_restart(tmp_path):
    p = str(tmp_path / "l.sqlite")
    Ledger(p, cap=5).try_spend()
    assert Ledger(p, cap=5).used_today() == 1
