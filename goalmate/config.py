from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _env(key: str, default: str, dotenv_values: dict[str, str]) -> str:
    return os.environ.get(key, dotenv_values.get(key, default))


@dataclass(frozen=True)
class AppConfig:
    root_dir: Path
    static_dir: Path
    data_dir: Path
    db_path: Path
    host: str
    port: int
    app_env: str
    database_url: str
    session_secret: str
    dev_organizer_id: int
    dev_program_id: int
    dev_participant_id: int

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() != "production"


def load_config(root_dir: Path) -> AppConfig:
    dotenv_values = _load_dotenv(root_dir / ".env")

    data_dir_value = _env("DATA_DIR", "data", dotenv_values)
    data_dir = Path(data_dir_value)
    if not data_dir.is_absolute():
        data_dir = root_dir / data_dir

    db_path_value = _env("DATABASE_PATH", str(data_dir / "goalmate.db"), dotenv_values)
    db_path = Path(db_path_value)
    if not db_path.is_absolute():
        db_path = root_dir / db_path

    return AppConfig(
        root_dir=root_dir,
        static_dir=root_dir / "static",
        data_dir=data_dir,
        db_path=db_path,
        host=_env("HOST", "127.0.0.1", dotenv_values),
        port=int(_env("PORT", "8000", dotenv_values)),
        app_env=_env("APP_ENV", "development", dotenv_values),
        database_url=_env("DATABASE_URL", "", dotenv_values),
        session_secret=_env("SESSION_SECRET", "dev-session-secret", dotenv_values),
        dev_organizer_id=int(_env("DEV_ORGANIZER_ID", "1", dotenv_values)),
        dev_program_id=int(_env("DEV_PROGRAM_ID", "1", dotenv_values)),
        dev_participant_id=int(_env("DEV_PARTICIPANT_ID", "1", dotenv_values)),
    )
