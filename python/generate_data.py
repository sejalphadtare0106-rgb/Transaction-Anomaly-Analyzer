"""
Generate a reproducible synthetic transaction dataset.

The output is deliberately messy so that data_cleaning.py has real work to do.
The ground truth file is separate and is only used later for validation.
Everything here is synthetic. No real customer or bank data is used.
"""

from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Fixed configuration
# ---------------------------------------------------------------------------
SEED = 42
N_TRANSACTIONS = 10_000
N_CUSTOMERS = 300
START_DATE = date(2026, 8, 1)
END_DATE = date(2026, 10, 29)
N_DAYS = (END_DATE - START_DATE).days + 1

CITIES = [
    "Mumbai",
    "Delhi",
    "Bengaluru",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Pune",
    "Ahmedabad",
]
CITY_WEIGHTS = np.array([0.20, 0.16, 0.14, 0.11, 0.10, 0.09, 0.11, 0.09])

TRANSACTION_TYPES = ["Transfer", "Payment", "Withdrawal"]
PAYMENT_CATEGORIES = [
    "Groceries",
    "Fuel",
    "Dining",
    "Online Shopping",
    "Utilities",
    "Travel",
    "Healthcare",
    "Entertainment",
]

NORMAL_FAILURE_RATE = 0.025       # about 2.5% of normal transactions fail
TRAVEL_RATE = 0.01                # 1% of normal transactions happen while travelling
LARGE_PURCHASE_RATE = 0.007       # 0.7% are legitimate large purchases
NIGHT_OWL_SHARE = 0.10            # 10% of customers often transact after midnight

TARGET_ANOMALY_ROWS = 400         # 4.0% of 10,000
BURST_EVENTS = 12
FAILURE_EVENTS = 22
COMBINED_EVENT_SHARE = 0.15       # 15% of injected events combine two types

# Raw-data problems. These are extra rows/edits, not detector inputs.
N_DUPLICATE_ROWS = 30             # about 0.3%
N_JUNK_ROWS = 8                   # extra rows with missing critical fields
N_NULL_MERCHANT = 40
N_NULL_LOCATION = 30
N_MIXED_TIMESTAMPS = 100
N_MESSY_CATEGORIES = 60
N_TEXT_AMOUNTS = 10

DATASET_DIR = Path(__file__).resolve().parents[1] / "dataset"
RAW_PATH = DATASET_DIR / "transactions_raw.csv"
GROUND_TRUTH_PATH = DATASET_DIR / "ground_truth.csv"


def build_profiles(rng: np.random.Generator) -> list[dict]:
    """Create one hidden behaviour profile per customer."""
    # Pick exactly 30 night-owl customers so the 10% share is easy to check.
    night_owl_indices = set(
        rng.choice(N_CUSTOMERS, size=int(N_CUSTOMERS * NIGHT_OWL_SHARE), replace=False).tolist()
    )

    # Customer frequency weights are unequal. The multinomial call below turns
    # them into transaction counts that add up to N_TRANSACTIONS.
    frequency_weights = rng.lognormal(mean=0.0, sigma=0.55, size=N_CUSTOMERS)
    counts = rng.multinomial(N_TRANSACTIONS, frequency_weights / frequency_weights.sum())

    profiles = []
    for i in range(N_CUSTOMERS):
        home_city = str(rng.choice(CITIES, p=CITY_WEIGHTS / CITY_WEIGHTS.sum()))
        median_amount = float(np.exp(rng.uniform(np.log(400), np.log(9_000))))

        # Pick two or three preferred payment categories.
        preferred = rng.choice(PAYMENT_CATEGORIES, size=3, replace=False)
        category_weights = np.array(
            [3.0 if category in preferred else 1.0 for category in PAYMENT_CATEGORIES]
        )
        category_weights = category_weights / category_weights.sum()

        transaction_mix = rng.dirichlet([5.0, 3.0, 1.3])

        is_night_owl = i in night_owl_indices
        if is_night_owl:
            # Night owls have an evening window plus a lot of activity from
            # midnight to 4:59 AM.
            active_start = int(rng.integers(18, 21))
            active_end = 23
            peak_hour = int(rng.integers(21, 24))
        else:
            active_start = int(rng.integers(7, 11))
            active_end = int(rng.integers(19, 24))
            peak_low = max(active_start + 2, 12)
            peak_high = min(active_end - 1, 21)
            peak_hour = int(rng.integers(peak_low, peak_high + 1))

        profiles.append(
            {
                "Customer_ID": f"CUST{i + 1:03d}",
                "home_city": home_city,
                "median_amount": median_amount,
                "amount_sigma": float(rng.uniform(0.45, 0.75)),
                "active_start": active_start,
                "active_end": active_end,
                "peak_hour": peak_hour,
                "night_owl": is_night_owl,
                "transaction_mix": transaction_mix,
                "category_weights": category_weights,
                "target_count": int(counts[i]),
            }
        )
    return profiles


