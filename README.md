# Transaction Anomaly & Fraud Pattern Analyzer

I built a small transaction review pipeline in Python and SQL. It generates synthetic banking transactions, cleans a deliberately messy raw file, applies five explainable rules, gives each transaction a review score, and prepares four CSV files for a Power BI dashboard.

All data in this repository is synthetic. A flag means **needs review**, never "proven fraud". The Risk_Score is an **illustrative rules-based score, not a validated fraud probability**.

## Problem

A transaction team cannot manually inspect every row. I wanted to see whether a few simple, explainable rules could move unusual transactions to the top of a review queue. I also wanted the output to say why a row was flagged, so an analyst could check it.

I did not use machine learning. The project is deliberately small: five rules, a fixed score, a SQLite database, tests, and a Power BI guide.

## Tech stack

- Python 3.10+ with pandas and NumPy
- SQLite through Python's built-in `sqlite3` module
- SQL written close to MySQL style, with differences noted below
- pytest
- Power BI Desktop, guide only
- Git and GitHub

## Folder tour

```text
Transaction-Anomaly-Analyzer/
  dataset/
    transactions_raw.csv           messy input, generated
    transactions_clean.csv         cleaned output, generated
    ground_truth.csv               hidden answer key, validation only
    transactions.db                SQLite database, generated and gitignored
  sql/
    schema.sql                     explicit table definitions
    analysis_queries.sql           ten commented analysis queries
  python/
    generate_data.py               synthetic data + planted anomalies
    data_cleaning.py               cleaning and cleaning log
    build_db.py                    load CSV into SQLite, build customer_profile
    anomaly_detection.py           rules, scores, CSV outputs, validation
    run_sql.py                     run the ten SQL queries
    export_web.py                  copy public data for the static site
    run_all.py                     one-command clean pipeline
  dashboard/
    data/
      all_transactions_scored.csv  all rows with scores
      flagged_transactions.csv     flagged rows only
      flag_summary.csv             one row per rule
      daily_summary.csv            daily totals
    POWERBI_GUIDE.md               written but not verified in Power BI
  web/
    index.html                     static Vercel dashboard
    styles.css                     page styles
    app.js                         CSV loading, charts and filters
    data/                          four public CSVs plus metrics.json
    vendor/                        Chart.js and PapaParse, pinned locally
    vercel.json                    static deployment settings
  reports/
    cleaning_log.txt               generated cleaning counts
    validation_results.txt         generated precision/recall details
    analysis_report.md             one-page findings summary
  tests/
    conftest.py
    test_pipeline.py
  README.md
  INTERVIEW.md
  LEARN.md
  requirements.txt
  .gitignore
```

I kept the generated CSV files in the repository on purpose. A reviewer can open the dashboard data without running Python. The database is ignored by Git because it can be rebuilt.

## How the data was made

`python/generate_data.py` uses seed 42. The generated clean dataset has 10,000 transactions from 300 customers over 90 days, from 2026-08-01 to 2026-10-29. Amounts are in INR.

Each customer has a hidden profile:

- a weighted home city from the eight cities used in the project;
- a lognormal amount distribution with a personal median;
- an active-hours window and a personal peak hour;
- a transaction frequency;
- preferred payment categories;
- a mix of Transfer, Payment and Withdrawal transactions.

There are 30 genuine night-owl customers, which is the 10 percent group. Normal failures are kept isolated. I also added innocent oddities so the detector would not be perfect: normal travel to another city, legitimate large purchases, and genuine late-night behaviour.

The clean data contains 400 injected anomaly rows, which is 4.00 percent of 10,000. The generator made 221 anomaly events, and 33 events (14.93 percent) combine two types. The five types are high amount, burst, unusual city, night timing and repeated failures. A burst or failure cluster marks every row in that event as injected.

The raw file has 10,038 rows. The extra work for cleaning is real:

- 30 exact duplicate rows (about 0.3 percent);
- 8 extra rows with a missing Customer_ID, Amount or Transaction_Time;
- 40 null Merchant_Category values;
- 30 null Location values;
- 100 day-first timestamps mixed with ISO timestamps;
- 10 amounts stored as text with commas or a rupee sign;
- inconsistent category casing and extra spaces.

The hidden answer key is in `dataset/ground_truth.csv`. The detector never reads it while scoring. The file is read only after the dashboard CSVs and SQLite scoring table have been written. It is not copied into `dashboard/data/`.

## Cleaning

