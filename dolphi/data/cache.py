from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional


class LRUCache:
    def __init__(self, maxsize: int = 128, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        timestamp, value = self._cache[key]
        if time.monotonic() - timestamp > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)
        self._cache.move_to_end(key)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


class SQLiteCache:
    def __init__(self, db_path: Path, ttl_hours: int = 1):
        self._db_path = db_path
        self._ttl_seconds = ttl_hours * 3600
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "  key_hash TEXT PRIMARY KEY,"
            "  url TEXT,"
            "  response TEXT,"
            "  fetched_at REAL"
            ")"
        )
        self._conn.commit()

    def _hash(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def get(self, url: str) -> Optional[Any]:
        key_hash = self._hash(url)
        with self._lock:
            row = self._conn.execute(
                "SELECT response, fetched_at FROM cache WHERE key_hash = ?", (key_hash,)
            ).fetchone()
            if row is not None and time.time() - row[1] > self._ttl_seconds:
                self._conn.execute("DELETE FROM cache WHERE key_hash = ?", (key_hash,))
                self._conn.commit()
                return None
        if row is None:
            return None
        response_text, fetched_at = row
        return json.loads(response_text)

    def set(self, url: str, response: Any) -> None:
        key_hash = self._hash(url)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key_hash, url, response, fetched_at) VALUES (?, ?, ?, ?)",
                (key_hash, url, json.dumps(response), time.time()),
            )
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache")
            self._conn.commit()
