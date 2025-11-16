# System Test Harness

The `system_tests/` tree contains high-level tests that exercise `pg_retry`
under realistic concurrency, load, and configuration scenarios. They build on a
temporary PostgreSQL cluster so they can run in CI without relying on a global
server.

## What Gets Tested

- **Concurrent workload:** python threads and `pgbench` clients race on helper
  functions that lock shared rows in different orders to provoke `40P01`
  deadlocks and `40001` serialization failures.
- **Retry under load:** `pgbench` drives dozens of retries while holding locks
  just long enough to raise `55P03`/`57014`, validating exponential backoff.
- **GUC configuration:** tests toggle `pg_retry.default_*` with both global and
  `SET LOCAL` scope to ensure retries inherit the expected defaults.
- **Isolation levels:** transactions at `READ COMMITTED`, `REPEATABLE READ`, and
  `SERIALIZABLE` must recover from transient errors without leaking
  subtransactions.

## Requirements

1. A local PostgreSQL toolchain (the same one you build the extension with).
2. Python 3.11+ with the packages listed in `requirements.txt`.
3. `pgbench` (ships with the core PostgreSQL distribution). Tests that depend on
   it will automatically skip when it is unavailable.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r system_tests/requirements.txt
```

## Running

```bash
# Build + install the extension into your active PostgreSQL toolchain
make
sudo make install      # or run as the same user PostgreSQL was built with

# Spin up the disposable cluster and run pytest
make systemtest
```

The `systemtest` make target installs Python requirements, creates a fresh
cluster via `pg_config --bindir`, installs `pg_retry`, loads the helper SQL
objects in `system_tests/sql/`, and executes `pytest system_tests`. Heavier
 suites are opt-in:

```bash
make systemtest SYSTEMTEST_PYTEST_FLAGS="--pgbench"
make systemtest SYSTEMTEST_PYTEST_FLAGS="--pgreplay"
make systemtest SYSTEMTEST_PYTEST_FLAGS="--faults"ß
```

You can combine flags (e.g., `--pgbench --pgreplay`). When running directly with
pytest you can also pass marker expressions (e.g., `pytest -m "pgbench or faults"`
system_tests`). In CI scenarios where the extension was already installed, set
`SYSTEMTEST_SKIP_INSTALL=1` to avoid re-invoking `make install`.

## How It Works

The harness (see `cluster.py`) bootstraps a cluster under
`tmp_path_factory / pg_retry_cluster` using:

- `initdb` / `pg_ctl` from the detected `pg_config`.
- Configuration tuned for quick retries: `listen_addresses = '127.0.0.1'`,
  fast fsync settings, verbose logging (`postgres.log`).
- A dedicated database `pg_retry_system_tests` with the extension preloaded and
  helper schemas, tables, and PL/pgSQL functions.

`pytest` fixtures provide:

- `pg_cluster`: lifecycle of the temporary cluster.
- `dsn`: psycopg connection string for the test database.
- `conn`: autocommit connection reset between tests.

The helper SQL creates:

- `retry.accounts` & `retry.transfer_with_advisory()` – conflicting transfers.
- `retry.failure_plan_*` functions – deterministic fault injection that raises
  arbitrary SQLSTATEs for a configurable number of attempts (useful for GUC and
  isolation tests).
- `retry.lock_waiter()` – sets tiny `lock_timeout` values to trigger `55P03`
  while verifying that top-level `txid_current()` values remain stable and that
  `pg_stat_activity` never shows lingering "idle in transaction" sessions.
- `retry.pgbench_lock_workload()` – workload for pgbench that combines
  intentional lock contention with fault plans to stress exponential backoff.

## pgTAP SQL Testing

The `pgtap/` directory contains comprehensive SQL-level tests using pgTAP:

- **`setup.sql`**: Basic functionality tests covering extension installation, retry logic, GUC parameters, and SQL injection protection
- **`retry_scenarios.sql`**: Advanced tests for different failure scenarios (serialization, deadlocks, timeouts, etc.)
- **`run_tests.sh`**: Automated test runner with results reporting

Run pgTAP tests with:
```bash
cd system_tests/pgtap
./run_tests.sh
```

This provides thorough SQL-level validation of the pg_retry extension's functionality.

## Extending

- Put additional helper SQL in `system_tests/sql/` and list it in
  `cluster.py:load_helpers()`.
- Mark long-running tests with `pytest.mark.pgbench`, `pytest.mark.pgreplay`, or
  `pytest.mark.faults` so contributors can opt in via command-line switches.
- For even more extreme cases (crash/restart loops, Tsung recordings, etc.),
  follow the pattern in `test_fault_injection.py`—guard the logic behind both a
  pytest marker and an explicit environment variable so the default CI path
  remains safe and fast.
