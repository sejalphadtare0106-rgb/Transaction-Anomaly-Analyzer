"""
Clean the raw synthetic transaction file.

Rules used here:
- remove exact duplicate rows, keeping the first one;
- standardise text casing and spacing;
- parse both timestamp formats;
- convert amounts such as "₹1,234.50" to numbers;
- drop rows with a missing Customer_ID, Amount or Transaction_Time;
- fill missing Location and Merchant_Category with "Unknown", not a guess.
"""

from datetime import datetime
from pathlib import Path
import re

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "dataset" / "transactions_raw.csv"
CLEAN_PATH = PROJECT_ROOT / "dataset" / "transactions_clean.csv"
LOG_PATH = PROJECT_ROOT / "reports" / "cleaning_log.txt"

CITIES = [
    "Mumbai",
    "Delhi",
    "Bengaluru",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Pune",
    "Ahmedabad",
]
PAYMENT_CATEGORIES = [
    "Groceries",
    "Fuel",
    "Dining",
    "Online Shopping",
    "Utilities",
    "Travel",
    "Healthcare",
    "Entertainment",
]
MERCHANT_CATEGORIES = PAYMENT_CATEGORIES + ["P2P Transfer", "ATM", "Unknown"]

LOCATION_LOOKUP = {city.casefold(): city for city in CITIES}
LOCATION_LOOKUP["unknown"] = "Unknown"
CATEGORY_LOOKUP = {category.casefold(): category for category in MERCHANT_CATEGORIES}
TYPE_LOOKUP = {name.casefold(): name for name in ["Transfer", "Payment", "Withdrawal"]}
STATUS_LOOKUP = {name.casefold(): name for name in ["Success", "Failed"]}


def _clean_text(value: object) -> str:
    """Trim, collapse repeated spaces and turn missing values into blank text."""
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _map_text(value: object, lookup: dict[str, str]) -> str:
    text = _clean_text(value)
    if text == "":
        return ""
    return lookup.get(text.casefold(), text.title())


def parse_amount(value: object) -> float:
    """Turn rupee-formatted text into a float. Return NaN when it cannot parse."""
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if text == "":
        return np.nan
    text = text.replace("₹", "").replace(",", "").replace(" ", "")
    text = re.sub(r"(?i)^rs\.?", "", text)
    try:
        return round(float(text), 2)
    except ValueError:
        return np.nan


def parse_timestamp(value: object) -> tuple[pd.Timestamp, str]:
    """Try the two timestamp formats used by the generator."""
    if pd.isna(value):
        return pd.NaT, "missing"
    text = str(value).strip()
    if text == "":
        return pd.NaT, "missing"
    for label, fmt in (
        ("iso", "%Y-%m-%d %H:%M:%S"),
        ("day_first", "%d/%m/%Y %H:%M:%S"),
    ):
        try:
            return pd.Timestamp(datetime.strptime(text, fmt)), label
        except ValueError:
            continue
    return pd.NaT, "invalid"


