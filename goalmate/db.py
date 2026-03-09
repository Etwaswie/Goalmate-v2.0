from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from goalmate.config import AppConfig


@dataclass(frozen=True)
class DatabaseSettings:
    backend: str
    driver: str
    database_url: str
    sqlite_path: Path | None
    label: str

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"


def build_database_settings(config: AppConfig) -> DatabaseSettings:
    if not config.database_url:
        return DatabaseSettings(
            backend="sqlite",
            driver="sqlite3",
            database_url="",
            sqlite_path=config.db_path,
            label=str(config.db_path),
        )

    parsed = urlparse(config.database_url)
    scheme = parsed.scheme.lower()
    if scheme in {"sqlite", "sqlite3"}:
        raw_path = parsed.path or ""
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            raw_path = f"/{parsed.netloc}{raw_path}"
        sqlite_path = Path(raw_path or config.db_path)
        if not sqlite_path.is_absolute():
            sqlite_path = config.root_dir / sqlite_path
        return DatabaseSettings(
            backend="sqlite",
            driver="sqlite3",
            database_url=config.database_url,
            sqlite_path=sqlite_path,
            label=str(sqlite_path),
        )

    if scheme in {"postgres", "postgresql"}:
        database_name = parsed.path.lstrip("/") or "goalmate"
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        return DatabaseSettings(
            backend="postgresql",
            driver="pending-adapter",
            database_url=config.database_url,
            sqlite_path=None,
            label=f"{host}:{port}/{database_name}",
        )

    raise RuntimeError(f"Неподдерживаемый DATABASE_URL scheme: {scheme}")


def ensure_sqlite_data_dir(settings: DatabaseSettings) -> None:
    if settings.is_sqlite and settings.sqlite_path is not None:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)


def connect_database(settings: DatabaseSettings) -> sqlite3.Connection:
    if not settings.is_sqlite or settings.sqlite_path is None:
        raise RuntimeError(
            "PostgreSQL backend уже распознан, но runtime-адаптер еще не подключен. "
            "Пока оставь SQLite или продолжай следующий DB-этап."
        )

    connection = sqlite3.connect(settings.sqlite_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
