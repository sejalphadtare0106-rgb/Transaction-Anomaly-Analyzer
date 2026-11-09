# Learn the Project

This file is for studying the project after it is built. I explain what each file does, then the main concepts. Read the files in the order they run.

The short version of the pipeline:

```text
generate_data.py
      |
      v
transactions_raw.csv + ground_truth.csv
      |
      v
data_cleaning.py
      |
      v
transactions_clean.csv
      |
      +----------------------+
      |                      |
      v                      v
build_db.py            anomaly_detection.py
      |                      |
      v                      +--> dashboard/data/*.csv
transactions.db              +--> scored_transactions table
      |                      +--> validation against ground truth
      v
run_sql.py
```

## Every file

### `dataset/transactions_raw.csv`

This is the deliberately messy input. It has 10,038 rows. The extra rows are 30 exact duplicates and 8 rows with a missing critical field. Some merchant or location values are blank. A few amounts are text with commas or a rupee sign. Some dates use a day-first format.

I never edit this file by hand. Running the generator recreates it with seed 42.

### `dataset/transactions_clean.csv`

This is the cleaned output. It has 10,000 rows, one per transaction ID. Text is standardised, dates are ISO, amounts are numbers, duplicates are gone, and missing city or merchant values say `Unknown`.

### `dataset/ground_truth.csv`

This is the hidden answer key. It has three columns: `Transaction_ID`, `Is_Injected_Anomaly` and `Injected_Type`.

It is not an input to the detector. `anomaly_detection.py` reads it only after writing the dashboard files. It is also not copied into `dashboard/data/`.

### `dataset/transactions.db`

This is the SQLite database created by `build_db.py`. It contains:

- `transactions`, loaded from the clean CSV;
- `customer_profile`, built from the transactions;
- `scored_transactions`, empty at first, then filled by `anomaly_detection.py`.

The database is ignored by Git because it can be rebuilt.

### `sql/schema.sql`

This file contains the table definitions. I wrote the types and constraints here instead of hiding them inside Python code.

`transactions` has the clean columns. Its primary key is `Transaction_ID`.

`customer_profile` has one row per customer: count, average amount, home city and failed count.

`scored_transactions` stores the score columns. Its `Risk_Score` has a `CHECK` constraint from 0 to 100.

### `sql/analysis_queries.sql`

This file holds exactly ten SQL queries. Each one starts with a comment that states the business question. The queries cover:

1. Highest amounts.
2. Busiest customers.
3. Possible bursts with `GROUP BY` and `HAVING`.
4. Activity by location.
5. Flagged count and value from `scored_transactions`.
6. Amounts above three times the customer average with a subquery.
7. Time since the previous transaction with `LAG`.
8. Amount bands with `CASE`.
9. Transactions joined to `customer_profile`.
10. Failed transactions per customer.

### `python/generate_data.py`

This creates the data. I use `numpy.random.default_rng(SEED)` so the random numbers are repeatable. The seed is 42.

The script first builds 300 customer profiles. A profile contains a home city, a median amount, an amount spread, an active-hours window, a peak hour, a transaction mix and preferred categories.

It then makes normal transactions, adds three kinds of innocent oddities, and plants 400 anomaly rows. Bursts and repeated failures are groups of rows, not single rows. About 15 percent of the event objects combine two anomaly types.

Finally it adds raw-file problems: duplicates, blank values, messy categories, mixed dates, text amounts and a few rows with missing critical fields. It writes the raw CSV and the separate ground truth.

### `python/data_cleaning.py`

This script defines the cleaning functions and the command-line entry point.

The important order is:

1. Read the raw data as text.
2. Remove exact duplicate rows before changing values.
3. Clean and standardise text.
4. Parse amounts and timestamps.
5. Find and drop rows with missing critical fields.
6. Fill missing Location and Merchant_Category with `Unknown`.
7. Enforce types and sort.
8. Write the clean CSV and the cleaning log.

The log records the count before and after each important step.

### `python/build_db.py`

This creates the SQLite database. SQLite has no one-line local CSV load that works the same everywhere, so Python reads the CSV and inserts the rows.

The `customer_profile` table is built from the clean transactions. The count and average use every transaction. The failed count uses `Status = 'Failed'`. The home city is the most common known successful-transaction city.

The script leaves `scored_transactions` empty because scoring has not run yet.

### `python/anomaly_detection.py`

This is the main analysis script. `CONFIG` at the top holds every threshold and point value.

The script adds Date, Hour, Day_Of_Week and Amount_Band. It builds each customer's successful baseline. Then it calculates five rule flags, sums points, caps the score, assigns a risk level, and writes plain reasons.

