# Power BI Dashboard Guide

**Written but not verified in Power BI Desktop. Power BI Desktop runs on Windows only.**

I wrote these steps from the CSV design, but I could not open Power BI Desktop in this environment. The Python pipeline and all four CSV files were executed and checked. The dashboard itself is still your manual step.

A flag means "needs review". It does not prove fraud. The Risk_Score is an illustrative rules-based score, not a validated fraud probability.

## Files to load

Load these four files from `dashboard/data/`:

| Query name in Power BI | File | Rows |
|---|---|---:|
| `all_transactions_scored` | `all_transactions_scored.csv` | 10,000 |
| `flagged_transactions` | `flagged_transactions.csv` | 705 |
| `flag_summary` | `flag_summary.csv` | 5 |
| `daily_summary` | `daily_summary.csv` | 90 |

Do not load `dataset/ground_truth.csv` into Power BI. It is only for the validation step. The four dashboard files were checked and contain no `Is_Injected_Anomaly` or `Injected_Type` column.

The row counts above are from the last Python run, not from Power BI.

## Step 1: Load one CSV

1. Open Power BI Desktop.
2. Select **Home > Get Data > Text/CSV**.
3. Select `dashboard/data/all_transactions_scored.csv`.
4. Check that the preview shows columns, not one long text column.
5. Select **Transform Data**. Do not select **Load** yet.
6. In Power Query, right-click each column header and set the data type:
   - `Transaction_ID`: Text
   - `Customer_ID`: Text
   - `Amount`: Decimal Number
   - `Transaction_Time`: Date/Time
   - `Location`: Text
   - `Transaction_Type`: Text
   - `Merchant_Category`: Text
   - `Status`: Text
   - `Date`: Date
   - `Hour`: Whole Number
   - `Day_Of_Week`: Text
   - `Amount_Band`: Text
   - `Customer_Median_Amount`: Decimal Number
   - `Risk_Score`: Whole Number
   - `Risk_Level`: Text
   - `Is_Flagged`: Whole Number
   - `Flag_Reasons`: Text
   - `Flag_Count`: Whole Number
   - `Flag_High_Amount`: Whole Number
   - `Flag_High_Frequency`: Whole Number
   - `Flag_Location`: Whole Number
   - `Flag_Timing`: Whole Number
   - `Flag_Failures`: Whole Number
7. If a numeric column fails to convert, use **Using Locale > English (United States)**. The CSV uses a dot decimal separator and `YYYY-MM-DD` dates.
8. Select **Home > Close & Apply**.
9. In the Data pane, check that the table is named `all_transactions_scored`. If Power BI added a different name, either rename it or change the table names in the DAX measures below.

Repeat these steps for the other three files.

### Type checks for the other tables

`flagged_transactions.csv` has the same columns as `all_transactions_scored`, so use the same types.

For `flag_summary.csv`:

- `Flag_Type`: Text
- `Count`: Whole Number
- `Total_Value`: Decimal Number

For `daily_summary.csv`:

- `Date`: Date
- `Total_Transactions`: Whole Number
- `Flagged_Count`: Whole Number
- `Total_Value`: Decimal Number
- `Flagged_Value`: Decimal Number
- `High_Count`: Whole Number
- `Medium_Count`: Whole Number
- `Low_Count`: Whole Number

## Step 2: Relationships

No relationships are required for this guide.

Each visual reads one CSV table. Page 2 slicers are columns from `flagged_transactions`, and the Page 2 table also uses `flagged_transactions`. That means the slicers filter the table without a relationship.

This has a limit: a slicer from `flagged_transactions` will not filter a visual built from another table. Do not mix tables on Page 2 unless you add and check a relationship. I kept the model simple.

Do not create a relationship between `all_transactions_scored` and `flagged_transactions` by `Transaction_ID` unless you need it. It is redundant because the second table is already a filtered copy of the first.

## Step 3: Add the DAX measures

Create these measures on the `all_transactions_scored` table. Right-click the table in the Data pane and select **New measure**. Paste one block at a time.

```DAX
// Count every scored transaction.
Total Transactions = COUNTROWS(all_transactions_scored)
```

```DAX
// Count transactions where at least one rule fired.
Flagged Count =
CALCULATE(
    COUNTROWS(all_transactions_scored),
    all_transactions_scored[Is_Flagged] = 1
)
```

```DAX
// Share of all transactions that were flagged.
Flagged % =
DIVIDE(
    [Flagged Count],
    [Total Transactions],
    0
)
```

```DAX
// Sum of all transaction amounts in INR.
Total Value = SUM(all_transactions_scored[Amount])
```

```DAX
// Sum of amounts for flagged transactions only.
Flagged Value =
CALCULATE(
    SUM(all_transactions_scored[Amount]),
    all_transactions_scored[Is_Flagged] = 1
)
```

```DAX
// Share of total value that sits in flagged transactions.
Flagged Value % =
DIVIDE(
    [Flagged Value],
    [Total Value],
    0
)
```

