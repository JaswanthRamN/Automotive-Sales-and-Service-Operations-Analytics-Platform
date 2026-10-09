"""Run every read-only SQL acceptance gate and fail on FAIL/empty results."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sqlalchemy import create_engine, text
from automotive_analytics.etl import ETLConfig

CHECK_FILES = [ROOT / 'sql/analytics/data_quality.sql',
               *sorted((ROOT / 'sql/analytics').glob('*_validation.sql')),
               ROOT / 'powerbi/documentation/model_validation.sql']


def check_results(rows, source):
    if not rows:
        raise RuntimeError(f'{source}: no check results')
    failures = [row.get('check_name', 'unnamed') for row in rows if row.get('status') != 'PASS']
    if failures:
        raise RuntimeError(f'{source}: failed checks: {", ".join(failures)}')
    return len(rows)


def main():
    config = ETLConfig.from_env(env_file=ROOT / '.env')
    engine = create_engine(config.database_url, connect_args={
        'connect_timeout': 5, 'options': '-c statement_timeout=30000'})
    total = 0
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
            conn.exec_driver_sql('SET TRANSACTION READ ONLY')
            for path in CHECK_FILES:
                rows = conn.execute(text(path.read_text(encoding='utf-8'))).mappings().all()
                count = check_results(rows, path.name)
                total += count
                print(f'PASS: {path.relative_to(ROOT)} ({count} checks)', flush=True)
        print(f'PASS: {total} SQL checks across {len(CHECK_FILES)} files')
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        print(f'SQL acceptance FAILED: {exc}', file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        # Database exception text can contain query parameters; report only type.
        print(f'SQL acceptance failed: {type(exc).__name__}. Check PostgreSQL availability/configuration and failed check names above.', file=sys.stderr)
        raise SystemExit(1)
