"""
Export the public data for the static Vercel dashboard.

This copies only the four dashboard CSVs into web/data/ and writes an
aggregate metrics.json. dataset/ground_truth.csv is read only to compute the
same validation numbers that are already in reports/validation_results.txt.
It is never copied into web/.
"""

from contextlib import redirect_stdout
from pathlib import Path
import io
import json
import shutil

import pandas as pd

import anomaly_detection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DATA = PROJECT_ROOT / "dashboard" / "data"
WEB_DATA = PROJECT_ROOT / "web" / "data"

PUBLIC_FILES = [
    "all_transactions_scored.csv",
    "flagged_transactions.csv",
    "flag_summary.csv",
    "daily_summary.csv",
]
FORBIDDEN_COLUMNS = {"Is_Injected_Anomaly", "Injected_Type"}


def main() -> None:
    WEB_DATA.mkdir(parents=True, exist_ok=True)

    for filename in PUBLIC_FILES:
        source = DASHBOARD_DATA / filename
        if not source.exists():
            raise FileNotFoundError(
                f"Dashboard file not found: {source}. Run python/run_all.py first."
            )
        header = pd.read_csv(source, nrows=0)
        bad = FORBIDDEN_COLUMNS.intersection(header.columns)
        if bad:
            raise ValueError(f"Refusing to publish ground-truth columns in {filename}: {bad}")
        shutil.copyfile(source, WEB_DATA / filename)

    scored = pd.read_csv(DASHBOARD_DATA / "all_transactions_scored.csv")

    # validate_results prints a long report and rewrites the validation file.
    # The report was already produced by anomaly_detection.py, so keep this
    # export quiet. The returned dictionary is what the website needs.
    with redirect_stdout(io.StringIO()):
        results = anomaly_detection.validate_results(scored)

    metrics = {
        "scored_rows": results["scored_rows"],
        "injected_rows": results["injected_rows"],
        "flagged_rows": results["flagged_rows"],
        "true_positive": results["true_positive"],
        "false_positive": results["false_positive"],
        "false_negative": results["false_negative"],
        "true_negative": results["true_negative"],
        "precision": round(results["precision"], 6),
        "recall": round(results["recall"], 6),
        "f1": round(results["f1"], 6),
        "base_type_rows": results["base_type_rows"],
        "exact_type_rows": results["exact_type_rows"],
        "fp_by_rule": results["fp_by_rule"],
        "fp_combinations": results["fp_combinations"].to_dict(orient="records"),
        "risk_counts": {
            str(level): int(count) for level, count in results["risk_counts"].items()
        },
        "avg_flagged_score": round(results["avg_flagged_score"], 2),
        "flagged_value": round(results["flagged_value"], 2),
        "total_value": round(results["total_value"], 2),
    }

    metrics_path = WEB_DATA / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("Static web data exported")
    for filename in PUBLIC_FILES:
        print(f"  web/data/{filename}")
    print("  web/data/metrics.json")
    print(f"Flagged rows: {results['flagged_rows']:,}")
    print(f"Precision: {results['precision']:.2%}, recall: {results['recall']:.2%}")
    print("Ground truth was not copied. Only aggregate metrics are published.")


if __name__ == "__main__":
    main()
