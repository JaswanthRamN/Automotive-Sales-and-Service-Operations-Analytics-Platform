from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAG_PATH = PROJECT_ROOT / "airflow" / "dags" / "automotive_etl_dag.py"


class FakeDAG:
    def __init__(self, **kwargs: object) -> None:
        self.dag_id = kwargs["dag_id"]
        self.kwargs = kwargs

    def __enter__(self) -> "FakeDAG":
        return self

    def __exit__(self, *_: object) -> None:
        return None


class FakePythonOperator:
    def __init__(self, *, task_id: str, python_callable: object, **kwargs: object) -> None:
        self.task_id = task_id
        self.python_callable = python_callable
        self.kwargs = kwargs
        self.downstream_task_ids: set[str] = set()

    def __rshift__(self, other: "FakePythonOperator") -> "FakePythonOperator":
        self.downstream_task_ids.add(other.task_id)
        return other


class FakeEmptyOperator(FakePythonOperator):
    def __init__(self, *, task_id: str, **kwargs: object) -> None:
        super().__init__(task_id=task_id, python_callable=None, **kwargs)


def _import_with_airflow_shim(monkeypatch: pytest.MonkeyPatch):
    airflow = ModuleType("airflow")
    models = ModuleType("airflow.models")
    operators = ModuleType("airflow.operators")
    empty_operators = ModuleType("airflow.operators.empty")
    python_operators = ModuleType("airflow.operators.python")
    models.DAG = FakeDAG
    empty_operators.EmptyOperator = FakeEmptyOperator
    python_operators.PythonOperator = FakePythonOperator
    monkeypatch.setitem(sys.modules, "airflow", airflow)
    monkeypatch.setitem(sys.modules, "airflow.models", models)
    monkeypatch.setitem(sys.modules, "airflow.operators", operators)
    monkeypatch.setitem(sys.modules, "airflow.operators.empty", empty_operators)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", python_operators)

    spec = importlib.util.spec_from_file_location("automotive_etl_dag_import_test", DAG_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dag_import_and_dependency_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _import_with_airflow_shim(monkeypatch)

    assert module.dag.dag_id == "automotive_sales_service_etl"
    assert module.dag.kwargs["catchup"] is False
    assert module.dag.kwargs["max_active_runs"] == 1
    assert module.default_args["retries"] == 2
    assert module.extract.downstream_task_ids == {"validate"}
    assert module.validate.downstream_task_ids == {"transform"}
    assert module.transform.downstream_task_ids == {"load"}
    assert module.load.downstream_task_ids == {"quality_check"}
    assert module.quality_check.downstream_task_ids == {"reporting_ready"}
    assert module.reporting_ready.downstream_task_ids == set()
    assert module.reporting_ready.kwargs["trigger_rule"] == "all_success"
    assert module.default_args["retry_exponential_backoff"] is True
    assert module.default_args["execution_timeout"].total_seconds() == 3600
    assert module.quality_check.kwargs["execution_timeout"].total_seconds() == 900


def test_dag_runtime_configuration_uses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRFLOW_DAG_OWNER", "warehouse-team")
    monkeypatch.setenv("AIRFLOW_DAG_SCHEDULE", "0 4 * * *")
    monkeypatch.setenv("AIRFLOW_DAG_RETRIES", "4")
    monkeypatch.setenv("AIRFLOW_RETRY_DELAY_MINUTES", "9")
    monkeypatch.setenv("AIRFLOW_MAX_RETRY_DELAY_MINUTES", "40")
    monkeypatch.setenv("AIRFLOW_TASK_TIMEOUT_MINUTES", "75")
    monkeypatch.setenv("AIRFLOW_QUALITY_TIMEOUT_MINUTES", "12")

    module = _import_with_airflow_shim(monkeypatch)

    assert module.default_args["owner"] == "warehouse-team"
    assert module.default_args["retries"] == 4
    assert module.default_args["retry_delay"].total_seconds() == 540
    assert module.default_args["max_retry_delay"].total_seconds() == 2400
    assert module.default_args["execution_timeout"].total_seconds() == 4500
    assert module.quality_check.kwargs["execution_timeout"].total_seconds() == 720
    assert module.dag.kwargs["schedule"] == "0 4 * * *"


def test_extract_fails_clearly_when_a_required_file_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _import_with_airflow_shim(monkeypatch)
    monkeypatch.setenv("ETL_PROCESSED_DIR", str(tmp_path))

    with pytest.raises(module.ETLValidationError, match="Missing processed CSV file"):
        module._extract()


@pytest.mark.parametrize(
    "rows, message",
    [
        ([], "returned no checks"),
        ([{"status": "FAIL", "check_name": "orphan rows", "failed_count": 3}], "orphan rows=3"),
    ],
)
def test_failed_quality_gate_raises_and_blocks_all_success_downstream(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, object]],
    message: str,
) -> None:
    module = _import_with_airflow_shim(monkeypatch)

    class Result:
        def mappings(self) -> "Result":
            return self

        def all(self) -> list[dict[str, object]]:
            return rows

    class Connection:
        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def exec_driver_sql(self, _: str) -> Result:
            return Result()

    class Engine:
        def connect(self) -> Connection:
            return Connection()

        def dispose(self) -> None:
            return None

    config = type("Config", (), {"database_url": "postgresql+psycopg://test"})()
    monkeypatch.setattr(module, "_etl_config", lambda: config)
    monkeypatch.setattr(module, "create_engine", lambda *args, **kwargs: Engine())

    with pytest.raises(module.ETLValidationError, match=message):
        module._quality_check()
    assert module.reporting_ready.kwargs["trigger_rule"] == "all_success"


def test_real_airflow_dagbag_import_when_airflow_is_installed() -> None:
    try:
        from airflow.models import DagBag
    except ImportError:
        pytest.skip("Apache Airflow is not installed in this test environment")

    dag_bag = DagBag(dag_folder=str(DAG_PATH.parent), include_examples=False)
    assert dag_bag.import_errors == {}
    assert dag_bag.get_dag("automotive_sales_service_etl") is not None