`python/data_cleaning.py` writes both `dataset/transactions_clean.csv` and `reports/cleaning_log.txt`.

The counts from the last full run:

| Item | Count |
|---|---:|
| Rows in raw file | 10,038 |
| Exact duplicates removed | 30 |
| Rows dropped for missing critical fields | 8 |
| Rows out | 10,000 |
| Location nulls filled with Unknown | 30 |
| Merchant_Category nulls filled with Unknown | 40 |
| Amount text values converted | 10 |
| Day-first timestamps parsed | 100 |

I stripped and standardised text, parsed the two timestamp formats, removed commas and rupee signs from amounts, dropped rows without a usable Customer_ID, Amount or Transaction_Time, and filled missing Location and Merchant_Category with `Unknown`. I did not guess a city or a shop category. The full per-column null table is in the cleaning log.

## SQL

`python/build_db.py` creates `dataset/transactions.db` from `sql/schema.sql`. It loads the clean CSV and builds `customer_profile` from the data. Loading a local CSV into SQLite needs Python or a command-line import; there is no single portable SQL statement for it. I state that in the build script.

The order is important:

1. `build_db.py` creates `transactions`, `customer_profile`, and an empty `scored_transactions` table.
2. `anomaly_detection.py` fills `scored_transactions`.
3. `run_sql.py` runs Query 5 after that, so the join has rows.

`sql/analysis_queries.sql` contains exactly ten numbered queries:

1. Top 20 amounts.
2. Top 10 customers by transaction count.
3. Possible bursts with `GROUP BY` customer and hour plus `HAVING COUNT(*) >= 5`.
4. Activity and value by location.
5. Flagged count and value, joined to `scored_transactions`.
6. Transactions above three times their customer's average, using a correlated subquery.
7. Minutes since the same customer's previous transaction, using `LAG`.
8. Amount bands with `CASE`.
9. Transactions joined to `customer_profile`.
10. Top 10 customers by failed transaction count.

All ten queries ran against the generated SQLite database. Query 5 returned 705 flagged transactions with a total value of INR 8,530,549.33.

### SQLite vs MySQL notes

| Task | SQLite in this project | MySQL equivalent |
|---|---|---|
| Hour bucket | `strftime('%Y-%m-%d %H', Transaction_Time)` | `DATE_FORMAT(Transaction_Time, '%Y-%m-%d %H')` |
| Extract date | `strftime('%Y-%m-%d', Transaction_Time)` | `DATE_FORMAT(Transaction_Time, '%Y-%m-%d')` or `DATE(Transaction_Time)` |
| Minutes between times | `(julianday(a) - julianday(b)) * 24 * 60` | `TIMESTAMPDIFF(MINUTE, b, a)` |
| Previous transaction | `LAG(...) OVER (PARTITION BY ... ORDER BY ...)` | Supported in MySQL 8 and later |
| Load a local CSV | Python `sqlite3` inserts in `build_db.py` | `LOAD DATA INFILE` with the right server permissions |
| Identifier and amount types | SQLite uses dynamic typing; I still write `TEXT`, `INTEGER`, `REAL` | Use `VARCHAR`, `INT`, `DECIMAL` and usually `AUTO_INCREMENT` |

The SQL is close to MySQL, but not a drop-in copy. SQLite stores these timestamps as text and uses `julianday` for date arithmetic. MySQL uses date and time types and `TIMESTAMPDIFF`. Window functions require MySQL 8 or later.

## Detection rules

All thresholds and points are in one `CONFIG` dictionary at the top of `python/anomaly_detection.py`.

The customer baseline is built from that customer's successful transactions. I used successful rows for amount, home city, city share and night share. Frequency and repeated-failure checks look at all transactions because failed attempts matter there. `Unknown` locations are not treated as unusual cities. Missing location is missing data, not evidence.

| Rule | Condition | Points | Why |
|---|---|---:|---|
| High amount | Amount > 3 × the customer's median successful amount AND Amount > 5,000 INR | 30 | One-off large spend can be a warning sign, but a floor avoids flagging small customers. |
| High frequency | The row sits in a window of 5 or more transactions by the same customer within 60 minutes | 20 | Rapid repeated activity can be a burst. |
| Location | City is not the customer's home city AND that city is under 5 percent of their successful transactions | 25 | A city the customer almost never uses is worth checking. |
| Timing | Transaction is between 00:00 and 04:59 AND under 10 percent of the customer's successful transactions happen at those hours | 15 | A night transaction is suspicious only for someone who is not normally awake and active then. |
| Repeated failures | The failed row sits in a window of 3 or more failed attempts within 30 minutes | 20 | Several failures close together can be card testing or a broken payment attempt. |