It writes four dashboard CSVs and loads `scored_transactions` into SQLite. After those outputs are written, it reads the ground truth and prints precision, recall, per-type recall and false-positive counts.

### `python/run_sql.py`

This reads `analysis_queries.sql`, splits it into ten statements and runs them one at a time against `transactions.db`. It prints a readable table for each query.

It checks that the scored table has rows and prints a warning if Query 5 is about to run before detection.

### `python/run_all.py`

This is the one-command runner. It deletes generated data, logs and database files, then calls each script in order. At the end it calls pytest.

It deletes generated files only. It does not delete source files or documentation.

### `dashboard/data/all_transactions_scored.csv`

This has all 10,000 clean rows plus the date fields, amount band, customer median, score, risk level, flag reasons, flag count and five rule columns.

### `dashboard/data/flagged_transactions.csv`

This is the same columns filtered to `Is_Flagged = 1`. It is sorted by `Risk_Score` from high to low. It has 705 rows in the last run.

### `dashboard/data/flag_summary.csv`

This has one row per rule: Flag_Type, Count and Total_Value. The counts overlap because one transaction can trigger more than one rule. This file is for a rule-level chart, not for counting unique flagged transactions.

### `dashboard/data/daily_summary.csv`

This has one row per day. It includes transaction count, flagged count, total value, flagged value and counts for High, Medium and Low risk. It has 90 rows in the last run.

### `dashboard/POWERBI_GUIDE.md`

This is a manual guide for building the dashboard. It is marked as written but not verified in Power BI Desktop. It explains the file imports, column types, pages, DAX measures, layout and common problems.

### `reports/cleaning_log.txt`

This is generated by `data_cleaning.py`. It records rows in, duplicates, dropped rows, missing values, timestamp formats and rows out.

### `reports/validation_results.txt`

This is generated by `anomaly_detection.py` after scoring. It contains the confusion matrix, precision, recall, F1, recall by type, false positives by rule and risk counts.

### `reports/analysis_report.md`

This is a short findings summary. It uses numbers from the generated validation file.

### `tests/conftest.py`

This adds the `python/` folder to the import path so the tests can import the scripts.

### `tests/test_pipeline.py`

This has five tests:

- score cap;
- risk level boundaries;
- cleaning duplicates and messy amounts;
- generator reproducibility;
- no ground-truth columns in dashboard files.

### `README.md`

This is the project overview, setup instructions, methodology, results, SQL notes and limitations.

### `INTERVIEW.md`

This has a spoken project explanation and twelve short interview answers.

### `LEARN.md`

This file. It is the beginner study guide.

### `requirements.txt`

This lists pandas, NumPy and pytest.

### `.gitignore`

This ignores Python caches, virtual environments, database files and Power BI temp files. The CSV files stay in Git on purpose.

## Key concepts

### Data cleaning and duplicate removal

An exact duplicate is a row that matches another row in every column. I remove it and keep the first copy. If I cleaned the text first, two rows that were not exact duplicates in the raw file might become duplicates by accident, so the duplicate check runs before standardisation.

Missing critical fields are different. A row without a usable Customer_ID, Amount or Transaction_Time cannot be tied to a customer or used in time-based rules, so I drop it. Missing Location or Merchant_Category is a gap I can keep, so I fill it with `Unknown`.

### Why the raw file is messy

Real files do not arrive in a perfect format. Mixed dates, blank values and amounts with currency symbols are normal problems. The mess gives the cleaning script something real to handle and gives the cleaning log useful counts.

### Customer baseline

A baseline is what "normal" looks like for one customer. I use that customer's successful transactions for:

- median amount;
- most common city, which becomes the home city;
- city share;
- night share.

I do not compare a customer against all customers. A student who spends small amounts should not look unusual just because another customer spends more.

### Median vs mean

The mean is the arithmetic average: add all values and divide by the count. The median is the middle value after sorting.

One very large transaction can pull the mean up a lot. It does not move the median much. For anomaly detection, the median is a steadier description of usual spend. If I used the mean, a large transaction could raise the customer's own threshold and make the next large transaction harder to catch.

### Rule-based risk scoring

Each rule is a yes/no condition. If it fires, I add its points. The score is capped at 100. The risk level uses fixed cutoffs.

The reason for separate rule columns is simple: a reviewer and Power BI can see which rule caused the alert. A single combined score would hide that.

### Sliding windows for bursts and failures

