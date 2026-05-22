"""
Stage 3 — Database Loading.

Reads data/validated/titanic_validated.csv, creates the PostgreSQL table
(if absent), inserts rows with per-row error handling, and writes:
  - data/validated/titanic_inserted.csv   (successfully inserted rows)
  - data/validated/titanic_db_rejected.csv (rows rejected by the DB)
  - logs/load.log                          (detailed run log)
"""

import csv
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import errors as pg_errors
from dotenv import load_dotenv

load_dotenv()

VALIDATED_PATH = Path("data/validated/titanic_validated.csv")
INSERTED_PATH = Path("data/validated/titanic_inserted.csv")
DB_REJECTED_PATH = Path("data/validated/titanic_db_rejected.csv")
SQL_PATH = Path("sql/create_table.sql")
LOG_PATH = Path("logs/load.log")

_INSERT_SQL = """
    INSERT INTO passengers (
        passenger_id, age, fare, sex, sibsp, parch, pclass,
        embarked, survived, family_size, is_alone, fare_per_person, age_group
    ) VALUES (
        %(passenger_id)s, %(age)s, %(fare)s, %(sex)s, %(sibsp)s, %(parch)s,
        %(pclass)s, %(embarked)s, %(survived)s, %(family_size)s, %(is_alone)s,
        %(fare_per_person)s, %(age_group)s
    )
"""

log = logging.getLogger(__name__)


def _db_config() -> dict:
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "titanic"),
        "user": os.getenv("POSTGRES_USER", "pipeline"),
        "password": os.getenv("POSTGRES_PASSWORD", "pipeline123"),
        "connect_timeout": 10,
    }


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
    )
    log.addHandler(file_handler)


def _connect(config: dict) -> psycopg2.extensions.connection:
    log.info(
        f"Connecting to PostgreSQL at {config['host']}:{config['port']} "
        f"db={config['dbname']} user={config['user']}"
    )
    return psycopg2.connect(**config)


def _create_table(conn: psycopg2.extensions.connection) -> None:
    ddl = SQL_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    log.info("Table 'passengers' ensured (CREATE TABLE IF NOT EXISTS)")


def _already_loaded(conn: psycopg2.extensions.connection) -> set[int]:
    """Return passenger_ids already present in the DB to avoid re-inserting."""
    with conn.cursor() as cur:
        cur.execute("SELECT passenger_id FROM passengers")
        return {row[0] for row in cur.fetchall()}


def _row_to_dict(row: pd.Series) -> dict:
    return {
        "passenger_id": int(row["passenger_id"]),
        "age": float(row["age"]),
        "fare": float(row["fare"]),
        "sex": str(row["sex"]),
        "sibsp": int(row["sibsp"]),
        "parch": int(row["parch"]),
        "pclass": int(row["pclass"]),
        "embarked": str(row["embarked"]) if pd.notna(row["embarked"]) else None,
        "survived": int(row["survived"]),
        "family_size": int(row["family_size"]),
        "is_alone": int(row["is_alone"]),
        "fare_per_person": float(row["fare_per_person"]) if pd.notna(row["fare_per_person"]) else None,
        "age_group": str(row["age_group"]) if pd.notna(row["age_group"]) else None,
    }


def load(
    validated_path: Path = VALIDATED_PATH,
    inserted_path: Path = INSERTED_PATH,
    rejected_path: Path = DB_REJECTED_PATH,
) -> tuple[list[dict], list[dict]]:
    _setup_logging()
    log.info("=== Stage 3: Database Load ===")
    log.info(f"Run started at {datetime.now().isoformat()}")

    df = pd.read_csv(validated_path)
    log.info(f"Loaded {len(df)} rows from {validated_path}")

    config = _db_config()
    try:
        conn = _connect(config)
    except psycopg2.OperationalError as exc:
        log.error(f"Cannot connect to PostgreSQL: {exc}")
        raise

    _create_table(conn)
    existing_ids = _already_loaded(conn)
    log.info(f"Rows already in DB: {len(existing_ids)}")

    inserted: list[dict] = []
    rejected: list[dict] = []  # each entry has extra key "rejection_reason"

    for _, row in df.iterrows():
        record = _row_to_dict(row)

        # Pre-flight: skip duplicates already in the database
        if record["passenger_id"] in existing_ids:
            record["rejection_reason"] = "duplicate: already in database"
            rejected.append(record)
            log.warning(
                f"SKIP   passenger_id={record['passenger_id']} — already in DB"
            )
            continue

        # Attempt insert in its own savepoint so a failure doesn't kill the transaction
        try:
            with conn.cursor() as cur:
                cur.execute(_INSERT_SQL, record)
            conn.commit()
            existing_ids.add(record["passenger_id"])
            inserted.append(record)
            log.debug(f"INSERT passenger_id={record['passenger_id']}")
        except pg_errors.UniqueViolation:
            conn.rollback()
            reason = "db_error: unique violation"
            record["rejection_reason"] = reason
            rejected.append(record)
            log.warning(f"REJECT passenger_id={record['passenger_id']} — {reason}")
        except pg_errors.CheckViolation as exc:
            conn.rollback()
            reason = f"db_error: check constraint — {exc.diag.constraint_name}"
            record["rejection_reason"] = reason
            rejected.append(record)
            log.warning(f"REJECT passenger_id={record['passenger_id']} — {reason}")
        except Exception as exc:
            conn.rollback()
            reason = f"db_error: {type(exc).__name__}: {exc}"
            record["rejection_reason"] = reason
            rejected.append(record)
            log.error(f"REJECT passenger_id={record['passenger_id']} — {reason}")

    conn.close()

    # Persist results
    for p in (inserted_path, rejected_path):
        p.parent.mkdir(parents=True, exist_ok=True)

    if inserted:
        pd.DataFrame(inserted).drop(columns=["rejection_reason"], errors="ignore").to_csv(
            inserted_path, index=False
        )
    if rejected:
        pd.DataFrame(rejected).to_csv(rejected_path, index=False)

    log.info(
        f"Load complete — inserted: {len(inserted)}, rejected: {len(rejected)}, "
        f"total: {len(df)}"
    )
    log.info(f"Inserted CSV : {inserted_path}")
    log.info(f"Rejected CSV : {rejected_path}")
    log.info(f"Log file     : {LOG_PATH}")
    return inserted, rejected


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load()
