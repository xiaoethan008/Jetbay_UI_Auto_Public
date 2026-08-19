"""Remove stale UI-automation leads from the non-production product schema."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.database import get_mysql_connection
from runtime_environments import get_current_environment


TARGET_DATABASE = "product"
TARGET_TABLE = "leads"
AUTOMATION_NAMES = ("Codex Tester",)
APPLY_CONFIRMATION = "DELETE_PRODUCT_CODEX_TEST_LEADS"


def cutoff_epoch_ms(retention_hours: int, now_seconds: float | None = None) -> int:
    if retention_hours < 1:
        raise ValueError("retention-hours must be at least 1")
    current_seconds = time.time() if now_seconds is None else now_seconds
    return int((current_seconds - retention_hours * 60 * 60) * 1000)


def build_database_config() -> dict:
    config = dict(get_current_environment()["database"])
    missing = [key for key in ("host", "user", "password") if not config.get(key)]
    if missing:
        raise RuntimeError(f"Missing database settings: {', '.join(missing)}")
    config["db"] = TARGET_DATABASE
    return config


def cleanup_test_leads(retention_hours: int, apply: bool) -> tuple[int, int]:
    cutoff = cutoff_epoch_ms(retention_hours)
    placeholders = ", ".join(["%s"] * len(AUTOMATION_NAMES))
    where_clause = f"name IN ({placeholders}) AND create_time < %s"
    params = (*AUTOMATION_NAMES, cutoff)
    config = build_database_config()
    connection = get_mysql_connection(database_config=config)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name")
            database_name = cursor.fetchone()["database_name"]
            if database_name != TARGET_DATABASE:
                raise RuntimeError(
                    f"Refusing cleanup outside {TARGET_DATABASE!r}: connected to {database_name!r}"
                )

            cursor.execute(
                f"SELECT COUNT(*) AS count FROM {TARGET_TABLE} WHERE {where_clause}",
                params,
            )
            matched = int(cursor.fetchone()["count"])
            if not apply:
                connection.rollback()
                return matched, matched

            cursor.execute(
                f"DELETE FROM {TARGET_TABLE} WHERE {where_clause}",
                params,
            )
            deleted = cursor.rowcount
            if deleted != matched:
                raise RuntimeError(
                    f"Target set changed during cleanup: matched={matched}, deleted={deleted}"
                )
            connection.commit()

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS count FROM {TARGET_TABLE} WHERE {where_clause}",
                params,
            )
            remaining = int(cursor.fetchone()["count"])
        return deleted, remaining
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retention-hours", type=int, default=6)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit deletion. Without this flag the command is a dry run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and os.getenv("CLEANUP_CONFIRM", "") != APPLY_CONFIRMATION:
        raise RuntimeError(
            f"Set CLEANUP_CONFIRM={APPLY_CONFIRMATION} before using --apply"
        )

    affected, remaining = cleanup_test_leads(
        retention_hours=args.retention_hours,
        apply=args.apply,
    )
    mode = "APPLY" if args.apply else "DRY_RUN"
    print(
        f"mode={mode} database={TARGET_DATABASE} table={TARGET_TABLE} "
        f"names={AUTOMATION_NAMES!r} retention_hours={args.retention_hours} "
        f"affected={affected} remaining={remaining}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
