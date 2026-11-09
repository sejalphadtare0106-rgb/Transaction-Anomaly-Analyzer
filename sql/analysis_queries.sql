-- Ten SQL practice queries for the Transaction Anomaly Analyzer.
-- Query 5 joins scored_transactions. Run anomaly_detection.py before Query 5.
-- The other queries use the transactions and customer_profile tables.

-- Query 1: Which 20 transactions have the highest amounts?
SELECT
    Transaction_ID,
    Customer_ID,
    Amount,
    Transaction_Time,
    Location,
    Transaction_Type,
    Status
FROM transactions
ORDER BY Amount DESC, Transaction_ID
LIMIT 20;

-- Query 2: Which 10 customers have the most transactions?
SELECT
    Customer_ID,
    COUNT(*) AS Transaction_Count
FROM transactions
GROUP BY Customer_ID
ORDER BY Transaction_Count DESC, Customer_ID
LIMIT 10;

-- Query 3: Which customer-hour groups contain at least 5 transactions (possible bursts)?
SELECT
    Customer_ID,
    strftime('%Y-%m-%d %H', Transaction_Time) AS Hour_Bucket,
    COUNT(*) AS Transaction_Count,
    ROUND(SUM(Amount), 2) AS Total_Value
FROM transactions
GROUP BY Customer_ID, strftime('%Y-%m-%d %H', Transaction_Time)
HAVING COUNT(*) >= 5
ORDER BY Transaction_Count DESC, Customer_ID
LIMIT 20;

-- Query 4: How much activity and value happens in each location?
SELECT
    Location,
    COUNT(*) AS Transaction_Count,
    ROUND(SUM(Amount), 2) AS Total_Value
FROM transactions
GROUP BY Location
ORDER BY Total_Value DESC, Location;

-- Query 5: How many transactions were flagged, and what value do they represent?
SELECT
    COUNT(*) AS Flagged_Transactions,
    ROUND(SUM(t.Amount), 2) AS Flagged_Value
FROM transactions AS t
JOIN scored_transactions AS s
    ON s.Transaction_ID = t.Transaction_ID
WHERE s.Is_Flagged = 1;

-- Query 6: Which transactions are more than 3 times their customer's average amount?
SELECT
    t.Transaction_ID,
    t.Customer_ID,
    t.Amount,
    ROUND(
        (SELECT AVG(t2.Amount) FROM transactions AS t2
         WHERE t2.Customer_ID = t.Customer_ID),
        2
    ) AS Customer_Average,
    t.Location,
    t.Transaction_Time
FROM transactions AS t
WHERE t.Amount > 3 * (
    SELECT AVG(t2.Amount) FROM transactions AS t2
    WHERE t2.Customer_ID = t.Customer_ID
)
ORDER BY t.Amount DESC, t.Transaction_ID
LIMIT 20;

-- Query 7: How many minutes passed since the same customer's previous transaction?
WITH transaction_lag AS (
    SELECT
        Transaction_ID,
        Customer_ID,
        Transaction_Time,
        LAG(Transaction_Time) OVER (
            PARTITION BY Customer_ID
            ORDER BY Transaction_Time
        ) AS Previous_Transaction_Time
    FROM transactions
)
SELECT
    Transaction_ID,
    Customer_ID,
    Transaction_Time,
    ROUND(
        (julianday(Transaction_Time) - julianday(Previous_Transaction_Time)) * 24 * 60,
        2
    ) AS Minutes_Since_Previous
FROM transaction_lag
WHERE Previous_Transaction_Time IS NOT NULL
ORDER BY Minutes_Since_Previous DESC, Transaction_ID
LIMIT 30;

-- Query 8: How many transactions fall into each amount band?
WITH banded AS (
    SELECT
        CASE
            WHEN Amount < 1000 THEN 'Under 1k'
            WHEN Amount < 10000 THEN '1k-10k'
            WHEN Amount < 50000 THEN '10k-50k'
            ELSE '50k+'
        END AS Amount_Band
    FROM transactions
)
SELECT
    Amount_Band,
    COUNT(*) AS Transaction_Count
FROM banded
GROUP BY Amount_Band
ORDER BY CASE Amount_Band
    WHEN 'Under 1k' THEN 1
    WHEN '1k-10k' THEN 2
    WHEN '10k-50k' THEN 3
    ELSE 4
END;

-- Query 9: How does each transaction compare with its customer's overall profile?
SELECT
    t.Transaction_ID,
    t.Customer_ID,
    t.Amount,
    p.Average_Amount AS Customer_Average,
    ROUND(t.Amount - p.Average_Amount, 2) AS Amount_Difference,
    t.Location,
    p.Home_City,
    p.Transaction_Count
FROM transactions AS t
JOIN customer_profile AS p
    ON p.Customer_ID = t.Customer_ID
ORDER BY ABS(t.Amount - p.Average_Amount) DESC, t.Transaction_ID
LIMIT 20;

-- Query 10: Which 10 customers have the most failed transactions?
SELECT
    Customer_ID,
    COUNT(*) AS Failed_Count,
    ROUND(SUM(Amount), 2) AS Failed_Value
FROM transactions
WHERE Status = 'Failed'
GROUP BY Customer_ID
ORDER BY Failed_Count DESC, Customer_ID
LIMIT 10;