The score is the sum of points for the rules that fired, capped at 100. The levels are:

- None: 0
- Low: 1 to 29
- Medium: 30 to 59
- High: 60 or more

Each rule also has a 0/1 column. `Flag_Reasons` records plain English reasons, such as an amount being several times the customer's usual or a city they rarely use. `Flag_Count` records how many rules fired.

I did not change any threshold after seeing the validation results. The numbers below are from the first configured rules.

## Results

These are the real results from the final full pipeline run.

The flagged file has 705 rows out of 10,000, or 7.05 percent. There are 400 injected rows. Comparing `Is_Flagged` with the hidden ground truth gives:

| Outcome | Count |
|---|---:|
| True positives | 375 |
| False positives | 330 |
| False negatives | 25 |
| True negatives | 9,270 |

- Precision: 0.5319 (53.19%)
- Recall: 0.9375 (93.75%)
- F1: 0.6787 (67.87%)

Precision and recall look strong, but the validation is circular. I planted the patterns, and the rules were written to look for those patterns. These numbers show that the rules recover the planted patterns. They do not show real-world fraud performance.

### Recall by planted type

Combined-type rows count once under each base type, so the injected counts add to more than 400.

| Injected type | Detected / injected | Recall |
|---|---:|---:|
| High Amount | 75 / 83 | 90.36% |
| Burst | 111 / 111 | 100.00% |
| Unusual City | 62 / 77 | 80.52% |
| Night Timing | 63 / 65 | 96.92% |
| Repeated Failures | 102 / 102 | 100.00% |

The 25 misses are explainable:

- 7 of the 8 missed high-amount rows were below the INR 5,000 floor, and one was 2.88 times the observed median, just under the 3× rule.
- All 15 missed unusual-city rows had a city share of at least 5 percent for that customer. Small transaction histories made a single visit look less unusual.
- The two missed night rows came from customers with 9 and 10 successful transactions, so one night row was 11.11 percent and 10.00 percent of their history, not under 10 percent.

### False positives

The exact rule combinations for the 330 false positives are:

| Rule combination | False positives |
|---|---:|
| High Amount only | 250 |
| Unusual City only | 76 |
| High Frequency only | 3 |
| High Amount + Unusual City | 1 |

The overlapping counts by rule are 251 for High Amount, 77 for Unusual City, 3 for High Frequency, 0 for Night Timing and 0 for Repeated Failures. The one row with both high amount and unusual city is why those per-rule counts add to 331 rather than 330.

The causes match the innocent oddities I built into the data:

- The high-amount rule caused most false positives. Some normal transactions are genuine large purchases at 4 to 8 times the customer's median, and the normal lognormal tail also produces large amounts.
- The unusual-city rule caught normal travel. These are normal transactions in another city, not fraud.
- Three ordinary rows sat in busy 60-minute windows and were caught by the frequency rule.
- The timing rule had no false positives because genuine night owls have a high night share and are not flagged by timing alone.
- The failure rule had no false positives because I kept normal failures isolated in the generator.

### Risk levels and value

| Risk level | Rows |
|---|---:|
| None | 9,295 |
| Low | 306 |
| Medium | 389 |
| High | 10 |

The average Risk_Score of flagged rows is 28.28. Total transaction value is INR 35,766,771.47. Flagged value is INR 8,530,549.33. High risk is a small group because one rule gives at most 30 points, so a row needs at least two rules to reach 60.

## What this project does not prove

The scores are review priorities, not probabilities. A score of 70 does not mean a 70 percent chance of fraud. A flag means an analyst should look at the transaction.

The validation is circular. I wrote both the anomaly generator and the rules, so the measured recall is a check that the rules find the planted patterns. It is not evidence that these rules would work on a bank's real data.

## Limitations