def random_timestamp(rng: np.random.Generator, profile: dict, day: date) -> datetime:
    """Choose a time inside a customer's usual behaviour window."""
    if profile["night_owl"] and rng.random() < 0.60:
        hour = int(rng.integers(0, 5))  # 00:00 to 04:59
    else:
        hours = np.arange(profile["active_start"], profile["active_end"] + 1)
        # A bell shape centred on the personal peak hour.
        weights = np.exp(-0.5 * ((hours - profile["peak_hour"]) / 2.0) ** 2)
        weights = weights / weights.sum()
        hour = int(rng.choice(hours, p=weights))
    minute = int(rng.integers(0, 60))
    second = int(rng.integers(0, 60))
    return datetime.combine(day, time(hour, minute, second))


def random_day(rng: np.random.Generator) -> date:
    return START_DATE + timedelta(days=int(rng.integers(0, N_DAYS)))


def normal_amount(rng: np.random.Generator, profile: dict) -> float:
    """Lognormal amount with the profile's median at its centre."""
    value = rng.lognormal(
        mean=np.log(profile["median_amount"]), sigma=profile["amount_sigma"]
    )
    return round(max(20.0, float(value)), 2)


def payment_category(rng: np.random.Generator, profile: dict) -> str:
    return str(rng.choice(PAYMENT_CATEGORIES, p=profile["category_weights"]))


def make_transaction(
    rng: np.random.Generator,
    profile: dict,
    timestamp: datetime,
    *,
    amount: float | None = None,
    location: str | None = None,
    status: str = "Success",
    injected_type: str = "None",
) -> dict:
    """Build one transaction row using the customer's usual mix."""
    transaction_type = str(
        rng.choice(TRANSACTION_TYPES, p=profile["transaction_mix"])
    )
    if transaction_type == "Transfer":
        category = "P2P Transfer"
    elif transaction_type == "Withdrawal":
        category = "ATM"
    else:
        category = payment_category(rng, profile)

    return {
        "Customer_ID": profile["Customer_ID"],
        "Amount": round(amount, 2) if amount is not None else normal_amount(rng, profile),
        "Transaction_Time": timestamp,
        "Location": location or profile["home_city"],
        "Transaction_Type": transaction_type,
        "Merchant_Category": category,
        "Status": status,
        "Is_Injected_Anomaly": int(injected_type != "None"),
        "Injected_Type": injected_type,
    }


