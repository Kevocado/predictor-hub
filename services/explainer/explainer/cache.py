"""Explanations cached by a hash of everything that shaped them: new odds,
news, prompt or model mean a new key, so stale text is never served."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone


class Cache:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS explanations (key TEXT PRIMARY KEY, sport TEXT, id TEXT, "
                "body_json TEXT, source TEXT, model TEXT, prompt_version TEXT, created_at TEXT)"
            )
            c.execute("CREATE INDEX IF NOT EXISTS explanations_id ON explanations (sport, id, created_at)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, check_same_thread=False, timeout=10)

    @staticmethod
    def key(sport: str, id: str, facts_json: str, news_json: str, prompt_version: str, model: str) -> str:
        raw = "\x1f".join([sport, id, facts_json, news_json, prompt_version, model])
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _row(r) -> dict | None:
        if r is None:
            return None
        return {"body": json.loads(r[0]), "source": r[1], "model": r[2], "prompt_version": r[3], "created_at": r[4]}

    def get(self, key: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT body_json, source, model, prompt_version, created_at FROM explanations "
                          "WHERE key = ?", (key,)).fetchone()
        return self._row(r)

    def put(self, key: str, sport: str, id: str, body: dict, source: str, model: str, prompt_version: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO explanations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (key, sport, id, json.dumps(body, ensure_ascii=False), source, model, prompt_version, now))

    def latest_for(self, sport: str, id: str) -> dict | None:
        """Newest row for an id, whatever its facts: for /status only, never served as an answer."""
        with self._conn() as c:
            r = c.execute("SELECT body_json, source, model, prompt_version, created_at FROM explanations "
                          "WHERE sport = ? AND id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                          (sport, id)).fetchone()
        return self._row(r)