- The data is synthetic. It is not real bank data and does not contain real customer behaviour.
- The validation is circular. I injected the anomalies, so the metrics show recovery of planted patterns, not real-world fraud detection.
- The rules are simple and fixed. They cannot learn new patterns, and the thresholds are not fitted to real outcomes.
- Risk scores are illustrative rules-based scores, not validated fraud probabilities.
- A flag is not proof of fraud.
- Customer profiles use only 90 days of history. Real home-city and travel behaviour would need a longer and more careful baseline.
- The location rule skips `Unknown`. Missing data is not evidence of an unusual city, but this also means some location anomalies can be missed.
- Normal long-tail amounts and legitimate large purchases create many high-amount false positives. The high-amount rule is the largest source of false positives in this run.
- The 5,000 INR floor causes false negatives for low-spend customers.
- Frequent, low-history customers can make a travel city look less unusual than it is.
- Power BI Desktop was not available here. I wrote the dashboard guide but did not build or verify the dashboard.
- SQLite is used for a quick local demo. It is not a production data warehouse.
- The pipeline has only five small tests. They check core boundaries, cleaning, reproducibility and the ground-truth exclusion, not every possible data problem.

## How to run from scratch

Open PowerShell in the project folder. These are Windows-friendly commands.

```powershell
cd "C:\Users\Sejal\Documents\Default Project\Transaction-Anomaly-Analyzer"

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python python\run_all.py
```

If PowerShell blocks the activation script, you can use the virtual environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe python\run_all.py
```

`run_all.py` does the following:

1. Deletes generated CSVs, the SQLite database, the cleaning log and the validation log.
2. Generates the raw data and ground truth with seed 42.
3. Cleans the raw data.
4. Builds the SQLite database and customer profile.
5. Scores the transactions, writes the four dashboard CSVs, loads the scored table into SQLite, and validates against ground truth.
6. Runs all ten SQL queries.
7. Copies the four public CSVs and aggregate metrics into `web/data/` for the static site. It never copies `ground_truth.csv`.
8. Runs pytest.

On the final run, all five tests passed and all ten SQL queries executed.

If you want to run the steps by hand:

```powershell
python python\generate_data.py
python python\data_cleaning.py
python python\build_db.py
python python\anomaly_detection.py
python python\run_sql.py
python python\export_web.py
python -m pytest -q
```

Run them in that order. Query 5 will show a note if detection has not filled `scored_transactions` yet.

## Power BI

The dashboard guide is in `dashboard/POWERBI_GUIDE.md`. It is marked:

> Written but not verified in Power BI Desktop. Power BI Desktop runs on Windows only.

The guide loads the four CSVs, explains the types, lists no required relationships, gives copy-paste DAX measures, and sketches the Overview and Investigation pages. I did not open Power BI Desktop, so I cannot claim the dashboard works. Build it and check the visuals yourself.

## Static web dashboard (Vercel)

I also built a small read-only web dashboard in `web/`. It loads the same four CSVs from `web/data/` and shows headline findings, six charts, the validation tables, and a sortable, paginated review table with filters and a filtered CSV download. It is separate from the Power BI guide. It is not a substitute for checking the Power BI file.

I checked it locally in a browser: all six charts render, the risk/location/type/text filters work, sorting and pagination work, and the CSV download contains the 705 flagged rows with their rule reasons.

Only the `web/` folder is deployed. The ground truth file, the raw dataset and the SQLite database are outside that folder. `python/export_web.py` refuses to copy a CSV that contains `Is_Injected_Anomaly` or `Injected_Type`, and it publishes only aggregate validation numbers in `metrics.json`.

To preview it locally:

```powershell
python -m http.server 8000 --directory web
```

Then open `http://localhost:8000`.

To deploy it, install the Vercel CLI and run this from the project folder:

```powershell
vercel --cwd web --prod
```

`web/data/` is rebuilt by `python/run_all.py`, so rerun the pipeline after changing the rules or the data. Vercel is a static host here. The Python pipeline does not run on Vercel.

## Dashboard screenshots

I still need to build the Power BI file, take both screenshots, and add them here.

Planned paths:

```markdown
![Overview](dashboard/screenshots/overview.png)

![Investigation](dashboard/screenshots/investigation.png)
```

Do not add screenshots until you have actually viewed the dashboard. It is better to leave this section honest than to describe a dashboard that was not checked.

## Reproducibility

The generator uses seed 42. Running `python python/run_all.py` from a clean state rebuilds the same clean data, ground truth, scores, summaries and database rows. The pytest suite includes a test that runs the generator twice in a temporary folder and compares the raw and ground-truth bytes.

## What I would add next

If this were a larger project, I would add a review label field for analyst decisions, a proper date table in Power BI, and a backtest on a separate time period. I would not add machine learning until I had real labels and a fair validation split. For this portfolio version, the simple rules are easier to explain and check.