A burst is not just "many transactions in one hour". It is many transactions close together. For each customer, I sort the timestamps, try each row as a window start, and move the end forward while the gap stays inside the window. If the block is large enough, I mark every row in it.

The frequency rule uses a 60-minute window and a minimum count of 5. The repeated-failure rule uses a 30-minute window and a minimum count of 3 failed rows.

### GROUP BY and HAVING

`GROUP BY` puts rows into groups. `HAVING` filters the groups after aggregation.

Query 3 groups by customer and hour:

```sql
SELECT Customer_ID,
       strftime('%Y-%m-%d %H', Transaction_Time) AS Hour_Bucket,
       COUNT(*) AS Transaction_Count
FROM transactions
GROUP BY Customer_ID, strftime('%Y-%m-%d %H', Transaction_Time)
HAVING COUNT(*) >= 5;
```

`WHERE` filters individual rows before grouping. `HAVING` filters the groups after `COUNT`, `SUM` or `AVG`.

### Subqueries

A subquery is a query inside another query. Query 6 uses a correlated subquery:

```sql
WHERE t.Amount > 3 * (
    SELECT AVG(t2.Amount)
    FROM transactions AS t2
    WHERE t2.Customer_ID = t.Customer_ID
)
```

The inner query calculates the average for the current customer. The outer query compares each transaction with that customer's average.

### Window functions and LAG

A window function calculates a value across related rows without collapsing them into one row. `LAG` looks at a previous row.

Query 7 partitions by `Customer_ID` and orders by time. For each transaction, `LAG` returns the previous transaction time for the same customer. `julianday` converts both timestamps to day numbers, so the difference times 24 times 60 gives minutes.

This is a SQL demonstration. The Python detector uses its own window marking because it needs to flag every row inside a qualifying burst, not only calculate a gap.

### CASE

`CASE` works like an if/else chain. Query 8 puts each amount into a band:

- Under 1k
- 1k-10k
- 10k-50k
- 50k+

The exact boundaries are 1,000, 10,000 and 50,000. I use the same labels in the Python `Amount_Band` column.

### JOIN

A join combines rows from two tables using a matching key. Query 9 joins `transactions` to `customer_profile` on `Customer_ID`. Each transaction then appears next to the customer's average and home city.

Query 5 joins `transactions` to `scored_transactions` on `Transaction_ID`. That is why the scoring table has to be filled before the query runs.

### Precision and recall with this project's numbers

The confusion matrix from the final run:

- True positives: 375
- False positives: 330
- False negatives: 25
- True negatives: 9,270

Precision asks: of the rows I flagged, how many were really injected?

```text
precision = TP / (TP + FP)
          = 375 / (375 + 330)
          = 0.5319
          = 53.19%
```

Recall asks: of the injected rows, how many did I flag?

```text
recall = TP / (TP + FN)
       = 375 / (375 + 25)
       = 0.9375
       = 93.75%
```

F1 balances the two:

```text
F1 = 2 * precision * recall / (precision + recall)
   = 0.6787
   = 67.87%
```

A high recall with lower precision means the rules catch most planted cases but send many normal rows to review. That is a queue problem, not a proof of fraud.

### Why this validation is circular

I wrote the generator and the rules. The generator puts bursts in tight windows, and the frequency rule looks for tight windows. The validation shows that the rule finds my planted bursts. It does not show that real bursts look the same.

A fair test would use real labels and a time-based split. I would fit or choose thresholds on older data and test on later data. I would also ask analysts to review a sample and record their decisions.

### Flag vs fraud

A flag means "a person should review this". It is not a fraud label. Many flagged rows are normal travel or normal large purchases. A missed fraud is possible too. The dashboard and README use the word "review" instead of "fraud" for this reason.

## A good reading order

1. `README.md`
2. `python/generate_data.py`
3. `python/data_cleaning.py`
4. `sql/schema.sql`
5. `python/build_db.py`
6. `python/anomaly_detection.py`
7. `sql/analysis_queries.sql`
8. `python/run_sql.py`
9. `tests/test_pipeline.py`
10. `reports/validation_results.txt`

Read `POWERBI_GUIDE.md` after that. It is a guide, not a verified dashboard.

## Questions I should be able to answer

- Why is the ground truth a separate file?
- Why does cleaning happen before database loading?
- Why is the customer median used instead of the global average?
- What is the difference between `WHERE` and `HAVING`?
- What does `LAG` do in Query 7?
- Why does the score cap exist?
- Why can precision be lower than recall here?
- Why is the validation circular?
- Why is a flag not a fraud label?
- Why are there two different burst checks, one in SQL and one in Python?
