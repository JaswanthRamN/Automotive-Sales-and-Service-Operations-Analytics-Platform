"""Command-line entry point for the PostgreSQL ETL pipeline."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from automotive_analytics.etl import main  # noqa: E402


if __name__ == "__main__":
    main()
