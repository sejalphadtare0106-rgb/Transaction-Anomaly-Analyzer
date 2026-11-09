"""
Build the SQLite database from the clean CSV.

SQLite is built into Python. It is not possible to load a local CSV file into
SQLite with one portable SQL statement, so Python reads the CSV and inserts the
rows. The explicit table definitions are in sql/schema.sql.

Order matters:
  1. build_db.py creates transactions and customer_profile.
  2. anomaly_detection.py later fills scored_transactions.
  3. run_sql.py runs Query 5 after that, so the join has data.
"""

from pathlib import Path
import sqlite3

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_PATH = PROJECT_ROOT / "dataset" / "transactions_clean.csv"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"
DB_PATH = PROJECT_ROOT / "dataset" / "transactions.db"


def build_customer_profile(transactions: pd.DataFrame) -> pd.DataFrame:
    """Create the customer_profile table from the loaded transactions."""
    work = transactions.copy()
    work["Is_Failed"] = (work["Status"] == "Failed").astype(int)

    profile = (
        work.groupby("Customer_ID", as_index=False)
        .agg(
            Transaction_Count=("Transaction_ID", "count"),
            Average_Amount=("Amount", "mean"),
            Failed_Count=("Is_Failed", "sum"),
        )
    )

    # Home city is the most common known successful-transaction city. I use
    # successful rows because failures may contain unusual locations and the
    # detector also builds its baseline from successful rows.
    successful = work[(work["Status"] == "Success") & (work["Location"] != "Unknown")]
    city_counts = (
        successful.groupby(["Customer_ID", "Location"], as_index=False)
        .size()
        .rename(columns={"size": "City_Count"})
        .sort_values(
            ["Customer_ID", "City_Count", "Location"],
            ascending=[True, False, True],
        )
    )
    home = city_counts.drop_duplicates("Customer_ID")[["Customer_ID", "Location"]]
    home = home.rename(columns={"Location": "Home_City"})
    profile = profile.merge(home, on="Customer_ID", how="left")
    profile["Home_City"] = profile["Home_City"].fillna("Unknown")
    profile["Average_Amount"] = profile["Average_Amount"].round(2)
    profile = profile.sort_values("Customer_ID").reset_index(drop=True)
    return profile[
        ["Customer_ID", "Transaction_Count", "Average_Amount", "Home_City", "Failed_Count"]
    ]


def main() -> None:
    if not CLEAN_PATH.exists():
        raise FileNotFoundError(
            f"Clean data not found: {CLEAN_PATH}. Run python/data_cleaning.py first."
        )
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema not found: {SCHEMA_PATH}")

    transactions = pd.read_csv(
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
    transactions["Amount"] = transactions["Amount"].astype(float).round(2)
    transactions["Transaction_Time"] = pd.to_datetime(
        transactions["Transaction_Time"], format="%Y-%m-%d %H:%M:%S"
    ).dt.strftime("%Y-%m-%d %H:%M:%S")

    profile = build_customer_profile(transactions)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        transaction_records = [
            (
                str(row.Transaction_ID),
                str(row.Customer_ID),
                float(row.Amount),
                str(row.Transaction_Time),
                str(row.Location),
                str(row.Transaction_Type),
                str(row.Merchant_Category),
                str(row.Status),
            )
            for row in transactions.itertuples(index=False)
        ]
        conn.executemany(
            """
            INSERT INTO transactions (
                Transaction_ID, Customer_ID, Amount, Transaction_Time,
                Location, Transaction_Type, Merchant_Category, Status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            transaction_records,
        )

        profile_records = [
            (
                str(row.Customer_ID),
                int(row.Transaction_Count),
                float(row.Average_Amount),
                str(row.Home_City),
                int(row.Failed_Count),
            )
            for row in profile.itertuples(index=False)
        ]
        conn.executemany(
            """
            INSERT INTO customer_profile (
                Customer_ID, Transaction_Count, Average_Amount, Home_City, Failed_Count
            ) VALUES (?, ?, ?, ?, ?)
            """,
            profile_records,
        )
        conn.commit()

        transaction_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        profile_count = conn.execute("SELECT COUNT(*) FROM customer_profile").fetchone()[0]
        scored_count = conn.execute("SELECT COUNT(*) FROM scored_transactions").fetchone()[0]
    finally:
        conn.close()

    print("Database built")
    print(f"Database: {DB_PATH}")
    print(f"transactions rows: {transaction_count:,}")
    print(f"customer_profile rows: {profile_count:,}")
    print(f"scored_transactions rows: {scored_count}")
    print("scored_transactions is empty until anomaly_detection.py runs.")


if __name__ == "__main__":
    main()
