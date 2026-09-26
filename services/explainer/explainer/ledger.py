"""The daily OpenRouter budget: counted before every call, retries included,
per UTC day, never exceeded under concurrency."""
import sqlite3
import threading
from datetime import datetime, timezone


class Ledger:
    def __init__(self, path: str, cap: int, now=lambda: datetime.now(timezone.utc)):
        self.path, self.cap, self.now = path, cap, now
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS spend (day TEXT PRIMARY KEY, n INTEGER NOT NULL)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, check_same_thread=False, timeout=10, isolation_level=None)

    def _day(self) -> str:
        return self.now().astimezone(timezone.utc).date().isoformat()

    def try_spend(self) -> bool:
        """Take one request from today's budget; False when it is spent."""
        day = self._day()
        with self._lock:
            c = self._conn()
            try:
                c.execute("BEGIN IMMEDIATE")
                c.execute("INSERT OR IGNORE INTO spend (day, n) VALUES (?, 0)", (day,))
                cur = c.execute("UPDATE spend SET n = n + 1 WHERE day = ? AND n < ?", (day, self.cap))
                c.execute("COMMIT")
                return cur.rowcount == 1
            except Exception:
                c.execute("ROLLBACK")
                raise
            finally:
                c.close()

    def used_today(self) -> int:
        c = self._conn()
        try:
            r = c.execute("SELECT n FROM spend WHERE day = ?", (self._day(),)).fetchone()
        finally:
            c.close()
        return r[0] if r else 0
