#!/usr/bin/env python3
"""Backfill Binance transaction history and synthetic account snapshots."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


from app.core.database import SessionLocal  # noqa: E402
from app.services.history_backfill_service import backfill_account_history, load_active_accounts  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill recent transaction history from Binance.")
    parser.add_argument(
        "--account-id",
        dest="account_ids",
        action="append",
        type=int,
        help="Backfill only the specified account id. Can be provided multiple times.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="How many recent days to backfill. Default: 7.",
    )
    parser.add_argument(
        "--symbol",
        dest="symbols",
        action="append",
        help="Optional symbol to force-fetch trades for. Can be provided multiple times.",
    )
    parser.add_argument(
        "--snapshot-interval-minutes",
        type=int,
        default=60,
        help="Synthetic account snapshot interval in minutes. Default: 60.",
    )
    parser.add_argument(
        "--skip-snapshots",
        action="store_true",
        help="Only backfill transaction history and skip synthetic account snapshots.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


async def run_backfill(
    account_ids: Optional[Sequence[int]],
    days: int,
    symbols: Optional[Sequence[str]],
    include_snapshots: bool,
    snapshot_interval_minutes: int,
) -> int:
    db = SessionLocal()
    try:
        accounts = load_active_accounts(db, account_ids)
        if not accounts:
            logging.error("no matching active accounts found")
            return 1

        for account in accounts:
            result = await backfill_account_history(
                db,
                account,
                days=days,
                extra_symbols=symbols,
                include_snapshots=include_snapshots,
                snapshot_interval_minutes=snapshot_interval_minutes,
            )
            logging.info(result["message"])

        logging.info("backfill completed for %s account(s)", len(accounts))
        return 0
    finally:
        db.close()


async def async_main() -> int:
    args = parse_args()
    load_dotenv()
    configure_logging(args.verbose)

    if args.days <= 0:
        logging.error("--days must be greater than 0")
        return 1
    if args.snapshot_interval_minutes <= 0:
        logging.error("--snapshot-interval-minutes must be greater than 0")
        return 1

    return await run_backfill(
        account_ids=args.account_ids,
        days=args.days,
        symbols=args.symbols,
        include_snapshots=not args.skip_snapshots,
        snapshot_interval_minutes=args.snapshot_interval_minutes,
    )


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
