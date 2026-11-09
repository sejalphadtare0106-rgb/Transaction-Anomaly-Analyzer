"""A small set of tests for the important repeatable behaviour."""

from pathlib import Path

import pandas as pd
import pytest

import anomaly_detection
import data_cleaning
import generate_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DATA = PROJECT_ROOT / "dashboard" / "data"


def test_score_is_capped_at_100():
    config = anomaly_detection.CONFIG
    all_rules = sum(
        config[key]
        for key in [
            "high_amount_points",
            "frequency_points",
            "location_points",
            "timing_points",
            "failure_points",
        ]
    )
    assert all_rules > config["score_cap"]
    assert anomaly_detection.cap_score(-10) == 0
    assert anomaly_detection.cap_score(all_rules) == 100
    assert anomaly_detection.score_to_risk(110) == (100, "High")


def test_risk_level_boundaries():
    expected = {
        0: "None",
        1: "Low",
        29: "Low",
        30: "Medium",
        59: "Medium",
        60: "High",
        100: "High",
    }
    for score, level in expected.items():
        assert anomaly_detection.risk_level_from_score(score) == level


def test_cleaning_removes_duplicates_and_parses_messy_amounts():
    columns = [
        "Transaction_ID",
        "Customer_ID",
        "Amount",
        "Transaction_Time",
        "Location",
        "Transaction_Type",
        "Merchant_Category",
        "Status",
    ]
    first_row = {
        "Transaction_ID": "TXN000001",
        "Customer_ID": "CUST001",
        "Amount": "₹1,234.50",
        "Transaction_Time": "01/08/2026 10:00:00",
        "Location": " mumbai ",
        "Transaction_Type": "payment",
        "Merchant_Category": "  groceries ",
        "Status": "success",
    }
    second_row = {
        "Transaction_ID": "TXN000002",
        "Customer_ID": "CUST002",
        "Amount": " 2,000.00 ",
        "Transaction_Time": "2026-08-01 11:00:00",
        "Location": None,
        "Transaction_Type": "Transfer",
        "Merchant_Category": None,
        "Status": "Failed",
    }
    missing_customer = {
        "Transaction_ID": "TXN000003",
        "Customer_ID": None,
        "Amount": "500",
        "Transaction_Time": "2026-08-01 12:00:00",
        "Location": "Delhi",
        "Transaction_Type": "Payment",
        "Merchant_Category": "Dining",
        "Status": "Success",
    }
    raw = pd.DataFrame(
        [first_row, first_row.copy(), second_row, missing_customer], columns=columns
    )

    clean, stats = data_cleaning.clean_transactions(raw)

    assert stats["duplicates_removed"] == 1
    assert stats["rows_dropped_critical"] == 1
    assert len(clean) == 2
    assert clean["Amount"].tolist() == pytest.approx([1234.50, 2000.00])
    assert clean.loc[0, "Location"] == "Mumbai"
    assert clean.loc[0, "Merchant_Category"] == "Groceries"
    assert clean.loc[1, "Location"] == "Unknown"
    assert clean.loc[1, "Merchant_Category"] == "Unknown"
    assert str(clean.loc[0, "Transaction_Time"]) == "2026-08-01 10:00:00"


def test_generator_is_reproducible(tmp_path, monkeypatch):
    monkeypatch.setattr(generate_data, "DATASET_DIR", tmp_path)
    monkeypatch.setattr(generate_data, "RAW_PATH", tmp_path / "transactions_raw.csv")
    monkeypatch.setattr(
        generate_data, "GROUND_TRUTH_PATH", tmp_path / "ground_truth.csv"
    )

    generate_data.main()
    first_raw = (tmp_path / "transactions_raw.csv").read_bytes()
    first_truth = (tmp_path / "ground_truth.csv").read_bytes()

    generate_data.main()
    second_raw = (tmp_path / "transactions_raw.csv").read_bytes()
    second_truth = (tmp_path / "ground_truth.csv").read_bytes()

    assert first_raw == second_raw
    assert first_truth == second_truth

    truth = pd.read_csv(tmp_path / "ground_truth.csv")
    assert len(truth) == 10_000
    assert int(truth["Is_Injected_Anomaly"].sum()) == 400


def test_dashboard_files_do_not_contain_ground_truth():
    files = sorted(DASHBOARD_DATA.glob("*.csv"))
    assert files, "Run python/run_all.py before checking dashboard files."
    for path in files:
        columns = set(pd.read_csv(path, nrows=0).columns)
        assert "Is_Injected_Anomaly" not in columns, path
        assert "Injected_Type" not in columns, path
