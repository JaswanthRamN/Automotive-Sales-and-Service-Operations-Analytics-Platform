from __future__ import annotations

from pathlib import Path

import pytest

from api import database


class FakeConnectionContext:
    def __enter__(self) -> str:
        return "connection"

    def __exit__(self, *_: object) -> None:
        return None


class FakeEngine:
    def __init__(self) -> None:
        self.dispose_calls = 0
        self.connect_calls = 0

    def connect(self) -> FakeConnectionContext:
        self.connect_calls += 1
        return FakeConnectionContext()

    def dispose(self) -> None:
        self.dispose_calls += 1


@pytest.fixture(autouse=True)
def reset_engine(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(database, "_ENGINE", None)
    yield
    monkeypatch.setattr(database, "_ENGINE", None)


@pytest.mark.parametrize(
    "value, message",
    [("abc", "must be an integer"), ("0", "must be at least 1")],
)
def test_integer_environment_validation(
    monkeypatch: pytest.MonkeyPatch, value: str, message: str
) -> None:
    monkeypatch.setenv("TEST_INTEGER", value)
    with pytest.raises(ValueError, match=message):
        database._integer_env("TEST_INTEGER", 5)


def test_engine_is_lazily_configured_from_environment_and_reused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_engine = FakeEngine()
    calls: list[dict[str, object]] = []
    config = type("Config", (), {"database_url": "postgresql+psycopg://configured"})()
    monkeypatch.setenv("API_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.setenv("API_DB_POOL_SIZE", "3")
    monkeypatch.setenv("API_DB_MAX_OVERFLOW", "0")
    monkeypatch.setenv("API_DB_POOL_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("API_DB_CONNECT_TIMEOUT_SECONDS", "4")
    monkeypatch.setattr(database, "load_dotenv", lambda path, override: calls.append({"env_file": path}))
    monkeypatch.setattr(database.ETLConfig, "from_env", lambda env_file=None: config)

    def fake_create_engine(url: object, **kwargs: object) -> FakeEngine:
        calls.append({"url": url, **kwargs})
        return fake_engine

    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    first = database.get_engine()
    second = database.get_engine()

    assert first is second is fake_engine
    assert len(calls) == 2
    assert calls[1]["pool_size"] == 3
    assert calls[1]["max_overflow"] == 0
    assert calls[1]["pool_timeout"] == 12
    assert calls[1]["connect_args"] == {"connect_timeout": 4}


def test_connection_dependency_and_disposal(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(database, "_ENGINE", engine)

    dependency = database.get_connection()
    assert next(dependency) == "connection"
    with pytest.raises(StopIteration):
        next(dependency)
    assert engine.connect_calls == 1

    database.dispose_engine()
    assert engine.dispose_calls == 1
    assert database._ENGINE is None
    database.dispose_engine()
