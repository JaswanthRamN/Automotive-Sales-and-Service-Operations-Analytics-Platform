from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_required_project_files_exist() -> None:
    required_files = (
        ".env.example",
        ".gitignore",
        "Makefile",
        "README.md",
        "pytest.ini",
        "requirements.txt",
    )

    missing = [name for name in required_files if not (PROJECT_ROOT / name).is_file()]

    assert not missing, f"Missing required project files: {missing}"


def test_required_project_directories_exist() -> None:
    required_directories = (
        "airflow",
        "api",
        "config",
        "dashboards",
        "data/output",
        "data/processed",
        "data/raw",
        "docker",
        "docs",
        "notebooks",
        "scripts",
        "sql",
        "src/automotive_analytics",
        "tests",
    )

    missing = [
        name for name in required_directories if not (PROJECT_ROOT / name).is_dir()
    ]

    assert not missing, f"Missing required project directories: {missing}"


def test_environment_example_contains_no_active_secret() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD=change_me" in env_example
    assert "jaswanthram18@gmail.com" not in env_example

