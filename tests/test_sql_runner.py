"""SQL gates must reject FAIL, missing status and empty result sets."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_sql', ROOT / 'scripts/check_sql.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('rows', [[], [{'status':'FAIL', 'check_name':'orphan'}], [{'check_name':'missing_status'}]])
def test_gate_rejects_invalid_results(rows):
    with pytest.raises(RuntimeError):
        module.check_results(rows, 'fixture.sql')


def test_gate_accepts_pass_results_and_covers_all_files():
    assert module.check_results([{'status':'PASS'}, {'status':'PASS'}], 'fixture.sql') == 2
    assert len(module.CHECK_FILES) == 7
    assert all(path.is_file() for path in module.CHECK_FILES)
