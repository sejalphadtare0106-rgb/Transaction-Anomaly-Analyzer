# Interview Notes

These are my own short answers. I should only say them if I can point to the code or the generated output.

## 60-second explanation

I built a transaction review pipeline on 10,000 synthetic bank transactions from 300 customers over 90 days. I planted 400 anomalies of five types: high amount, rapid bursts, unusual cities, night timing and repeated failures. I wrote five fixed rules in Python. Each rule looks at the customer's own history, adds points when it fires, and writes a plain-English reason. The output is a CSV review queue and a SQLite table with a risk score from 0 to 100. In the final run the rules flagged 705 rows. They found 375 of the 400 planted anomalies, with precision 53.19 percent, recall 93.75 percent and F1 67.87 percent. The validation is circular because I wrote both the generator and the rules, so it shows recovery of planted patterns, not real fraud performance. A flag means needs review, never proven fraud.

## Q1. Why rules instead of machine learning?

I did not have real fraud labels. The data is synthetic and I planted the patterns myself. A model would look more advanced, but it would only learn my generator. With five rules I can explain every alert, and an interviewer or analyst can check the logic.

Rules also made the project testable. I could write tests for the score cap and risk boundaries, and I could show the exact reason for each flag.

## Q2. Isn't your validation circular?

Yes. I generated the anomalies and then wrote rules that look for those same patterns. The validation checks that the pipeline recovers what was planted. It does not prove that these rules would catch real fraud or that the scores are real probabilities.

I kept this in the README, the report and the validation file on purpose. The honest claim is that the rules work as expected on this synthetic data.

## Q3. Why median instead of average?

A customer's average is pulled up by one very large transaction. If I use the average, that same transaction raises the bar for what counts as unusual next time. The median is less affected by extreme values, so it is a better picture of the customer's usual spend.

I compute the median from the customer's successful transactions only. Failed attempts still count for the repeated-failure rule and the frequency rule.

## Q4. How would you reduce false positives?

First, I would add human review labels. Then I could check which alerts analysts accept or reject and tune with evidence instead of guessing.

For this dataset, the high-amount rule is the main source. I would test a higher multiple or a stricter floor for low-spend customers. I would also handle travel explicitly, for example by marking a travel window, because normal travel causes the location false positives. Another option is to require two rules for an alert, but that would increase false negatives.

## Q5. How would this change with real data?

I would need a longer history per customer, account and device details, and verified travel records. I would also need labels for past fraud cases. The class balance would be much more uneven than 4 percent.

I would split by time, not randomly, because real deployment uses past data to score future transactions. I would not reuse these thresholds without testing on that setup. The current score would become one input into a review process, not a fraud decision.

## Q6. What is the precision and recall trade-off here?

At the current settings I flagged 705 rows. I got 375 true positives, 330 false positives and 25 false negatives. Precision is 53.19 percent and recall is 93.75 percent.

If I made the rules stricter, I would reduce false positives but miss more planted anomalies. If I made them looser, I would catch more but send more normal rows to review. For a review queue, recall matters because a missed case has no chance to be reviewed, but the team can only handle a limited queue. The right point depends on analyst capacity and the cost of a miss.

## Q7. SQLite versus MySQL?

SQLite is a single local file with no server. It is built into Python, which made setup easy. MySQL is a server database with users, permissions, concurrency and stronger production tooling.

The SQL is close, but the date functions differ. I used `strftime` and `julianday` in SQLite. MySQL would use `DATE_FORMAT` and `TIMESTAMPDIFF`. The `LAG` window function works in both, but MySQL needs version 8 or later. Loading a CSV also differs: I used Python with SQLite, while MySQL has `LOAD DATA INFILE`.

## Q8. What does your window function do?

Query 7 uses `LAG` grouped by customer and ordered by time. For each transaction it looks at the previous transaction for that same customer and calculates the minutes between them. That gives a gap column.

I used it as a SQL practice query. The detector itself uses a Python sliding-window check for the frequency and failure rules, because I needed to mark every row inside a qualifying window, not just compute a gap. I can explain both.

## Q9. What would you add next?

I would add an analyst review field with values such as confirmed fraud, normal, or needs more information. That would give me a real label to evaluate. Then I would build a time-based test and compare the rules with a simple baseline.

On the dashboard side I would add a proper date table and screenshots. I would also consider a small set of behavioural features from longer history. I would not add machine learning until I had labels and a fair split.

## Q10. Why did you use a 5,000 INR floor?

Without a floor, a customer whose usual amount is 500 INR could be flagged for a normal 2,000 INR transaction. A 4x jump looks large in ratio terms but may be small in rupees.

The floor has a cost. Seven of my eight missed high-amount rows were below 5,000 INR. I kept the rule because it reduces noise for low-spend customers, but I would test a customer-specific floor with real data.

## Q11. How did you handle messy data?

The raw file had 10,038 rows. I removed 30 exact duplicates and dropped 8 extra rows that were missing a critical field. I filled 30 missing locations and 40 missing merchant categories with `Unknown`, not a guess. I converted 10 amount values stored with commas or a rupee sign, and parsed 100 day-first timestamps mixed with ISO dates. The clean file has 10,000 rows.

I did not silently throw away missing locations. The detector skips `Unknown` for the city rule because missing data is not evidence of an unusual city.

## Q12. What does the Risk_Score mean?

It is the sum of rule points, capped at 100. High Amount gives 30, Unusual City gives 25, High Frequency gives 20, Repeated Failures gives 20 and Night Timing gives 15. The risk level follows fixed boundaries.

It is a review priority, not a probability. A score of 60 does not mean a 60 percent chance of fraud. A flag means a person should look at the transaction. The score is illustrative because the rules and the data are both mine.

## Before an interview

I should read `LEARN.md`, `anomaly_detection.py`, all ten SQL queries and the validation output. I should also be ready to explain why high amount caused most of the 330 false positives and why 25 planted rows were missed. I should not describe the Power BI dashboard as finished until I have actually built and checked it.