def generate_normal_transactions(
    rng: np.random.Generator, profiles: list[dict]
) -> pd.DataFrame:
    """Generate N_TRANSACTIONS normal rows, then keep failures isolated."""
    rows = []
    for profile in profiles:
        for _ in range(profile["target_count"]):
            timestamp = random_timestamp(rng, profile, random_day(rng))
            amount = normal_amount(rng, profile)

            # A few normal rows look odd on purpose.
            location = profile["home_city"]
            if rng.random() < TRAVEL_RATE:
                other_cities = [city for city in CITIES if city != profile["home_city"]]
                location = str(rng.choice(other_cities))
            if rng.random() < LARGE_PURCHASE_RATE:
                amount = round(profile["median_amount"] * float(rng.uniform(4.0, 8.0)), 2)

            status = "Failed" if rng.random() < NORMAL_FAILURE_RATE else "Success"
            rows.append(
                make_transaction(
                    rng,
                    profile,
                    timestamp,
                    amount=amount,
                    location=location,
                    status=status,
                )
            )

    normal = pd.DataFrame(rows)
    normal = normal.sort_values(["Customer_ID", "Transaction_Time"], kind="mergesort")

    # "Isolated" means no two normal failures close together. Convert a later
    # failure to success if it is within 4 hours of the previous one.
    keep_ids = []
    for _, group in normal.groupby("Customer_ID", sort=False):
        last_failure = None
        for index, row in group.iterrows():
            if row["Status"] != "Failed":
                continue
            if last_failure is None or (row["Transaction_Time"] - last_failure).total_seconds() >= 4 * 3600:
                last_failure = row["Transaction_Time"]
                keep_ids.append(index)
            else:
                normal.at[index, "Status"] = "Success"

    return normal.reset_index(drop=True)


def make_anomaly_rows(
    rng: np.random.Generator, profiles: list[dict]
) -> tuple[pd.DataFrame, dict]:
    """Create the planted anomaly events and return their rows and event stats."""
    # Cluster sizes are random but always inside the specification.
    burst_sizes = [int(value) for value in rng.integers(6, 13, size=BURST_EVENTS)]
    failure_sizes = [int(value) for value in rng.integers(3, 7, size=FAILURE_EVENTS)]
    cluster_row_count = sum(burst_sizes) + sum(failure_sizes)
    single_row_count = TARGET_ANOMALY_ROWS - cluster_row_count

    # Split the remaining single-row anomalies across the three simple types.
    n_high = round(single_row_count * 0.36)
    n_location = round(single_row_count * 0.34)
    n_night = single_row_count - n_high - n_location

    events = []
    for _ in range(n_high):
        events.append({"primary": "High Amount", "size": 1})
    for _ in range(n_location):
        events.append({"primary": "Unusual City", "size": 1})
    for _ in range(n_night):
        events.append({"primary": "Night Timing", "size": 1, "night": True})
    for size in burst_sizes:
        events.append({"primary": "Burst", "size": size})
    for size in failure_sizes:
        events.append({"primary": "Repeated Failures", "size": size, "failures": True})

    # Give every event a customer, date and any combined second type.
    non_night_owl_profiles = [profile for profile in profiles if not profile["night_owl"]]
    for event in events:
        if event.get("night"):
            event["profile"] = non_night_owl_profiles[
                int(rng.integers(0, len(non_night_owl_profiles)))
            ]
        else:
            event["profile"] = profiles[int(rng.integers(0, len(profiles)))]
        event["day"] = random_day(rng)

    n_combined = round(len(events) * COMBINED_EVENT_SHARE)
    combined_indices = rng.choice(len(events), size=n_combined, replace=False)
    for idx in combined_indices:
        event = events[int(idx)]
        candidates = ["High Amount", "Unusual City"]
        if not event["profile"]["night_owl"] and event["primary"] != "Night Timing":
            candidates.append("Night Timing")
        candidates = [name for name in candidates if name != event["primary"]]
        event["secondary"] = str(rng.choice(candidates))

    rows = []
    for event in events:
        profile = event["profile"]
        primary = event["primary"]
        secondary = event.get("secondary")
        tags = [primary] + ([secondary] if secondary else [])
        injected_type = " + ".join(tags)

        if primary in ("Burst", "Repeated Failures"):
            # Put burst/failure clusters in the daytime unless a combined
            # "Night Timing" tag deliberately moves them to 00:00-04:59.
            if "Night Timing" in tags:
                start_hour = int(rng.integers(0, 4))
            else:
                start_hour = int(rng.integers(8, 22))
            start = datetime.combine(
                event["day"],
                time(start_hour, int(rng.integers(0, 60)), int(rng.integers(0, 60))),
            )
            window = 40 if primary == "Burst" else 20
            offsets = np.sort(rng.integers(0, window * 60 + 1, size=event["size"]))
            unusual_city = None
            if "Unusual City" in tags:
                choices = [city for city in CITIES if city != profile["home_city"]]
                unusual_city = str(rng.choice(choices))

            for offset in offsets:
                timestamp = start + timedelta(seconds=int(offset))
                high_amount = None
                if "High Amount" in tags:
                    high_amount = profile["median_amount"] * float(rng.uniform(5.0, 15.0))
                status = "Failed" if primary == "Repeated Failures" else "Success"
                rows.append(
                    make_transaction(
                        rng,
                        profile,
                        timestamp,
                        amount=high_amount,
                        location=unusual_city,
                        status=status,
                        injected_type=injected_type,
                    )
                )
        else:
            # Single-row events. A combined night tag means 00:00-04:59.
            if "Night Timing" in tags:
                timestamp = datetime.combine(
                    event["day"],
                    time(int(rng.integers(0, 5)), int(rng.integers(0, 60)), int(rng.integers(0, 60))),
                )
            else:
                timestamp = random_timestamp(rng, profile, event["day"])

            high_amount = None
            if "High Amount" in tags:
                high_amount = profile["median_amount"] * float(rng.uniform(5.0, 15.0))

            unusual_city = None
            if "Unusual City" in tags:
                choices = [city for city in CITIES if city != profile["home_city"]]
                unusual_city = str(rng.choice(choices))

            rows.append(
                make_transaction(
                    rng,
                    profile,
                    timestamp,
                    amount=high_amount,
                    location=unusual_city,
                    injected_type=injected_type,
                )
            )

    anomaly = pd.DataFrame(rows)
    stats = {
        "event_count": len(events),
        "combined_events": n_combined,
        "burst_rows": sum(burst_sizes),
        "failure_rows": sum(failure_sizes),
        "anomaly_rows": len(anomaly),
    }
    return anomaly, stats


