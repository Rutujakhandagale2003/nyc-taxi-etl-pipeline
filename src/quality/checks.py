"""Data quality checks that run before loading data into the warehouse."""
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.transform.enrich import PAYMENT_TYPES


class DataQualityError(Exception):
    """Raised when an 'error' severity check fails, which stops the pipeline."""


@dataclass
class CheckResult:
    check_name: str
    column: str
    severity: str        # "error" stops the pipeline, "warning" only logs
    failed_rows: int
    passed: bool
    details: str = ""


# ---------- Reusable check functions ----------

def check_not_null(df, column, severity="error") -> CheckResult:
    failed = int(df[column].isna().sum())
    return CheckResult("not_null", column, severity, failed, failed == 0)


def check_between(df, column, min_value, max_value, severity="error") -> CheckResult:
    failed = int((~df[column].between(min_value, max_value)).sum())
    return CheckResult("between", column, severity, failed, failed == 0,
                       f"allowed range {min_value} to {max_value}")


def check_max(df, column, max_value, severity="warning") -> CheckResult:
    failed = int((df[column] > max_value).sum())
    return CheckResult("max_value", column, severity, failed, failed == 0,
                       f"values above {max_value}")


def check_accepted_values(df, column, allowed, severity="error") -> CheckResult:
    invalid = ~df[column].isin(allowed)
    failed = int(invalid.sum())
    found = sorted(df.loc[invalid, column].astype(str).unique().tolist())[:5]
    return CheckResult("accepted_values", column, severity, failed, failed == 0,
                       f"unexpected values: {found}" if found else "")


def check_min_rows(df, minimum, severity="error") -> CheckResult:
    rows = len(df)
    return CheckResult("min_row_count", "*", severity, 0 if rows >= minimum else 1,
                       rows >= minimum, f"{rows:,} rows, minimum {minimum:,}")


def check_all_days_present(df, month, severity="error") -> CheckResult:
    expected = pd.date_range(start=f"{month}-01", periods=pd.Period(month).days_in_month, freq="D")
    present = pd.DatetimeIndex(df["pickup_date"].unique())
    missing = expected.difference(present)
    return CheckResult("all_days_present", "pickup_date", severity, len(missing), len(missing) == 0,
                       f"missing days: {[d.strftime('%Y-%m-%d') for d in missing]}" if len(missing) else "")


def check_duplicates(df, subset, severity="warning") -> CheckResult:
    failed = int(df.duplicated(subset=subset).sum())
    return CheckResult("no_duplicates", ",".join(subset), severity, failed, failed == 0)


# ---------- Run all checks ----------

def run_quality_checks(enriched_path: Path, month: str, config: dict, logger) -> list[CheckResult]:
    logger.info("Running data quality checks on %s", enriched_path.name)
    df = pd.read_parquet(enriched_path)
    q = config["quality"]

    results = [
        # Completeness of key columns
        check_not_null(df, "pickup_datetime"),
        check_not_null(df, "dropoff_datetime"),
        check_not_null(df, "pickup_location_id"),
        check_not_null(df, "dropoff_location_id"),
        check_not_null(df, "fare_amount"),
        # Referential integrity: every trip matched a zone and a weather day
        check_not_null(df, "pickup_zone"),
        check_not_null(df, "dropoff_zone"),
        check_not_null(df, "weather_category"),
        # Valid ranges and values
        check_between(df, "fare_amount", 0.01, config["cleaning"]["max_fare"]),
        check_accepted_values(df, "weather_category", ["dry", "rain", "heavy_rain", "snow"]),
        check_accepted_values(df, "payment_type_name", list(PAYMENT_TYPES.values()) + ["unknown"]),
        # Volume and completeness
        check_min_rows(df, q["min_rows_per_month"]),
        check_all_days_present(df, month),
        # Warnings only
        check_duplicates(df, ["vendor_id", "pickup_datetime", "dropoff_datetime",
                              "pickup_location_id", "dropoff_location_id", "fare_amount"]),
        check_max(df, "avg_speed_mph", q["max_avg_speed_mph"]),
    ]

    # Log every result
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        logger.info("  [%s] %-8s %-17s %-40s failed=%s %s",
                    status, r.severity, r.check_name, r.column[:40], f"{r.failed_rows:,}", r.details)

    # Save results so there's a permanent record of every run
    report = pd.DataFrame([asdict(r) for r in results])
    report.insert(0, "month", month)
    report.insert(0, "run_at", datetime.now().isoformat(timespec="seconds"))
    taxi_type = config["sources"]["taxi_type"]
    report_path = config["paths"]["quality"] / f"dq_results_{taxi_type}_{month}.csv"
    report.to_csv(report_path, index=False)
    logger.info("Saved quality report %s", report_path.name)

    # Quality gate: stop the pipeline if any error-level check failed
    failed_errors = [r for r in results if not r.passed and r.severity == "error"]
    failed_warnings = [r for r in results if not r.passed and r.severity == "warning"]
    if failed_warnings:
        logger.warning("%d warning check(s) failed for %s", len(failed_warnings), month)
    if failed_errors:
        names = ", ".join(f"{r.check_name}({r.column})" for r in failed_errors)
        raise DataQualityError(f"Quality gate failed for {month}: {names}")

    logger.info("Quality gate PASSED for %s", month)
    return results