from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor
from .utils import fetch_scalar, run_retry_sql


def test_concurrent_deadlocks_are_retried(pg_cluster):
    """Use many workers grabbing advisory locks in opposite order."""
    dsn = pg_cluster.dsn()
    pg_cluster.truncate_log()
    pg_cluster.run_sql("SELECT retry.configure_failure_plan('forced_deadlock', '40P01', 12)")

    deadlocks_before = fetch_scalar(
        dsn,
        """
        SELECT pg_stat_get_db_deadlocks(oid)
        FROM pg_database
        WHERE datname = current_database()
        """,
    )

    statements = [
        "SELECT retry.transfer_with_advisory(1, 2, 1, 30, 'forced_deadlock')",
        "SELECT retry.transfer_with_advisory(2, 1, 1, 30, NULL)",
    ] * 6
    random.shuffle(statements)

    with ThreadPoolExecutor(max_workers=len(statements)) as pool:
        futures = [pool.submit(run_retry_sql, dsn, stmt) for stmt in statements]
        for future in futures:
            future.result(timeout=60)

    total_balance = fetch_scalar(dsn, "SELECT sum(balance) FROM retry.accounts")
    history_count = fetch_scalar(dsn, "SELECT count(*) FROM retry.transfer_history")

    assert total_balance == 3000
    assert history_count == len(statements)

    deadlocks_after = fetch_scalar(
        dsn,
        """
        SELECT pg_stat_get_db_deadlocks(oid)
        FROM pg_database
        WHERE datname = current_database()
        """,
    )
    assert deadlocks_after > deadlocks_before
