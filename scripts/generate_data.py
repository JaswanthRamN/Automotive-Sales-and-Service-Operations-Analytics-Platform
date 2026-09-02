"""Command-line entry point for synthetic raw-data generation."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from automotive_analytics.data_generator import main  # noqa: E402


if __name__ == "__main__":
    main()
