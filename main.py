"""
Pipeline orchestrator.

Runs the three stages in order:
  1. clean    — raw CSV → data/processed/
  2. validate — processed CSV → data/validated/ + data/reports/
  3. load     — validated CSV → PostgreSQL

Usage:
  uv run python main.py               # all stages
  uv run python main.py --stage clean
  uv run python main.py --stage validate
  uv run python main.py --stage load
"""

import argparse
import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def run_clean() -> None:
    from src.clean import clean
    clean()


def run_validate() -> None:
    from src.validate import validate
    validate()


def run_load() -> None:
    from src.load import load
    load()


STAGES = {
    "clean": run_clean,
    "validate": run_validate,
    "load": run_load,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Titanic data pipeline")
    parser.add_argument(
        "--stage",
        choices=list(STAGES),
        default=None,
        help="Run a single stage instead of the full pipeline",
    )
    args = parser.parse_args(argv)

    stages = [args.stage] if args.stage else list(STAGES)

    t0 = time.perf_counter()
    for stage in stages:
        log.info(f"--- Starting stage: {stage} ---")
        t1 = time.perf_counter()
        try:
            STAGES[stage]()
        except Exception:
            log.exception(f"Stage '{stage}' failed")
            sys.exit(1)
        log.info(f"--- Stage '{stage}' done in {time.perf_counter() - t1:.1f}s ---")

    log.info(f"Pipeline finished in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
