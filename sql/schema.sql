-- SQLite schema for the Transaction Anomaly & Fraud Pattern Analyzer.
-- build_db.py executes this file and loads the clean CSV with Python.
-- Pure SQL has no portable "load local CSV" command, so loading is done in
-- Python. The table definitions stay here so the database structure is clear.

PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS scored_transactions;
DROP TABLE IF EXISTS customer_profile;
DROP TABLE IF EXISTS transactions;

CREATE TABLE transactions (
    Transaction_ID       TEXT PRIMARY KEY,
    Customer_ID          TEXT NOT NULL,
    Amount               REAL NOT NULL CHECK (Amount >= 0),
    Transaction_Time     TEXT NOT NULL,
    Location             TEXT NOT NULL,
    Transaction_Type     TEXT NOT NULL,
    Merchant_Category    TEXT NOT NULL,
    Status               TEXT NOT NULL
);

CREATE TABLE customer_profile (
    Customer_ID          TEXT PRIMARY KEY,
    Transaction_Count    INTEGER NOT NULL,
    Average_Amount       REAL NOT NULL,
    Home_City            TEXT NOT NULL,
    Failed_Count         INTEGER NOT NULL
);

-- This table is empty after build_db.py. anomaly_detection.py fills it after
-- scoring, which is why SQL Query 5 must run after detection.
CREATE TABLE scored_transactions (
    Transaction_ID       TEXT PRIMARY KEY,
    Risk_Score           INTEGER NOT NULL CHECK (Risk_Score BETWEEN 0 AND 100),
    Risk_Level           TEXT NOT NULL,
    Is_Flagged           INTEGER NOT NULL CHECK (Is_Flagged IN (0, 1)),
    Flag_Count           INTEGER NOT NULL,
    Flag_Reasons         TEXT,
    Flag_High_Amount     INTEGER NOT NULL CHECK (Flag_High_Amount IN (0, 1)),
    Flag_High_Frequency  INTEGER NOT NULL CHECK (Flag_High_Frequency IN (0, 1)),
    Flag_Location        INTEGER NOT NULL CHECK (Flag_Location IN (0, 1)),
    Flag_Timing          INTEGER NOT NULL CHECK (Flag_Timing IN (0, 1)),
    Flag_Failures        INTEGER NOT NULL CHECK (Flag_Failures IN (0, 1))
);

CREATE INDEX idx_transactions_customer_time
    ON transactions (Customer_ID, Transaction_Time);

CREATE INDEX idx_transactions_date
    ON transactions (Transaction_Time);