def clean_transactions(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Clean a raw transaction DataFrame and return the clean data plus statistics."""
    stats: dict = {}
    stats["rows_in"] = int(len(raw))
    stats["raw_nulls"] = {column: int(raw[column].isna().sum()) for column in raw.columns}

    # Remove exact duplicates before changing any values. If we standardised
    # first, two rows that were not exact duplicates in the raw file might
    # become duplicates by accident.
    duplicate_mask = raw.duplicated(keep="first")
    stats["duplicates_removed"] = int(duplicate_mask.sum())
    df = raw.loc[~duplicate_mask].copy()

    # Standardise identifiers and text fields.
    df["Transaction_ID"] = df["Transaction_ID"].map(_clean_text).str.upper()
    df["Customer_ID"] = df["Customer_ID"].map(_clean_text).str.upper()
    df["Location"] = df["Location"].map(lambda value: _map_text(value, LOCATION_LOOKUP))
    df["Merchant_Category"] = df["Merchant_Category"].map(
        lambda value: _map_text(value, CATEGORY_LOOKUP)
    )
    df["Transaction_Type"] = df["Transaction_Type"].map(
        lambda value: _map_text(value, TYPE_LOOKUP)
    )
    df["Status"] = df["Status"].map(lambda value: _map_text(value, STATUS_LOOKUP))

    # Amounts may be text such as "₹1,234.50" or plain "2750".
    amount_was_text = df["Amount"].map(
        lambda value: bool(
            not pd.isna(value)
            and re.search(r"[₹,]|^\s*[Rr][Ss]", str(value).strip()) is not None
        )
    )
    stats["text_amounts_cleaned"] = int(amount_was_text.sum())
    df["Amount"] = df["Amount"].map(parse_amount)

    parsed_times = df["Transaction_Time"].map(parse_timestamp)
    df["Transaction_Time"] = [item[0] for item in parsed_times]
    time_formats = [item[1] for item in parsed_times]
    stats["timestamp_formats"] = {
        label: int(time_formats.count(label))
        for label in ["iso", "day_first", "invalid", "missing"]
    }

    # Critical fields: a row without these cannot be used reliably.
    id_missing = df["Customer_ID"].eq("") | df["Customer_ID"].isna()
    amount_missing = df["Amount"].isna()
    time_missing = df["Transaction_Time"].isna()
    stats["critical_missing"] = {
        "Customer_ID": int(id_missing.sum()),
        "Amount": int(amount_missing.sum()),
        "Transaction_Time": int(time_missing.sum()),
    }
    critical_mask = id_missing | amount_missing | time_missing
    stats["rows_dropped_critical"] = int(critical_mask.sum())
    df = df.loc[~critical_mask].copy()

    # Missing Location and Merchant_Category are real gaps. I fill them with
    # "Unknown" and do not try to infer a city or a shop category.
    location_missing = df["Location"].eq("") | df["Location"].isna()
    merchant_missing = df["Merchant_Category"].eq("") | df["Merchant_Category"].isna()
    stats["filled_location_unknown"] = int(location_missing.sum())
    stats["filled_merchant_unknown"] = int(merchant_missing.sum())
    df.loc[location_missing, "Location"] = "Unknown"
    df.loc[merchant_missing, "Merchant_Category"] = "Unknown"

    # Enforce useful types. Transaction_Time stays as datetime inside pandas;
    # the CSV writer below stores it in one ISO format.
    df["Transaction_ID"] = df["Transaction_ID"].astype(str)
    df["Customer_ID"] = df["Customer_ID"].astype(str)
    df["Amount"] = df["Amount"].astype(float).round(2)
    df["Transaction_Time"] = pd.to_datetime(df["Transaction_Time"])
    for column in ["Location", "Transaction_Type", "Merchant_Category", "Status"]:
        df[column] = df[column].astype(str)

    df = df.sort_values(
        ["Transaction_Time", "Transaction_ID"], kind="mergesort"
    ).reset_index(drop=True)
    stats["rows_out"] = int(len(df))
    stats["duplicates_remaining"] = int(df.duplicated().sum())
    stats["unique_transaction_ids"] = int(df["Transaction_ID"].nunique())

    return df, stats


def format_log(stats: dict) -> str:
    """Create the plain-text cleaning log."""
    lines = [
        "CLEANING LOG",
        "=" * 60,
        f"Rows in raw file: {stats['rows_in']:,}",
        f"Exact duplicate rows removed (kept first): {stats['duplicates_removed']:,}",
        f"Rows dropped for missing critical fields: {stats['rows_dropped_critical']:,}",
        f"Rows out clean file: {stats['rows_out']:,}",
        "",
        "Null counts found in the raw file (before cleaning):",
    ]
    for column, count in stats["raw_nulls"].items():
        lines.append(f"  {column}: {count}")

    lines.extend(
        [
            "",
            "How each issue was handled:",
            "  Exact duplicates: removed, kept the first occurrence.",
            "  Customer_ID missing: row dropped.",
            "  Amount missing or not numeric: row dropped.",
            "  Transaction_Time missing or unparseable: row dropped.",
            f"  Location missing after cleaning: filled with 'Unknown' "
            f"({stats['filled_location_unknown']} rows).",
            f"  Merchant_Category missing after cleaning: filled with 'Unknown' "
            f"({stats['filled_merchant_unknown']} rows).",
            f"  Amount values with commas or rupee signs converted to numbers: "
            f"{stats['text_amounts_cleaned']} rows.",
            f"  ISO timestamps parsed: {stats['timestamp_formats']['iso']}.",
            f"  Day-first timestamps parsed: {stats['timestamp_formats']['day_first']}.",
            f"  Missing timestamps: {stats['timestamp_formats']['missing']}.",
            f"  Invalid timestamps: {stats['timestamp_formats']['invalid']}.",
            "  Text casing and extra spaces: standardised using fixed lookup lists.",
            "",
            "Critical missing details after duplicate removal:",
        ]
    )
    for column, count in stats["critical_missing"].items():
        lines.append(f"  {column}: {count}")

    lines.extend(
        [
            "",
            f"Rows out: {stats['rows_out']:,}",
            f"Unique Transaction_ID values: {stats['unique_transaction_ids']:,}",
            f"Exact duplicate rows still present: {stats['duplicates_remaining']}",
            "",
            "Missing values are marked 'Unknown'. I did not guess them.",
            "This data is synthetic. Clean rows are inputs to a rules-based",
            "review score, not proof of fraud.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    DATASET_DIR = CLEAN_PATH.parent
    REPORTS_DIR = LOG_PATH.parent
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(RAW_PATH, dtype=str, keep_default_na=True)
    clean, stats = clean_transactions(raw)
    clean.to_csv(CLEAN_PATH, index=False, date_format="%Y-%m-%d %H:%M:%S")
    log_text = format_log(stats)
    LOG_PATH.write_text(log_text, encoding="utf-8")

    print("Cleaning complete")
    print(log_text)
    print(f"Wrote: {CLEAN_PATH}")
    print(f"Wrote: {LOG_PATH}")


if __name__ == "__main__":
    main()
