"""
Stage 2 — Semantic Validation.

Reads data/processed/titanic_clean.csv, runs business-rule checks,
writes:
  - data/validated/titanic_validated.csv   (records that passed all rules)
  - data/validated/titanic_rejected.csv    (records that failed at least one rule)
  - data/reports/validation_report.txt     (human-readable report)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROCESSED_PATH = Path("data/processed/titanic_clean.csv")
VALIDATED_PATH = Path("data/validated/titanic_validated.csv")
REJECTED_PATH = Path("data/validated/titanic_rejected.csv")
REPORT_PATH = Path("data/reports/validation_report.txt")

log = logging.getLogger(__name__)


@dataclass
class ValidationError:
    row_index: int
    passenger_id: Any
    rule: str
    value: Any
    message: str


# Each rule is (mask_expr, rule_id, message_template, column_for_value)
# mask_expr is a callable df -> pd.Series[bool] where True = valid
_RULES: list[tuple] = [
    (
        lambda df: df["passenger_id"].notna(),
        "not_null:passenger_id",
        "passenger_id is null",
        "passenger_id",
    ),
    (
        lambda df: df["survived"].isin([0, 1]),
        "domain:survived",
        "survived={val} not in [0, 1]",
        "survived",
    ),
    (
        lambda df: df["pclass"].isin([1, 2, 3]),
        "domain:pclass",
        "pclass={val} not in [1, 2, 3]",
        "pclass",
    ),
    (
        lambda df: df["sex"].isin(["male", "female"]),
        "domain:sex",
        "sex='{val}' not in ['male', 'female']",
        "sex",
    ),
    (
        lambda df: df["embarked"].isin(["S", "C", "Q"]),
        "domain:embarked",
        "embarked='{val}' not in ['S', 'C', 'Q']",
        "embarked",
    ),
    (
        lambda df: df["age"].between(0, 120),
        "range:age",
        "age={val} out of valid range [0, 120]",
        "age",
    ),
    (
        lambda df: df["fare"] >= 0,
        "range:fare",
        "fare={val} is negative",
        "fare",
    ),
    (
        lambda df: df["sibsp"] >= 0,
        "range:sibsp",
        "sibsp={val} is negative",
        "sibsp",
    ),
    (
        lambda df: df["parch"] >= 0,
        "range:parch",
        "parch={val} is negative",
        "parch",
    ),
    (
        lambda df: df["family_size"] >= 1,
        "range:family_size",
        "family_size={val} < 1 (impossible)",
        "family_size",
    ),
    (
        lambda df: df["fare_per_person"] >= 0,
        "range:fare_per_person",
        "fare_per_person={val} is negative",
        "fare_per_person",
    ),
    (
        lambda df: ~df["passenger_id"].duplicated(keep=False),
        "unique:passenger_id",
        "passenger_id={val} is duplicated",
        "passenger_id",
    ),
    # Semantic: children (age < 12) should not travel alone
    (
        lambda df: ~((df["age"] < 12) & (df["is_alone"] == 1)),
        "semantic:child_alone",
        "child (age={val}) marked as traveling alone — suspicious",
        "age",
    ),
]


def _collect_errors(
    df: pd.DataFrame,
    mask: pd.Series,
    rule: str,
    msg_tpl: str,
    col: str,
) -> list[ValidationError]:
    errors = []
    for idx, row in df[~mask].iterrows():
        val = row.get(col) if col else None
        errors.append(
            ValidationError(
                row_index=int(idx),
                passenger_id=row.get("passenger_id"),
                rule=rule,
                value=val,
                message=msg_tpl.format(val=val),
            )
        )
    return errors


def run_validations(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[ValidationError]]:
    all_errors: list[ValidationError] = []
    bad_indices: set[int] = set()

    for rule_fn, rule_id, msg_tpl, col in _RULES:
        mask = rule_fn(df)
        errs = _collect_errors(df, mask, rule_id, msg_tpl, col)
        all_errors.extend(errs)
        bad_indices.update(df.index[~mask].tolist())

    valid = df.drop(index=list(bad_indices))
    rejected = df.loc[list(bad_indices)].copy()

    # Tag rejected rows with the rules they failed
    if not rejected.empty:
        failed_rules: dict[int, list[str]] = {}
        for e in all_errors:
            failed_rules.setdefault(e.row_index, []).append(e.rule)
        rejected["failed_rules"] = rejected.index.map(
            lambda i: "; ".join(failed_rules.get(i, []))
        )

    return valid, rejected, all_errors


def _write_report(
    errors: list[ValidationError],
    total: int,
    valid_count: int,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_rule: dict[str, list[ValidationError]] = {}
    for e in errors:
        by_rule.setdefault(e.rule, []).append(e)

    with path.open("w", encoding="utf-8") as f:
        sep = "=" * 64
        f.write(f"{sep}\n")
        f.write("PIPELINE VALIDATION REPORT\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{sep}\n\n")

        f.write(f"  Total records evaluated : {total:>6}\n")
        f.write(f"  Valid records           : {valid_count:>6}\n")
        f.write(f"  Rejected records        : {total - valid_count:>6}\n")
        f.write(f"  Total validation errors : {len(errors):>6}\n\n")

        if not errors:
            f.write("No errors detected. All records passed validation.\n")
            return

        f.write("ERRORS BY RULE\n")
        f.write("-" * 64 + "\n")
        for rule, errs in sorted(by_rule.items()):
            f.write(f"\n[{rule}]  {len(errs)} occurrence(s)\n")
            for e in errs[:10]:
                f.write(
                    f"    row={e.row_index:>5}  passenger_id={str(e.passenger_id):<6}  {e.message}\n"
                )
            if len(errs) > 10:
                f.write(f"    ... and {len(errs) - 10} more\n")

        f.write(f"\n{sep}\n")


def validate(
    processed_path: Path = PROCESSED_PATH,
    validated_path: Path = VALIDATED_PATH,
    rejected_path: Path = REJECTED_PATH,
    report_path: Path = REPORT_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    log.info("=== Stage 2: Validation ===")
    df = pd.read_csv(processed_path)
    log.info(f"Loaded {len(df)} rows for validation")

    valid, rejected, errors = run_validations(df)

    for p in (validated_path, rejected_path):
        p.parent.mkdir(parents=True, exist_ok=True)

    valid.to_csv(validated_path, index=False)
    rejected.to_csv(rejected_path, index=False)
    _write_report(errors, total=len(df), valid_count=len(valid), path=report_path)

    log.info(
        f"Valid: {len(valid)}  Rejected: {len(rejected)}  "
        f"Errors: {len(errors)}  Report: {report_path}"
    )
    return valid, rejected


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    validate()
