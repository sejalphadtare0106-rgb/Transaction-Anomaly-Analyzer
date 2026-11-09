"""
Run every query in sql/analysis_queries.sql and print the result tables.

Run this after build_db.py and anomaly_detection.py because Query 5 reads the
scored_transactions table that detection fills.
"""

from pathlib import Path
import re
import sqlite3

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "dataset" / "transactions.db"
QUERY_PATH = PROJECT_ROOT / "sql" / "analysis_queries.sql"


def split_queries(sql_text: str) -> list[str]:
    """Split the file on semicolons. No query contains a semicolon in a string."""
    return [part.strip() for part in sql_text.split(";") if part.strip()]


def query_title(statement: str, fallback: str) -> str:
    match = re.search(r"--\s*Query\s+(\d+)\s*:\s*(.+)", statement)
    return match.group(2).strip() if match else fallback


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. Run python/build_db.py first."
        )

    statements = split_queries(QUERY_PATH.read_text(encoding="utf-8"))
    print(f"Queries found: {len(statements)}")
    if len(statements) != 10:
        raise ValueError(f"Expected 10 queries, found {len(statements)}")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)

    conn = sqlite3.connect(DB_PATH)
    try:
        scored_rows = conn.execute("SELECT COUNT(*) FROM scored_transactions").fetchone()[0]
        for number, statement in enumerate(statements, start=1):
            print("\n" + "=" * 78)
            print(f"Query {number}: {query_title(statement, 'Untitled query')}")
            print("=" * 78)
            if number == 5 and scored_rows == 0:
                print("NOTE: scored_transactions is empty. Run anomaly_detection.py first.")
            result = pd.read_sql_query(statement, conn)
            if result.empty:
                print("No rows returned.")
            else:
                print(result.to_string(index=False))
                print(f"\n({len(result)} row{'s' if len(result) != 1 else ''})")
    finally:
        conn.close()

    print("\nAll 10 queries executed.")


if __name__ == "__main__":
    main()
