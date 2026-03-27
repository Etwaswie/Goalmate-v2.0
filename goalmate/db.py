from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from goalmate.config import AppConfig

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - optional dependency in early iterations
    psycopg = None
    dict_row = None


IDENTITY_TABLES = (
    "organizers",
    "programs",
    "invitation_codes",
    "users",
    "user_contexts",
    "sessions",
    "session_scopes",
    "organization_memberships",
    "modules",
    "tasks",
    "participants",
    "program_memberships",
    "enrollments",
    "teams",
    "team_members",
    "participant_tasks",
    "reports",
    "notifications",
    "daily_metrics",
    "private_challenges",
    "private_challenge_members",
)

_INSERT_OR_IGNORE_RE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.IGNORECASE)
_INSERT_RE = re.compile(r"^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_INTEGER_PRIMARY_KEY_RE = re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\b", re.IGNORECASE)


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

    @property
    def is_postgres(self) -> bool:
        return self.backend == "postgresql"


@dataclass
class CursorResult:
    cursor: Any
    lastrowid: int | None = None

    def fetchone(self) -> Any:
        return self.cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self.cursor.fetchall()


class PostgresCompatConnection:
    backend = "postgresql"

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __enter__(self) -> "PostgresCompatConnection":
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
        return self._connection.__exit__(exc_type, exc, tb)

    def execute(self, statement: str, params: Sequence[Any] | None = None) -> CursorResult:
        translated_statement = translate_statement_for_postgres(statement)
        append_returning = _should_append_returning_id(translated_statement)
        executed_statement = f"{translated_statement} RETURNING id" if append_returning else translated_statement
        cursor = self._connection.execute(executed_statement, params)
        lastrowid = None
        if append_returning:
            row = cursor.fetchone()
            if row is not None:
                lastrowid = int(row["id"])
        return CursorResult(cursor=cursor, lastrowid=lastrowid)

    def executemany(self, statement: str, params_seq: Iterable[Sequence[Any]]) -> Any:
        translated_statement = translate_statement_for_postgres(statement)
        for params in params_seq:
            self._connection.execute(translated_statement, params)
        return None

    def executescript(self, script: str) -> None:
        for statement in split_sql_script(script):
            translated_statement = translate_statement_for_postgres(statement, for_schema=True)
            if translated_statement:
                self._connection.execute(translated_statement)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


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
        driver = "psycopg" if psycopg is not None else "missing-psycopg"
        return DatabaseSettings(
            backend="postgresql",
            driver=driver,
            database_url=config.database_url,
            sqlite_path=None,
            label=f"{host}:{port}/{database_name}",
        )

    raise RuntimeError(f"Неподдерживаемый DATABASE_URL scheme: {scheme}")


def ensure_sqlite_data_dir(settings: DatabaseSettings) -> None:
    if settings.is_sqlite and settings.sqlite_path is not None:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)


def split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False

    for char in script:
        if char == "'":
            in_single_quote = not in_single_quote
        if char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def translate_statement_for_postgres(statement: str, for_schema: bool = False) -> str:
    translated = statement.strip()
    if not translated:
        return ""

    if translated.upper().startswith("PRAGMA "):
        return ""

    translated = _INSERT_OR_IGNORE_RE.sub("INSERT INTO ", translated)
    translated = translated.replace("?", "%s")
    translated = _INTEGER_PRIMARY_KEY_RE.sub("INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY", translated)

    if "INSERT INTO" in translated.upper() and "ON CONFLICT DO NOTHING" not in translated.upper():
        if statement.strip().upper().startswith("INSERT OR IGNORE INTO"):
            translated = f"{translated} ON CONFLICT DO NOTHING"

    if for_schema:
        translated = translated.rstrip(";")
    return translated


def _should_append_returning_id(statement: str) -> bool:
    normalized = statement.strip().upper()
    return normalized.startswith("INSERT INTO") and "RETURNING" not in normalized


def connect_database(settings: DatabaseSettings) -> sqlite3.Connection | PostgresCompatConnection:
    if settings.is_sqlite:
        if settings.sqlite_path is None:
            raise RuntimeError("SQLite backend выбран без sqlite_path")
        connection = sqlite3.connect(settings.sqlite_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    if psycopg is None or dict_row is None:
        raise RuntimeError(
            "Для PostgreSQL нужен пакет psycopg. Установи его и перезапусти GoalMate."
        )

    connection = psycopg.connect(settings.database_url, row_factory=dict_row)
    return PostgresCompatConnection(connection)


def reset_database(settings: DatabaseSettings, connection: sqlite3.Connection | PostgresCompatConnection) -> None:
    if settings.is_sqlite:
        return

    connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
    connection.execute("CREATE SCHEMA public")
    connection.commit()


def sync_identity_sequences(
    settings: DatabaseSettings,
    connection: sqlite3.Connection | PostgresCompatConnection,
    table_names: Sequence[str] = IDENTITY_TABLES,
) -> None:
    if settings.is_sqlite:
        return

    for table_name in table_names:
        sequence_name = f"{table_name}_id_seq"
        connection.execute(
            """
            SELECT setval(
                %s,
                COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                (SELECT COUNT(*) > 0 FROM {table_name})
            )
            """.replace("{table_name}", table_name),
            (sequence_name,),
        )
    connection.commit()
