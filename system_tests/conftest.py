import psycopg
import pytest

from .cluster import ClusterEnvironmentError, PgTestCluster, build_cluster


def pytest_addoption(parser):
    parser.addoption(
        "--pgbench",
        action="store_true",
        default=False,
        help="run pgbench-backed system tests",
    )
    parser.addoption(
        "--pgreplay",
        action="store_true",
        default=False,
        help="enable pgreplay workload tests",
    )
    parser.addoption(
        "--faults",
        action="store_true",
        default=False,
        help="enable external fault-injection suites",
    )
    parser.addoption(
        "--pgtap",
        action="store_true",
        default=False,
        help="enable pgTAP SQL-level tests",
    )
    parser.addoption(
        "--all",
        action="store_true",
        default=False,
        help="run all optional test suites (--pgbench, --pgreplay, --faults, --pgtap)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "pgbench: marks tests that depend on pgbench load generation",
    )
    config.addinivalue_line(
        "markers",
        "pgreplay: marks tests that require the pgreplay binary and log capture",
    )
    config.addinivalue_line(
        "markers",
        "faults: marks tests that rely on external fault-injection extensions",
    )
    config.addinivalue_line(
        "markers",
        "pgtap: marks tests that run pgTAP SQL-level test suites",
    )


def pytest_collection_modifyitems(config, items):
    run_all = config.getoption("--all")
    marker_flags = {
        "pgbench": run_all or config.getoption("--pgbench"),
        "pgreplay": run_all or config.getoption("--pgreplay"),
        "faults": run_all or config.getoption("--faults"),
        "pgtap": run_all or config.getoption("--pgtap"),
    }
    for item in items:
        # Skip tests based on their markers unless explicitly enabled
        for marker_name, enabled in marker_flags.items():
            if marker_name in item.keywords and not enabled:
                item.add_marker(pytest.mark.skip(reason=f"requires --{marker_name}"))


@pytest.fixture(scope="session")
def pg_cluster(tmp_path_factory) -> PgTestCluster:
    try:
        cluster = build_cluster(tmp_path_factory)
    except ClusterEnvironmentError as exc:
        pytest.skip(str(exc))
    yield cluster
    cluster.destroy()


@pytest.fixture(scope="session")
def dsn(pg_cluster: PgTestCluster) -> str:
    return pg_cluster.dsn()


@pytest.fixture
def conn(dsn: str):
    with psycopg.connect(dsn, autocommit=True) as connection:
        yield connection


@pytest.fixture(autouse=True)
def reset_helpers(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT retry.reset_accounts()")
        cur.execute("SELECT retry.reset_failure_plans()")