```DAX
// Number of transactions at High risk level.
High Risk Count =
CALCULATE(
    COUNTROWS(all_transactions_scored),
    all_transactions_scored[Risk_Level] = "High"
)
```

```DAX
// Number of transactions at Medium risk level.
Medium Risk Count =
CALCULATE(
    COUNTROWS(all_transactions_scored),
    all_transactions_scored[Risk_Level] = "Medium"
)
```

```DAX
// Number of transactions at Low risk level.
Low Risk Count =
CALCULATE(
    COUNTROWS(all_transactions_scored),
    all_transactions_scored[Risk_Level] = "Low"
)
```

```DAX
// Average score among flagged rows only.
Avg Risk Score of Flagged =
CALCULATE(
    AVERAGE(all_transactions_scored[Risk_Score]),
    all_transactions_scored[Is_Flagged] = 1
)
```

```DAX
// Number of failed transactions.
Failed Transactions =
CALCULATE(
    COUNTROWS(all_transactions_scored),
    all_transactions_scored[Status] = "Failed"
)
```

After creating them, set these formats:

- `Total Transactions`: Whole Number, thousands separator.
- `Flagged Count`: Whole Number, thousands separator.
- `Flagged %`: Percentage, 2 decimal places.
- `Total Value`: Decimal Number, 2 decimals, thousands separator, INR prefix if you want.
- `Flagged Value`: Decimal Number, 2 decimals, thousands separator.
- `Flagged Value %`: Percentage, 2 decimal places.
- `High Risk Count`, `Medium Risk Count`, `Low Risk Count`: Whole Number.
- `Avg Risk Score of Flagged`: Decimal Number, 2 decimals.
- `Failed Transactions`: Whole Number.

The measures return these source-data totals when no filters are applied:

- Total Transactions: 10,000
- Flagged Count: 705
- Flagged %: 7.05%
- Total Value: 35,766,771.47
- Flagged Value: 8,530,549.33
- High Risk Count: 10
- Medium Risk Count: 389
- Low Risk Count: 306
- Avg Risk Score of Flagged: 28.28

These totals are from `reports/validation_results.txt` and the generated CSVs. They are not a check made inside Power BI Desktop.

## Page 1: Overview

Rename the page to **Overview**.

### Layout sketch

```text
+--------------------------------------------------------------------------------+
| Transaction Anomaly & Fraud Pattern Analyzer          Flags mean review, not fraud |
+--------------------------------------------------------------------------------+
| [Total Transactions] [Flagged Count] [Flagged %] [Total Value] [Flagged Value]   |
+------------------------------------------------------+-------------------------+
| Daily transactions vs flagged transactions           | Risk Level              |
| line chart                                           | donut or bar             |
|                                                      |                         |
+------------------------------------------------------+-------------------------+
| Flags by type (rule)                 | Location activity                        |
| horizontal bar                       | horizontal bar                           |
+--------------------------------------+------------------------------------------+
| Small note: synthetic data. Scores are illustrative, not fraud probabilities.    |
+--------------------------------------------------------------------------------+
```

### Add the visuals

1. Add five **Card** visuals across the top.
   - Card 1: `[Total Transactions]`
   - Card 2: `[Flagged Count]`
   - Card 3: `[Flagged %]`
   - Card 4: `[Total Value]`
   - Card 5: `[Flagged Value]`
2. Add a **Line chart** under the cards.
   - X-axis: `daily_summary[Date]`
   - Y-axis: `daily_summary[Total_Transactions]` and `daily_summary[Flagged_Count]`
   - Title: `Daily transactions and flags`
   - Set the date axis type to Date. If Power BI treats it as text, the line will look wrong.
3. Add a **Donut chart** to the right of the line chart.
   - Legend: `all_transactions_scored[Risk_Level]`
   - Values: `[Total Transactions]`
   - Add a visual-level filter: `Is_Flagged is 1`. Without this filter, the None group has 9,295 rows and dominates the chart.
   - Title: `Risk level of flagged rows`
4. Add a **Clustered bar chart** under the donut.
   - Axis: `flag_summary[Flag_Type]`
   - Values: `flag_summary[Count]`
   - Title: `Flags by rule`
   - Add data labels.
   - Note: these counts overlap. One transaction can trigger more than one rule, so they do not add up to 705.
5. Add a **Clustered bar chart** at the bottom.
   - Axis: `all_transactions_scored[Location]`
   - Values: `[Total Transactions]`
   - Title: `Transactions by location`
   - Keep the `Unknown` city if you want to show missing values honestly. Do not replace it with a guessed city.
6. Add a text box at the bottom:
   - `Synthetic data. Risk scores are illustrative rules-based scores, not validated fraud probabilities. A flag means needs review, not proven fraud.`

## Page 2: Investigation

Add a new page and rename it **Investigation**.

### Layout sketch

