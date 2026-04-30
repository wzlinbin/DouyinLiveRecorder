from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import SCHEMA

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "config" / "admin.db"


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


class Database:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(SCHEMA)
            self._ensure_schema_updates(connection)

    @staticmethod
    def _ensure_schema_updates(connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(rooms)").fetchall()}
        if "deleted_at" not in columns:
            connection.execute("ALTER TABLE rooms ADD COLUMN deleted_at TEXT")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self, attempts: int = 5) -> Iterator[sqlite3.Connection]:
        last_error: sqlite3.OperationalError | None = None
        for attempt in range(attempts):
            connection = self.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                connection.close()
                if "database is locked" not in str(error).lower():
                    raise
                last_error = error
                time.sleep(0.05 * (attempt + 1))
                continue
            break
        else:
            if last_error:
                raise last_error
            raise RuntimeError("Failed to open SQLite transaction")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


db = Database()
