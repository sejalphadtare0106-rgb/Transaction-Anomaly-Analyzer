"""
Rule-based anomaly scoring.

The rules are simple on purpose. A flag means "this transaction needs review",
never "this is proven fraud". The risk score is an illustrative review priority,
not a probability of fraud.

Ground truth is NOT used while scoring. It is read only in validate_results(),
after the dashboard files and database table have already been written. This
keeps the detection step honest with respect to the hidden answer key.
"""

from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Every threshold and point value lives here.
# ---------------------------------------------------------------------------
CONFIG = {
    "high_amount_multiplier": 3.0,      # more than 3x the customer's median
    "high_amount_min_inr": 5_000.0,     # and above this rupee floor
    "high_amount_points": 30,
    "frequency_min_transactions": 5,    # 5+ transactions ...
    "frequency_window_minutes": 60,     # ... in any 60-minute window
    "frequency_points": 20,
    "location_share_max": 0.05,         # city under 5% of their history
    "location_points": 25,
    "timing_start_hour": 0,             # 00:00 ...
    "timing_end_hour": 4,               # ... through 04:59
    "timing_share_max": 0.10,           # under 10% of their history
    "timing_points": 15,
    "failure_min_count": 3,             # 3+ failed ...
    "failure_window_minutes": 30,       # ... in any 30-minute window
    "failure_points": 20,
    "score_cap": 100,
    "risk_high_min": 60,
    "risk_medium_min": 30,
    "risk_low_min": 1,
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_PATH = PROJECT_ROOT / "dataset" / "transactions_clean.csv"
GROUND_TRUTH_PATH = PROJECT_ROOT / "dataset" / "ground_truth.csv"
DB_PATH = PROJECT_ROOT / "dataset" / "transactions.db"
DASHBOARD_DATA_DIR = PROJECT_ROOT / "dashboard" / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"

BASE_COLUMNS = [
    "Transaction_ID",
    "Customer_ID",
    "Amount",
    "Transaction_Time",
    "Location",
    "Transaction_Type",
    "Merchant_Category",
    "Status",
]
RULE_COLUMNS = [
    "Flag_High_Amount",
    "Flag_High_Frequency",
    "Flag_Location",
    "Flag_Timing",
    "Flag_Failures",
]
RULE_LABELS = {
    "Flag_High_Amount": "High Amount",
    "Flag_High_Frequency": "High Frequency",
    "Flag_Location": "Unusual City",
    "Flag_Timing": "Night Timing",
    "Flag_Failures": "Repeated Failures",
}
INJECTED_TYPES = [
    "High Amount",
    "Burst",
    "Unusual City",
    "Night Timing",
    "Repeated Failures",
]
FORBIDDEN_OUTPUT_COLUMNS = {"Is_Injected_Anomaly", "Injected_Type"}


def cap_score(points: float) -> int:
    """Risk scores cannot go below 0 or above the configured cap."""
    return int(min(max(points, 0), CONFIG["score_cap"]))


def risk_level_from_score(score: float) -> str:
    """Map a numeric score to the labels used in Power BI."""
    if score >= CONFIG["risk_high_min"]:
        return "High"
    if score >= CONFIG["risk_medium_min"]:
        return "Medium"
    if score >= CONFIG["risk_low_min"]:
        return "Low"
    return "None"


def score_to_risk(points: float) -> tuple[int, str]:
    """Cap a raw point total and return both the score and risk level."""
    score = cap_score(points)
    return score, risk_level_from_score(score)


def amount_band(amount: float) -> str:
    """Same bands as SQL Query 8."""
    if amount < 1_000:
        return "Under 1k"
    if amount < 10_000:
        return "1k-10k"
    if amount < 50_000:
        return "10k-50k"
    return "50k+"


def find_window_positions(
    times: list[pd.Timestamp], minimum_count: int, window_minutes: int
) -> set[int]:
    """
    Return positions that sit inside a window containing at least minimum_count
    timestamps. `times` must be sorted from oldest to newest.

    For each possible start row I move the end pointer forward while the gap is
    inside the window. If the block is large enough, every row in that block is
    marked. This is a simple sliding-window style check, not ML.
    """
    marked: set[int] = set()
    n_rows = len(times)
    for start in range(n_rows):
        end = start
        while (
            end + 1 < n_rows
            and (times[end + 1] - times[start]).total_seconds()
            <= window_minutes * 60
        ):
            end += 1
        if end - start + 1 >= minimum_count:
            marked.update(range(start, end + 1))
    return marked


def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the date/time/band columns used by the rules and dashboard."""
    df = df.copy()
    df["Transaction_Time"] = pd.to_datetime(
        df["Transaction_Time"], format="%Y-%m-%d %H:%M:%S"
    )
    df["Amount"] = df["Amount"].astype(float)
    df["Date"] = df["Transaction_Time"].dt.strftime("%Y-%m-%d")
    df["Hour"] = df["Transaction_Time"].dt.hour.astype(int)
    df["Day_Of_Week"] = df["Transaction_Time"].dt.day_name()
    df["Amount_Band"] = df["Amount"].map(amount_band)
    return df


def calculate_rule_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all five 0/1 rule flags from the customer's own history."""
    df = df.copy()
    successful = df[df["Status"] == "Success"].copy()

    # Median is used because one very large transaction can pull an average up.
    median_by_customer = successful.groupby("Customer_ID")["Amount"].median()
    df["Customer_Median_Amount"] = df["Customer_ID"].map(median_by_customer)
    if df["Customer_Median_Amount"].isna().any():
        missing = sorted(df.loc[df["Customer_Median_Amount"].isna(), "Customer_ID"].unique())
        raise ValueError(f"Customers without a successful baseline: {missing}")

    # Home city and city share are based on successful transactions only.
    known_success = successful[successful["Location"] != "Unknown"]
    city_counts = (
        known_success.groupby(["Customer_ID", "Location"], as_index=False)
        .size()
        .rename(columns={"size": "City_Count"})
    )
    total_success = successful.groupby("Customer_ID").size().rename("Success_Total")
    city_counts = city_counts.merge(
        total_success, left_on="Customer_ID", right_index=True, how="left"
    )
    city_counts["City_Share"] = city_counts["City_Count"] / city_counts["Success_Total"]

    sorted_cities = city_counts.sort_values(
        ["Customer_ID", "City_Count", "Location"],
        ascending=[True, False, True],
    )
    home_lookup = (
        sorted_cities.drop_duplicates("Customer_ID")
        .set_index("Customer_ID")["Location"]
        .to_dict()
    )
    share_lookup = {
        (row.Customer_ID, row.Location): float(row.City_Share)
        for row in city_counts.itertuples(index=False)
    }
    df["_Home_City"] = df["Customer_ID"].map(home_lookup).fillna("Unknown")
    df["_City_Share"] = [
        share_lookup.get((customer, location), 0.0)
        for customer, location in zip(df["Customer_ID"], df["Location"])
    ]

    # Share of successful transactions that happen at night.
    successful["_Is_Night"] = successful["Hour"].between(
        CONFIG["timing_start_hour"], CONFIG["timing_end_hour"]
    )
    night_share = successful.groupby("Customer_ID")["_Is_Night"].mean()
    df["_Night_Share"] = df["Customer_ID"].map(night_share).fillna(0.0)

    # Rule 1: high amount. The median stops normal large spenders from being
    # judged against other customers.
    df["Flag_High_Amount"] = (
        (df["Amount"] > CONFIG["high_amount_multiplier"] * df["Customer_Median_Amount"])
        & (df["Amount"] > CONFIG["high_amount_min_inr"])
    ).astype(int)

    # Rule 2: five or more transactions by one customer in any 60-minute window.
    frequency_flags = pd.Series(0, index=df.index, dtype=int)
    for _, group in df.groupby("Customer_ID", sort=False):
        ordered = group.sort_values("Transaction_Time", kind="mergesort")
        times = ordered["Transaction_Time"].tolist()
        marked = find_window_positions(
            times,
            CONFIG["frequency_min_transactions"],
            CONFIG["frequency_window_minutes"],
        )
        frequency_flags.loc[ordered.index[list(marked)]] = 1
    df["Flag_High_Frequency"] = frequency_flags

    # Rule 3: unusual city. Unknown is missing data, not evidence of a crime.
    df["Flag_Location"] = (
        (df["Location"] != "Unknown")
        & (df["Location"] != df["_Home_City"])
        & (df["_City_Share"] < CONFIG["location_share_max"])
    ).astype(int)

    # Rule 4: night timing for a customer who rarely transacts at night.
    df["Flag_Timing"] = (
        df["Hour"].between(CONFIG["timing_start_hour"], CONFIG["timing_end_hour"])
        & (df["_Night_Share"] < CONFIG["timing_share_max"])
    ).astype(int)

    # Rule 5: three or more failures by one customer in any 30-minute window.
    failure_flags = pd.Series(0, index=df.index, dtype=int)
    failed = df[df["Status"] == "Failed"]
    for _, group in failed.groupby("Customer_ID", sort=False):
        ordered = group.sort_values("Transaction_Time", kind="mergesort")
        times = ordered["Transaction_Time"].tolist()
        marked = find_window_positions(
            times,
            CONFIG["failure_min_count"],
            CONFIG["failure_window_minutes"],
        )
        failure_flags.loc[ordered.index[list(marked)]] = 1
    df["Flag_Failures"] = failure_flags

    return df


def add_scores_and_reasons(df: pd.DataFrame) -> pd.DataFrame:
    """Sum rule points, cap the score and write plain-English reasons."""
    df = df.copy()
    df["Flag_Count"] = df[RULE_COLUMNS].sum(axis=1).astype(int)

    raw_points = (
        df["Flag_High_Amount"] * CONFIG["high_amount_points"]
        + df["Flag_High_Frequency"] * CONFIG["frequency_points"]
        + df["Flag_Location"] * CONFIG["location_points"]
        + df["Flag_Timing"] * CONFIG["timing_points"]
        + df["Flag_Failures"] * CONFIG["failure_points"]
    )
    df["Risk_Score"] = raw_points.map(cap_score).astype(int)
    df["Risk_Level"] = df["Risk_Score"].map(risk_level_from_score)
    df["Is_Flagged"] = (df["Flag_Count"] > 0).astype(int)
    df["Customer_Median_Amount"] = df["Customer_Median_Amount"].round(2)

    reasons = []
    for row in df.itertuples(index=False):
        parts = []
        if row.Flag_High_Amount:
            median = float(row.Customer_Median_Amount)
            multiple = float(row.Amount) / median if median > 0 else 0
            parts.append(f"Amount is {multiple:.1f}x this customer's usual")
        if row.Flag_High_Frequency:
            parts.append(
                f"{CONFIG['frequency_min_transactions']}+ transactions within "
                f"{CONFIG['frequency_window_minutes']} minutes"
            )
        if row.Flag_Location:
            parts.append(f"Unusual city: {row.Location}")
        if row.Flag_Timing:
            parts.append("Transaction between 12:00 AM and 4:59 AM")
        if row.Flag_Failures:
            parts.append(
                f"{CONFIG['failure_min_count']}+ failed attempts within "
                f"{CONFIG['failure_window_minutes']} minutes"
            )
        reasons.append("; ".join(parts))
    df["Flag_Reasons"] = reasons
    return df


def score_transactions(clean: pd.DataFrame) -> pd.DataFrame:
    """Run the scoring pipeline on clean transactions."""
    df = add_basic_features(clean)
    df = calculate_rule_flags(df)
    df = add_scores_and_reasons(df)

    output_columns = BASE_COLUMNS + [
        "Date",
        "Hour",
        "Day_Of_Week",
        "Amount_Band",
        "Customer_Median_Amount",
        "Risk_Score",
        "Risk_Level",
        "Is_Flagged",
        "Flag_Reasons",
        "Flag_Count",
    ] + RULE_COLUMNS
    scored = df[output_columns].copy()
    scored["Transaction_Time"] = scored["Transaction_Time"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return scored


def build_flag_summary(scored: pd.DataFrame) -> pd.DataFrame:
    """Count rows and rupee value touched by each rule."""
    rows = []
    for column in RULE_COLUMNS:
        mask = scored[column] == 1
        rows.append(
            {
                "Flag_Type": RULE_LABELS[column],
                "Count": int(mask.sum()),
                "Total_Value": round(float(scored.loc[mask, "Amount"].sum()), 2),
            }
        )
    return pd.DataFrame(rows)


def build_daily_summary(scored: pd.DataFrame) -> pd.DataFrame:
    """Daily totals for the Power BI overview page."""
    work = scored.copy()
    work["_Flagged_Value"] = np.where(
        work["Is_Flagged"] == 1, work["Amount"], 0.0
    )
    grouped = work.groupby("Date", as_index=False).agg(
        Total_Transactions=("Transaction_ID", "count"),
        Flagged_Count=("Is_Flagged", "sum"),
        Total_Value=("Amount", "sum"),
        Flagged_Value=("_Flagged_Value", "sum"),
    )

    risk_counts = pd.crosstab(work["Date"], work["Risk_Level"])
    for level in ["High", "Medium", "Low"]:
        if level not in risk_counts.columns:
            risk_counts[level] = 0
        grouped[level + "_Count"] = grouped["Date"].map(risk_counts[level]).fillna(0)

    # Fill any missing calendar day with zeros.
    all_dates = pd.date_range(work["Date"].min(), work["Date"].max(), freq="D")
    all_dates = [date.strftime("%Y-%m-%d") for date in all_dates]
    grouped = (
        grouped.set_index("Date")
        .reindex(all_dates, fill_value=0)
        .rename_axis("Date")
        .reset_index()
    )

    grouped["Total_Transactions"] = grouped["Total_Transactions"].astype(int)
    grouped["Flagged_Count"] = grouped["Flagged_Count"].astype(int)
    grouped["High_Count"] = grouped["High_Count"].astype(int)
    grouped["Medium_Count"] = grouped["Medium_Count"].astype(int)
    grouped["Low_Count"] = grouped["Low_Count"].astype(int)
    grouped["Total_Value"] = grouped["Total_Value"].round(2)
    grouped["Flagged_Value"] = grouped["Flagged_Value"].round(2)
    return grouped[
        [
            "Date",
            "Total_Transactions",
            "Flagged_Count",
            "Total_Value",
            "Flagged_Value",
            "High_Count",
            "Medium_Count",
            "Low_Count",
        ]
    ]


def write_dashboard_files(scored: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Write the four CSVs used by Power BI. No ground-truth columns here."""
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    flagged = (
        scored[scored["Is_Flagged"] == 1]
        .sort_values(["Risk_Score", "Transaction_Time"], ascending=[False, True])
        .reset_index(drop=True)
    )
    flag_summary = build_flag_summary(scored)
    daily_summary = build_daily_summary(scored)

    files = {
        "all_transactions_scored.csv": scored,
        "flagged_transactions.csv": flagged,
        "flag_summary.csv": flag_summary,
        "daily_summary.csv": daily_summary,
    }
    for filename, frame in files.items():
        if FORBIDDEN_OUTPUT_COLUMNS.intersection(frame.columns):
            raise ValueError(f"Ground-truth column found in {filename}")
        frame.to_csv(DASHBOARD_DATA_DIR / filename, index=False)
    return files


def write_scores_to_database(scored: pd.DataFrame) -> None:
    """Load the scoring columns into the SQLite scored_transactions table."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. Run python/build_db.py before detection."
        )

    records = [
        (
            str(row.Transaction_ID),
            int(row.Risk_Score),
            str(row.Risk_Level),
            int(row.Is_Flagged),
            int(row.Flag_Count),
            str(row.Flag_Reasons),
            int(row.Flag_High_Amount),
            int(row.Flag_High_Frequency),
            int(row.Flag_Location),
            int(row.Flag_Timing),
            int(row.Flag_Failures),
        )
        for row in scored.itertuples(index=False)
    ]

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM scored_transactions")
        conn.executemany(
            """
            INSERT INTO scored_transactions (
                Transaction_ID, Risk_Score, Risk_Level, Is_Flagged, Flag_Count,
                Flag_Reasons, Flag_High_Amount, Flag_High_Frequency,
                Flag_Location, Flag_Timing, Flag_Failures
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
        conn.commit()
        row_count = conn.execute("SELECT COUNT(*) FROM scored_transactions").fetchone()[0]
    finally:
        conn.close()
    print(f"scored_transactions rows loaded: {row_count:,}")


def _metric(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def validate_results(scored: pd.DataFrame) -> dict:
    """Compare flags with the hidden ground truth. This is validation only."""
    truth = pd.read_csv(GROUND_TRUTH_PATH, dtype={"Transaction_ID": str})
    merged = scored[["Transaction_ID", "Is_Flagged", "Risk_Score"] + RULE_COLUMNS].merge(
        truth,
        on="Transaction_ID",
        how="left",
        validate="one_to_one",
    )
    if merged["Is_Injected_Anomaly"].isna().any():
        raise ValueError("Some scored transactions have no ground-truth row.")

    merged["Is_Injected_Anomaly"] = merged["Is_Injected_Anomaly"].astype(int)
    true_positive = int(((merged["Is_Flagged"] == 1) & (merged["Is_Injected_Anomaly"] == 1)).sum())
    false_positive = int(((merged["Is_Flagged"] == 1) & (merged["Is_Injected_Anomaly"] == 0)).sum())
    false_negative = int(((merged["Is_Flagged"] == 0) & (merged["Is_Injected_Anomaly"] == 1)).sum())
    true_negative = int(((merged["Is_Flagged"] == 0) & (merged["Is_Injected_Anomaly"] == 0)).sum())

    precision = _metric(true_positive, true_positive + false_positive)
    recall = _metric(true_positive, true_positive + false_negative)
    f1 = _metric(2 * precision * recall, precision + recall)

    injected_total = int(merged["Is_Injected_Anomaly"].sum())
    flagged_total = int(merged["Is_Flagged"].sum())

    base_type_rows = []
    for anomaly_type in INJECTED_TYPES:
        subset = merged[merged["Injected_Type"].fillna("").str.contains(anomaly_type, regex=False)]
        detected = int(subset["Is_Flagged"].sum())
        base_type_rows.append(
            {
                "Type": anomaly_type,
                "Injected_Rows": int(len(subset)),
                "Detected_Rows": detected,
                "Recall": _metric(detected, len(subset)),
            }
        )

    exact_type_rows = []
    anomalies = merged[merged["Is_Injected_Anomaly"] == 1]
    for injected_type, group in anomalies.groupby("Injected_Type"):
        detected = int(group["Is_Flagged"].sum())
        exact_type_rows.append(
            {
                "Type": injected_type,
                "Rows": int(len(group)),
                "Detected": detected,
                "Recall": _metric(detected, len(group)),
            }
        )
    exact_type_rows.sort(key=lambda row: (-row["Rows"], row["Type"]))

    false_positives = merged[
        (merged["Is_Flagged"] == 1) & (merged["Is_Injected_Anomaly"] == 0)
    ].copy()
    fp_by_rule = {
        RULE_LABELS[column]: int(false_positives[column].sum()) for column in RULE_COLUMNS
    }

    def combination(row: pd.Series) -> str:
        labels = [RULE_LABELS[column] for column in RULE_COLUMNS if row[column] == 1]
        return " + ".join(labels) if labels else "No rule"

    false_positives["Rule_Combination"] = false_positives.apply(combination, axis=1)
    fp_combinations = (
        false_positives["Rule_Combination"].value_counts().rename_axis("Combination").reset_index(name="Count")
    )

    risk_counts = merged["Risk_Score"].map(risk_level_from_score).value_counts()
    avg_flagged_score = (
        float(merged.loc[merged["Is_Flagged"] == 1, "Risk_Score"].mean())
        if flagged_total
        else 0.0
    )
    flagged_value = float(scored.loc[scored["Is_Flagged"] == 1, "Amount"].sum())
    total_value = float(scored["Amount"].sum())

    results = {
        "scored_rows": int(len(merged)),
        "injected_rows": injected_total,
        "flagged_rows": flagged_total,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "base_type_rows": base_type_rows,
        "exact_type_rows": exact_type_rows,
        "fp_by_rule": fp_by_rule,
        "fp_combinations": fp_combinations,
        "risk_counts": risk_counts,
        "avg_flagged_score": avg_flagged_score,
        "flagged_value": flagged_value,
        "total_value": total_value,
    }

    lines = [
        "VALIDATION RESULTS",
        "=" * 72,
        "This validation is circular. I injected the anomalies, then checked",
        "whether my rules found them. It shows that the rules recover planted",
        "patterns. It does not prove real-world fraud detection performance.",
        "",
        f"Scored transactions: {int(len(merged)):,}",
        f"Injected anomaly rows: {injected_total:,} "
        f"({injected_total / len(merged):.2%} of scored rows)",
        f"Flagged rows: {flagged_total:,} ({flagged_total / len(merged):.2%} of scored rows)",
        "",
        "Overall: Is_Flagged vs Is_Injected_Anomaly",
        f"  True positives:  {true_positive:,}",
        f"  False positives: {false_positive:,}",
        f"  False negatives: {false_negative:,}",
        f"  True negatives:  {true_negative:,}",
        f"  Precision: {precision:.4f} ({precision:.2%})",
        f"  Recall:    {recall:.4f} ({recall:.2%})",
        f"  F1 score:  {f1:.4f} ({f1:.2%})",
        "",
        "Recall by injected type (combined rows count once for each base type):",
    ]
    for row in base_type_rows:
        lines.append(
            f"  {row['Type']}: {row['Detected_Rows']}/{row['Injected_Rows']} "
            f"detected ({row['Recall']:.2%})"
        )

    lines.append("")
    lines.append("Recall by exact ground-truth label:")
    for row in exact_type_rows:
        lines.append(
            f"  {row['Type']}: {row['Detected']}/{row['Rows']} detected "
            f"({row['Recall']:.2%})"
        )

    lines.extend(
        [
            "",
            "False positives by rule (a false positive can trigger more than one rule):",
        ]
    )
    for label, count in fp_by_rule.items():
        lines.append(f"  {label}: {count}")

    lines.append("")
    lines.append("False positives by exact rule combination (each row counted once):")
    if fp_combinations.empty:
        lines.append("  None")
    else:
        for row in fp_combinations.itertuples(index=False):
            lines.append(f"  {row.Combination}: {row.Count}")

    lines.extend(
        [
            "",
            "Risk level counts:",
            f"  None: {int(risk_counts.get('None', 0))}",
            f"  Low: {int(risk_counts.get('Low', 0))}",
            f"  Medium: {int(risk_counts.get('Medium', 0))}",
            f"  High: {int(risk_counts.get('High', 0))}",
            "",
            f"Average Risk_Score of flagged rows: {avg_flagged_score:.2f}",
            f"Total value: INR {total_value:,.2f}",
            f"Flagged value: INR {flagged_value:,.2f}",
            "",
            "A flag means 'needs review', not proof of fraud.",
            "The Risk_Score is an illustrative rules-based score, not a",
            "validated fraud probability.",
        ]
    )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "validation_results.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    return results


def main() -> None:
    if not CLEAN_PATH.exists():
        raise FileNotFoundError(
            f"Clean data not found: {CLEAN_PATH}. Run python/data_cleaning.py first."
        )

    clean = pd.read_csv(
        CLEAN_PATH,
        dtype={
            "Transaction_ID": str,
            "Customer_ID": str,
            "Transaction_Time": str,
            "Location": str,
            "Transaction_Type": str,
            "Merchant_Category": str,
            "Status": str,
        },
    )
    scored = score_transactions(clean)

    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files = write_dashboard_files(scored)
    write_scores_to_database(scored)

    print("Detection and scoring complete")
    print(f"Scored rows: {len(scored):,}")
    print(f"Flagged rows: {int(scored['Is_Flagged'].sum()):,}")
    print("Risk counts: " + ", ".join(
        f"{level}={int(count)}"
        for level, count in scored["Risk_Level"].value_counts().sort_index().items()
    ))
    for filename, frame in files.items():
        print(f"Wrote: {DASHBOARD_DATA_DIR / filename} ({len(frame)} rows)")
    print(f"Dashboard files contain ground truth: "
          f"{any(FORBIDDEN_OUTPUT_COLUMNS.intersection(frame.columns) for frame in files.values())}")

    # Ground truth is read only down here, after every output has been written.
    validate_results(scored)


if __name__ == "__main__":
    main()
