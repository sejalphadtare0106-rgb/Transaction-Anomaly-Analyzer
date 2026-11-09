# Findings Summary

I generated 10,000 synthetic transactions for 300 customers over 90 days and planted 400 anomalies. I then scored every row with five fixed rules and compared the flags with the hidden answer key.

All numbers here come from `reports/validation_results.txt` and the final pipeline run. The data is synthetic. A flag means "needs review", never "proven fraud". The Risk_Score is an illustrative rules-based score, not a fraud probability.

## Detection result

The rules flagged 705 rows, which is 7.05 percent of the file.

| Outcome | Count |
|---|---:|
| True positives | 375 |
| False positives | 330 |
| False negatives | 25 |
| True negatives | 9,270 |

- Precision: 53.19%
- Recall: 93.75%
- F1: 67.87%

The high recall is partly a result of the test design: I planted patterns that the rules were built to find. The precision number is more useful for showing the cost of the simple rules, because 330 normal rows were sent to review.

## Recall by planted type

| Injected type | Detected / injected | Recall |
|---|---:|---:|
| High Amount | 75 / 83 | 90.36% |
| Burst | 111 / 111 | 100.00% |
| Unusual City | 62 / 77 | 80.52% |
| Night Timing | 63 / 65 | 96.92% |
| Repeated Failures | 102 / 102 | 100.00% |

Bursts and repeated failures were easiest because the generator makes tight clusters and the rules look for tight clusters. Unusual city was the weakest type. Fifteen planted unusual-city rows had a city share of at least 5 percent, usually because the customer had a short history or had visited that city more than once.

The 25 misses did not come from a broken rule. Seven high-amount rows were below the INR 5,000 floor. One high-amount row was 2.88 times the observed median. All 15 unusual-city misses were at or above the 5 percent city-share cutoff. The two night misses came from customers with 9 and 10 successful transactions, so one night row was at least 10 percent of their history.

## False positives

The 330 false positives by exact rule combination:

| Rule combination | Count |
|---|---:|
| High Amount only | 250 |
| Unusual City only | 76 |
| High Frequency only | 3 |
| High Amount + Unusual City | 1 |

The high-amount rule is the main source. The data includes legitimate large purchases at 4 to 8 times a customer's median, and the normal lognormal distribution also has a long upper tail. The unusual-city rule catches normal travel. The three frequency false positives are ordinary rows that happened to sit in a busy 60-minute window.

The timing rule and the repeated-failure rule had no false positives. Genuine night owls have a high night share and are not flagged for timing alone. Normal failed transactions were kept isolated in the generator.

## Score and value

The flagged rows have an average Risk_Score of 28.28. There are 10 High, 389 Medium, 306 Low and 9,295 None rows. High is a small group because a single rule gives at most 30 points, so a row needs at least two rules to reach 60.

The flagged value is INR 8,530,549.33 out of INR 35,766,771.47 in total transaction value. The flag file is a review queue, not a list of confirmed fraud cases.

## What I take from this

The simple rules recover most of the planted patterns and give a reason for every flag. The cost is a large normal-review queue: 330 of the 705 flagged rows are false positives. The weakest areas are high-amount false positives from normal large spend and location misses for customers with short histories.

The next improvement would be a human review label on each flagged row, so I could measure whether analysts agree with the flags. After that I could test tighter thresholds or a second look at repeat travel. I would not claim better real-world performance from this synthetic test.

The Power BI dashboard is the remaining manual part. The guide is written, but I did not open Power BI Desktop in this environment.
