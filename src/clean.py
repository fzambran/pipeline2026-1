"""
Stage 1 — Data Cleaning.

Reads raw Titanic CSV from data/raw/, applies cleaning transformations,
and writes the result to data/processed/.

Encoding in the raw file:
  Sex:      0 = male, 1 = female
  Embarked: 0 = Southampton, 1 = Cherbourg, 2 = Queenstown, '' = unknown
  Survived: 0 = no, 1 = yes
  Columns named "zero" are all-zero padding columns and are dropped.
  Column "2urvived" is a typo for "survived".
"""

import logging
from pathlib import Path

import pandas as pd

RAW_PATH = Path("data/raw/train_and_test2.csv")
PROCESSED_PATH = Path("data/processed/titanic_clean.csv")

_SEX_MAP = {0: "male", 1: "female"}
_EMBARKED_MAP = {0: "S", 1: "C", 2: "Q"}
_COLUMN_RENAMES = {
    "Passengerid": "passenger_id",
    "Age": "age",
    "Fare": "fare",
    "Sex": "sex",
    "sibsp": "sibsp",
    "Parch": "parch",
    "Pclass": "pclass",
    "Embarked": "embarked",
    "2urvived": "survived",
}

log = logging.getLogger(__name__)


def clean(raw_path: Path = RAW_PATH, out_path: Path = PROCESSED_PATH) -> pd.DataFrame:
    log.info("=== Stage 1: Cleaning ===")
    df = pd.read_csv(raw_path)
    log.info(f"Loaded {len(df)} rows, {df.shape[1]} columns from {raw_path}")

    # 1. Drop all-zero padding columns.
    #    The raw file has 19 columns named "zero"; pandas auto-renames duplicates
    #    to "zero.1", "zero.2", … so we match on the prefix.
    zero_cols = [c for c in df.columns if c == "zero" or c.startswith("zero.")]
    df = df.drop(columns=zero_cols)
    log.info(f"Dropped {len(zero_cols)} padding ('zero') columns")

    # 2. Rename columns to clean names
    df = df.rename(columns=_COLUMN_RENAMES)

    # 3. Decode categoricals (Sex and Embarked were label-encoded in the raw file)
    df["sex"] = pd.to_numeric(df["sex"], errors="coerce").map(_SEX_MAP)
    df["embarked"] = pd.to_numeric(df["embarked"], errors="coerce").map(_EMBARKED_MAP)

    # 4. Remove duplicate passenger IDs
    before = len(df)
    df = df.drop_duplicates(subset=["passenger_id"])
    log.info(f"Duplicates removed: {before - len(df)}")

    # 5. Handle nulls
    #    Age and Embarked use imputation; rows missing critical fields are dropped.
    null_age = df["age"].isna().sum()
    df["age"] = df["age"].fillna(df["age"].median())
    log.info(f"Age: imputed {null_age} null(s) with median {df['age'].median():.2f}")

    null_embarked = df["embarked"].isna().sum()
    mode_embarked = df["embarked"].mode()[0]
    df["embarked"] = df["embarked"].fillna(mode_embarked)
    log.info(f"Embarked: imputed {null_embarked} null(s) with mode '{mode_embarked}'")

    before = len(df)
    df = df.dropna(subset=["passenger_id", "survived", "pclass", "fare"])
    log.info(f"Rows dropped (critical null): {before - len(df)}")

    # 6. Remove out-of-range records
    before = len(df)
    df = df[df["age"].between(0, 120)]
    df = df[df["fare"] >= 0]
    df = df[df["pclass"].isin([1, 2, 3])]
    df = df[df["survived"].isin([0, 1])]
    log.info(f"Out-of-range rows removed: {before - len(df)}")

    # 7. Derived columns
    df["family_size"] = df["sibsp"] + df["parch"] + 1
    df["is_alone"] = (df["family_size"] == 1).astype(int)
    df["fare_per_person"] = (df["fare"] / df["family_size"]).round(4)
    df["age_group"] = pd.cut(
        df["age"],
        bins=[0, 12, 18, 60, 120],
        labels=["child", "teenager", "adult", "senior"],
        right=True,
    ).astype(str)  # convert Categorical to str for CSV compatibility

    # 8. Standardise types
    for col in ("passenger_id", "survived", "pclass", "sibsp", "parch", "family_size", "is_alone"):
        df[col] = df[col].astype(int)
    df["age"] = df["age"].round(2)
    df["fare"] = df["fare"].round(4)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    log.info(f"Clean data saved to {out_path} — {len(df)} rows, {df.shape[1]} columns")
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clean()
