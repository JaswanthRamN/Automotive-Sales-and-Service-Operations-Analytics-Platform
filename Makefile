.PHONY: install test coverage preflight sql-check runtime-check audit docker-check clean

PYTHON ?= python

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov=api --cov-report=term-missing --cov-fail-under=80

preflight:
	$(PYTHON) scripts/run_etl.py --validate-only

sql-check:
	$(PYTHON) scripts/check_sql.py

runtime-check:
	$(PYTHON) scripts/verify_runtime.py

audit:
	$(PYTHON) scripts/audit_repository.py

docker-check:
	docker compose config --quiet

clean:
	$(PYTHON) -c "import shutil; from pathlib import Path; [shutil.rmtree(p, ignore_errors=True) for p in Path('.').rglob('__pycache__')]; shutil.rmtree('.pytest_cache', ignore_errors=True)"
