"""
Run the whole project from a clean state.

This deletes only generated data, logs and database files. Documentation and
source files are left alone. Then it runs generation, cleaning, database build,
detection and the ten SQL queries, followed by pytest.
"""

from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_ROOT / "python"
DATASET_DIR = PROJECT_ROOT / "dataset"
DASHBOARD_DATA_DIR = PROJECT_ROOT / "dashboard" / "data"
WEB_DATA_DIR = PROJECT_ROOT / "web" / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"

GENERATED_PATTERNS = [
    (DATASET_DIR, "*.csv"),
    (DATASET_DIR, "*.db"),
    (DASHBOARD_DATA_DIR, "*.csv"),
    (WEB_DATA_DIR, "*.csv"),
    (WEB_DATA_DIR, "*.json"),
]
GENERATED_LOGS = [
    REPORTS_DIR / "cleaning_log.txt",
    REPORTS_DIR / "validation_results.txt",
]


def remove_generated_files() -> None:
    removed = 0
    for folder, pattern in GENERATED_PATTERNS:
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.glob(pattern):
            path.unlink()
            removed += 1
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for path in GENERATED_LOGS:
        if path.exists():
            path.unlink()
            removed += 1
    print(f"Removed {removed} generated file(s).")


def run_step(label: str, arguments: list[str]) -> None:
    print("\n" + "#" * 78)
    print(label)
    print("#" * 78)
    subprocess.run([sys.executable] + arguments, cwd=PROJECT_ROOT, check=True)


def main() -> None:
    remove_generated_files()
    run_step("STEP 1: Generate synthetic data", [str(PYTHON_DIR / "generate_data.py")])
    run_step("STEP 2: Clean data", [str(PYTHON_DIR / "data_cleaning.py")])
    run_step("STEP 3: Build SQLite database", [str(PYTHON_DIR / "build_db.py")])
    run_step(
        "STEP 4: Score anomalies, build dashboard files and validate",
        [str(PYTHON_DIR / "anomaly_detection.py")],
    )
    run_step("STEP 5: Run the ten SQL queries", [str(PYTHON_DIR / "run_sql.py")])
    run_step(
        "STEP 6: Export the static Vercel dashboard data",
        [str(PYTHON_DIR / "export_web.py")],
    )
    run_step("STEP 7: Run tests", ["-m", "pytest", "-q"])

    print("\n" + "=" * 78)
    print("Pipeline finished. All steps and tests passed.")
    print("Dashboard CSVs: dashboard/data")
    print("Static site data: web/data")
    print("Validation: reports/validation_results.txt")
    print("=" * 78)


if __name__ == "__main__":
    main()
