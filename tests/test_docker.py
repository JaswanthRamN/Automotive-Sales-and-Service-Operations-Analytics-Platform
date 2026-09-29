"""Structural container checks; actual image/runtime checks require Docker."""
import importlib.util
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def test_compose_dependencies_and_persistent_storage():
    config = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
    services = config['services']
    visiting, visited = set(), set()

    def visit(name):
        assert name not in visiting, 'Compose dependency cycle'
        if name in visited:
            return
        visiting.add(name)
        for dependency, rule in services[name].get('depends_on', {}).items():
            assert dependency in services
            if rule['condition'] == 'service_healthy':
                assert 'healthcheck' in services[dependency]
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name, service in services.items():
        visit(name)
        assert service['networks'] == ['analytics']
        if service.get('restart') != 'no':
            assert service['healthcheck']['test']
    assert services['api']['environment']['POSTGRES_HOST'] == 'postgres'
    assert services['airflow-scheduler']['environment']['AIRFLOW__CORE__EXECUTOR'] == 'LocalExecutor'
    assert services['postgres']['volumes'] != services['airflow-db']['volumes']
    assert services['api']['depends_on']['warehouse-init']['condition'] == 'service_completed_successfully'


@pytest.mark.parametrize('fail', [False, True])
def test_bootstrap_runs_views_in_transaction_and_disposes(monkeypatch, fail):
    spec = importlib.util.spec_from_file_location('container_bootstrap', ROOT / 'docker/bootstrap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    monkeypatch.setattr(module, 'create_engine', lambda *_: engine)
    monkeypatch.setattr(module.ETLConfig, 'from_env', lambda **_: MagicMock(database_url='test'))
    schema = MagicMock()
    monkeypatch.setattr(module, 'apply_schema', schema)
    if fail:
        connection.exec_driver_sql.side_effect = RuntimeError('DDL failure')
        with pytest.raises(RuntimeError, match='DDL failure'):
            module.bootstrap()
        assert engine.begin.return_value.__exit__.call_args.args[0] is RuntimeError
    else:
        module.bootstrap()
        assert connection.exec_driver_sql.call_count == 5
        scripts = [call.args[0] for call in connection.exec_driver_sql.call_args_list]
        assert 'vw_sales_detail' in scripts[0]
        assert 'vw_dealership_performance' in scripts[-1]
        assert all('TRUNCATE' not in sql and 'BEGIN;' not in sql for sql in scripts)
    schema.assert_called_once()
    engine.dispose.assert_called_once()
