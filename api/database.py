"""Lazy PostgreSQL connection management for the FastAPI application."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from pathlib import Path
import sys
from threading import Lock

from dotenv import load_dotenv
from sqlalchemy import Connection, Engine, create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from automotive_analytics.etl import ETLConfig  # noqa: E402


LOGGER = logging.getLogger(__name__)
_ENGINE: Engine | None = None
_ENGINE_LOCK = Lock()


def _integer_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def get_engine() -> Engine:
    """Create one pooled engine on first database-backed request."""

    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                configured = Path(os.getenv("API_ENV_FILE", ".env"))
                env_file = configured if configured.is_absolute() else PROJECT_ROOT / configured
                load_dotenv(env_file, override=False)
                config = ETLConfig.from_env(env_file=None)
                _ENGINE = create_engine(
                    config.database_url,
                    pool_pre_ping=True,
                    pool_size=_integer_env("API_DB_POOL_SIZE", 5),
                    max_overflow=_integer_env("API_DB_MAX_OVERFLOW", 10, minimum=0),
                    pool_timeout=_integer_env("API_DB_POOL_TIMEOUT_SECONDS", 30),
                    connect_args={
                        "connect_timeout": _integer_env("API_DB_CONNECT_TIMEOUT_SECONDS", 10)
                    },
                )
                LOGGER.info("PostgreSQL connection pool initialized")
    return _ENGINE


def get_connection() -> Generator[Connection, None, None]:
    """Provide a short-lived read connection for one API request."""

    with get_engine().connect() as connection:
        yield connection


def dispose_engine() -> None:
    """Dispose the pool during application shutdown or test cleanup."""

    global _ENGINE
    if _ENGINE is not None:
        _ENGINE.dispose()
        _ENGINE = None
        LOGGER.info("PostgreSQL connection pool disposed")
