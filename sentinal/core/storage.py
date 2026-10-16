"""Small durable SQLite store for local runtime state."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, Iterable


class RuntimeStore:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("SENTINAL_DB_PATH", ".sentinal/sentinal.db")
        self.path = Path(configured)
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._initialize()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    correlation_id TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS config (
                    name TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def events(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in reversed(rows)]

    def append_events(self, items: Iterable[dict[str, Any]]) -> tuple[int, int]:
        accepted = duplicates = 0
        with self._lock, self._connection:
            for item in items:
                key = json.dumps([item["source_id"], item["id"]], separators=(",", ":"))
                cursor = self._connection.execute(
                    "INSERT OR IGNORE INTO events(event_key, payload) VALUES (?, ?)",
                    (key, json.dumps(item, sort_keys=True, default=str)),
                )
                if cursor.rowcount:
                    accepted += 1
                else:
                    duplicates += 1
        return accepted, duplicates

    def alerts(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM alerts ORDER BY updated_at, id"
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_alert(self, alert: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO alerts(id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                updated_at=CURRENT_TIMESTAMP
                """,
                (alert["id"], json.dumps(alert, sort_keys=True, default=str)),
            )

    def audit(self, action: str, payload: dict[str, Any], correlation_id: str | None) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO audit(action, correlation_id, payload) VALUES (?, ?, ?)",
                (action, correlation_id, json.dumps(payload, sort_keys=True, default=str)),
            )

    def load_config(self) -> dict[str, Any]:
        with self._lock:
            rows = self._connection.execute("SELECT name, payload FROM config").fetchall()
        return {row["name"]: json.loads(row["payload"]) for row in rows}

    def save_config(self, name: str, payload: Any) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO config(name, payload) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,
                updated_at=CURRENT_TIMESTAMP
                """,
                (name, json.dumps(payload, sort_keys=True, default=str)),
            )

    def close(self) -> None:
        self._connection.close()