def make_raw_file(
    rng: np.random.Generator, clean_unique: pd.DataFrame
) -> pd.DataFrame:
    """Add dirty values and duplicate rows to create transactions_raw.csv."""
    raw = clean_unique.copy()
    raw["Transaction_Time"] = pd.to_datetime(raw["Transaction_Time"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    all_indices = np.arange(len(raw))

    # Mixed timestamp formats: day-first for a small slice.
    mixed_idx = rng.choice(all_indices, size=N_MIXED_TIMESTAMPS, replace=False)
    for idx in mixed_idx:
        raw.at[idx, "Transaction_Time"] = datetime.strptime(
            raw.at[idx, "Transaction_Time"], "%Y-%m-%d %H:%M:%S"
        ).strftime("%d/%m/%Y %H:%M:%S")

    # Inconsistent casing and stray spaces in category text.
    category_idx = rng.choice(all_indices, size=N_MESSY_CATEGORIES, replace=False)
    for idx in category_idx:
        value = str(raw.at[idx, "Merchant_Category"])
        raw.at[idx, "Merchant_Category"] = f"  {value.upper()}  "

    # Missing merchant/location values. Cleaning fills these, it does not guess.
    merchant_null_idx = rng.choice(all_indices, size=N_NULL_MERCHANT, replace=False)
    raw.loc[merchant_null_idx, "Merchant_Category"] = np.nan
    location_null_idx = rng.choice(all_indices, size=N_NULL_LOCATION, replace=False)
    raw.loc[location_null_idx, "Location"] = np.nan

    # A few amounts are stored as text with rupee signs and thousands commas.
    # Convert the column to object first because pandas 3 refuses to put text
    # into a float64 column.
    raw["Amount"] = raw["Amount"].astype(object)
    amount_idx = rng.choice(all_indices, size=N_TEXT_AMOUNTS, replace=False)
    for idx in amount_idx:
        value = float(raw.at[idx, "Amount"])
        raw.at[idx, "Amount"] = "₹{:,.2f}".format(value)

    # Add exact duplicates of normal rows. Copy the already-messy raw values so
    # the duplicate rows really are byte-for-byte identical before cleaning.
    normal_ids = clean_unique.loc[~clean_unique["Is_Injected_Anomaly"].astype(bool), "Transaction_ID"]
    duplicate_source = rng.choice(normal_ids.to_numpy(), size=N_DUPLICATE_ROWS, replace=False)
    duplicates = raw[raw["Transaction_ID"].isin(duplicate_source)].copy()
    raw = pd.concat([raw, duplicates], ignore_index=True)

    # Extra junk rows with missing critical fields. These are dropped later.
    junk_rows = []
    missing_fields = ["Customer_ID"] * 3 + ["Amount"] * 3 + ["Transaction_Time"] * 2
    for offset, field in enumerate(missing_fields, start=1):
        base = clean_unique.iloc[int(rng.integers(0, len(clean_unique)))].copy()
        row = {column: base[column] for column in clean_unique.columns}
        row["Transaction_ID"] = f"TXN9{offset:05d}"
        row["Transaction_Time"] = pd.to_datetime(base["Transaction_Time"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        row[field] = np.nan
        junk_rows.append(row)
    raw = pd.concat([raw, pd.DataFrame(junk_rows)], ignore_index=True)

    # Shuffle so duplicates are not neatly next to their originals.
    raw = raw.iloc[rng.permutation(len(raw))].reset_index(drop=True)
    return raw.drop(columns=["Is_Injected_Anomaly", "Injected_Type"])


def save_outputs(raw: pd.DataFrame, ground_truth: pd.DataFrame) -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    raw.to_csv(RAW_PATH, index=False)
    ground_truth.to_csv(GROUND_TRUTH_PATH, index=False)


def main() -> None:
    rng = np.random.default_rng(SEED)
    profiles = build_profiles(rng)
    normal = generate_normal_transactions(rng, profiles)
    anomaly, event_stats = make_anomaly_rows(rng, profiles)

    # Keep exactly 9,600 normal rows plus 400 injected rows.
    remove_count = len(normal) - (N_TRANSACTIONS - len(anomaly))
    remove_idx = rng.choice(len(normal), size=remove_count, replace=False)
    normal = normal.drop(index=remove_idx).reset_index(drop=True)

    combined = pd.concat([normal, anomaly], ignore_index=True)
    combined = combined.sort_values(
        ["Transaction_Time", "Customer_ID", "Amount"], kind="mergesort"
    ).reset_index(drop=True)
    combined.insert(0, "Transaction_ID", [f"TXN{i + 1:06d}" for i in range(len(combined))])

    ground_truth = combined[["Transaction_ID", "Is_Injected_Anomaly", "Injected_Type"]].copy()
    clean_unique = combined.drop(columns=["Is_Injected_Anomaly", "Injected_Type"])
    raw = make_raw_file(rng, combined)

    save_outputs(raw, ground_truth)

    # Useful run facts, printed so they can be copied into the docs accurately.
    injected = int(ground_truth["Is_Injected_Anomaly"].sum())
    night_owls = sum(1 for profile in profiles if profile["night_owl"])
    print("Synthetic data generated")
    print(f"Customers: {N_CUSTOMERS}")
    print(f"Days: {N_DAYS} ({START_DATE} to {END_DATE})")
    print(f"Unique clean transactions: {len(combined):,}")
    print(f"Injected anomaly rows: {injected:,} ({injected / len(combined):.2%})")
    print(f"Injected events: {event_stats['event_count']}")
    print(
        f"Combined-type events: {event_stats['combined_events']} "
        f"({event_stats['combined_events'] / event_stats['event_count']:.2%} of events)"
    )
    print(f"Night-owl customers: {night_owls}")
    print(f"Raw rows written: {len(raw):,}")
    print(f"  exact duplicate rows: {N_DUPLICATE_ROWS}")
    print(f"  extra rows with missing critical fields: {N_JUNK_ROWS}")
    print(f"  rows with null Merchant_Category: {N_NULL_MERCHANT}")
    print(f"  rows with null Location: {N_NULL_LOCATION}")
    print(f"  rows with day-first timestamps: {N_MIXED_TIMESTAMPS}")
    print(f"  rows with text amounts: {N_TEXT_AMOUNTS}")
    print(f"Wrote: {RAW_PATH}")
    print(f"Wrote: {GROUND_TRUTH_PATH}")
    print("Ground truth is hidden from the detector and from dashboard/data.")


if __name__ == "__main__":
    main()