```text
+--------------------------------------------------------------------------------+
| Investigation                                    Flags mean review, not fraud     |
+--------------------------------------------------------------------------------+
| Slicers: [Date range] [Location] [Transaction Type] [Risk Level]                |
+--------------------------------------------------------------------------------+
| Transaction_ID | Time | Customer | Amount | Location | Risk_Score | Reasons     |
| ------------------------------------------------------------------------------ |
| TXN...         | ...  | CUST...  | ...    | ...      | 55         | ...          |
| ...                                                                            |
|                                                                                |
+--------------------------------------------------------------------------------+
| Note: synthetic data, score is not a probability.                               |
+--------------------------------------------------------------------------------+
```

### Add the slicers

Add four **Slicer** visuals from `flagged_transactions`:

1. `Date`
   - Use a range slicer or a dropdown. Make sure the data type is Date.
2. `Location`
   - Use a dropdown.
3. `Transaction_Type`
   - Use a dropdown.
4. `Risk_Level`
   - Use a dropdown or tiles.

All four fields must come from `flagged_transactions`, not `all_transactions_scored`. With no relationships, a slicer only filters visuals from its own table.

### Add the table

1. Add a **Table** visual.
2. Use `flagged_transactions`.
3. Add these fields in this order:
   - `Transaction_ID`
   - `Transaction_Time`
   - `Customer_ID`
   - `Amount`
   - `Location`
   - `Transaction_Type`
   - `Merchant_Category`
   - `Risk_Score`
   - `Risk_Level`
   - `Flag_Reasons`
4. Turn on word wrap for `Flag_Reasons` so long reasons are readable.
5. Format `Amount` as a decimal number with two places. Format `Transaction_Time` as date and time.
6. Set the table filter to `Is_Flagged is 1` if the table ever shows unflagged rows. The CSV already contains only flagged rows, so this should not be needed.

### Conditional formatting for Risk_Score

The exact labels in the Format pane can change between Power BI versions. Look for these controls:

1. Select the table visual.
2. Open the **Format visual** pane.
3. Find **Cell elements**.
4. Set **Apply settings to** to `Risk_Score`.
5. Turn on **Background color**.
6. Select the **fx** button.
7. Choose **Rules** and **Number** as the rule type.
8. Add rules:
   - If value is greater than or equal to 60, use red.
   - If value is greater than or equal to 30 and less than 60, use amber.
   - If value is greater than or equal to 1 and less than 30, use light yellow.
9. Apply the rules.

The table is already sorted by Risk_Score descending because the CSV was written that way. You can also sort the visual by `Risk_Score` descending.

### Add a count card

Add a card with `[Flagged Count]` if you want a quick count at the top. It uses the scored table, so it will not respond to the Page 2 slicers from `flagged_transactions`. Label it `Flagged count (all data)` to avoid confusion.

## SQLite and Power BI do not talk to each other here

The SQLite database is for the SQL practice part. Power BI reads the four CSV files. Do not point Power BI at `dataset/transactions.db` for this version.

## Common problems

### Amount or Risk_Score is text

The column type was not converted. Go back to **Transform Data**, set the type to Decimal Number or Whole Number, and use **Using Locale** if the preview still shows errors.

### Date is text and the line chart is wrong

Set `Date` to Date in Power Query. `Transaction_Time` can be Date/Time. The CSV has `YYYY-MM-DD` dates, so English (United States) locale is a safe choice for these files.

### Slicers do not filter the table

Check the field source. A slicer from `all_transactions_scored` will not filter a visual built from `flagged_transactions` unless there is a relationship. Page 2 should use one table only.

### Flagged % shows a decimal instead of a percentage

The measure format is not set to percentage. Select the measure in the Data pane, open Format, and choose Percentage with 2 decimal places. The source value for the full file is 7.05%.

### The None group makes the Risk_Level chart useless

Add the visual-level filter `Is_Flagged is 1` to that chart. There are 9,295 rows with Risk_Level None in the full scored file.

### Flags by rule do not add to total flags

A transaction can trigger more than one rule. Use `Flagged Count` for the number of flagged transactions, and use `flag_summary` only for the per-rule view.

### Data looks stale after rerunning Python

Select **Home > Refresh**. Power BI keeps the old values until it re-reads the CSVs.

### The dashboard shows different totals from the README

Check filters first. Then check data types. The unfiltered source totals should match the values listed above. If they do not, rerun `python/run_all.py` and refresh Power BI.

## Final check list

- Four CSV tables are loaded.
- `ground_truth.csv` is not loaded.
- `Amount` is decimal, `Date` is date, `Hour` and all flag columns are whole numbers.
- No relationships are used, and every visual uses fields from one table.
- Page 1 has the five cards, daily line chart, risk chart, flags-by-rule chart and location chart.
- Page 2 has the flagged table and four slicers from `flagged_transactions`.
- Both pages have a short note that flags need review and scores are illustrative.
- You took screenshots and added them to the README after checking the actual dashboard.
