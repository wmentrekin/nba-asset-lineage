from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str = "require"

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.dbname} "
            f"user={self.user} "
            f"password={self.password} "
            f"sslmode={self.sslmode}"
        )


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Set it in your local .env (gitignored) or shell environment."
        )
    return value


def _load_local_env_file(path: Path | None = None) -> None:
    resolved = path or Path.cwd() / ".env"
    if not resolved.exists():
        return

    for line in resolved.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def load_db_config() -> DbConfig:
    _load_local_env_file()
    return DbConfig(
        host=_required_env("NBA_ASSET_DB_HOST"),
        port=int(os.getenv("NBA_ASSET_DB_PORT", "5432")),
        dbname=_required_env("NBA_ASSET_DB_NAME"),
        user=_required_env("NBA_ASSET_DB_USER"),
        password=_required_env("NBA_ASSET_DB_PASSWORD"),
        sslmode=os.getenv("NBA_ASSET_DB_SSLMODE", "require"),
    )


def load_database_url() -> str:
    _load_local_env_file()
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError(
            "Missing DATABASE_URL. Set it in your local .env (gitignored) or shell environment."
        )
    return value
