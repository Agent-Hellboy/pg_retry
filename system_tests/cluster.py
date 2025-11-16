"""Utilities for spinning up a disposable PostgreSQL cluster for system tests."""

from __future__ import annotations

import contextlib
import getpass
import os
import shutil
import socket
import subprocess
import tempfile
import textwrap
import uuid
from pathlib import Path
from typing import Iterable, Mapping, Sequence


class ClusterEnvironmentError(RuntimeError):
    """Raised when the local environment cannot support a test cluster."""


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _which_pg_config() -> str:
    candidate = os.environ.get("PG_CONFIG")
    if candidate:
        return candidate
    pg_config = shutil.which("pg_config")
    if pg_config is None:
        raise RuntimeError("pg_config is required to run system tests")
    return pg_config


def _is_shared_memory_permission_error(exc: subprocess.CalledProcessError) -> bool:
    output_bits = [exc.stderr, exc.stdout]
    text = "\n".join(bit for bit in output_bits if bit).lower()
    needle = "could not create shared memory segment"
    return needle in text and ("operation not permitted" in text or "permission denied" in text)


def _is_shared_memory_resource_exhausted(exc: subprocess.CalledProcessError) -> bool:
    output_bits = [exc.stderr, exc.stdout]
    text = "\n".join(bit for bit in output_bits if bit).lower()
    return "could not create shared memory segment" in text and "no space left on device" in text


class PgTestCluster:
    """Manages one temporary PostgreSQL cluster for pytest."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        socket_suffix = f"{self.base_dir.name[:16]}_{uuid.uuid4().hex[:8]}"
        self.socket_dir = Path(tempfile.gettempdir()) / f"pg_retry_{socket_suffix}"
        self.logfile = self.base_dir / "postgres.log"
        self.host = "127.0.0.1"
        self.listen_addresses = "127.0.0.1"
        self.port = None
        self.cluster_started = False
        self.database = "pg_retry_system_tests"
        self.user = os.getenv("PGUSER") or getpass.getuser()

        pg_config = _which_pg_config()
        self.bindir = Path(
            subprocess.check_output([pg_config, "--bindir"], text=True).strip()
        )
        self.pg_ctl = self.bindir / "pg_ctl"
        self.initdb = self.bindir / "initdb"
        self.psql = self.bindir / "psql"

        pgbench_path = self.bindir / "pgbench"
        if not pgbench_path.exists():
            cmd = shutil.which("pgbench")
            pgbench_path = Path(cmd) if cmd else None
        self.pgbench = pgbench_path if pgbench_path and pgbench_path.exists() else None
        self.keep_cluster = bool(os.getenv("PG_RETRY_KEEP_CLUSTER"))

    # ---------- lifecycle management ----------
    def start(self) -> None:
        if self.cluster_started:
            return

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.socket_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.port = _find_free_port()
            self.host = "127.0.0.1"
            self.listen_addresses = "127.0.0.1"
        except PermissionError:
            # Sandboxed environments may forbid binding TCP sockets; fall back to a
            # Unix socket only configuration in that case.
            self.port = 64321
            self.host = str(self.socket_dir)
            self.listen_addresses = ""

        try:
            self._run(
                [
                    str(self.initdb),
                    "-D",
                    str(self.data_dir),
                    "-U",
                    self.user,
                    "--encoding",
                    "UTF8",
                    "--no-locale",
                    "--set",
                    "dynamic_shared_memory_type=mmap",
                ],
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            if _is_shared_memory_permission_error(exc):
                raise ClusterEnvironmentError(
                    "initdb failed: shared memory allocation is not permitted in this environment"
                ) from exc
            if _is_shared_memory_resource_exhausted(exc):
                raise ClusterEnvironmentError(
                    "initdb failed: shared memory is exhausted on this system"
                ) from exc
            raise

        self._configure_postgresql_conf()
        self._run_pg_ctl("start")
        self.cluster_started = True

        self._run_sql(
            f"CREATE DATABASE {self.database}",
            dbname="postgres",
            check_exists=True,
        )
        self.run_sql("CREATE EXTENSION IF NOT EXISTS pg_retry")
        self._load_helper_sql()

    def stop(self) -> None:
        if not self.cluster_started:
            return
        with contextlib.suppress(subprocess.CalledProcessError):
            self._run_pg_ctl("stop", extra_args=("-m", "fast"))
        self.cluster_started = False

    def destroy(self) -> None:
        self.stop()
        if not self.keep_cluster:
            if self.base_dir.exists():
                shutil.rmtree(self.base_dir)
            if self.socket_dir.exists():
                shutil.rmtree(self.socket_dir)

    # ---------- helpers ----------
    def _configure_postgresql_conf(self) -> None:
        conf = self.data_dir / "postgresql.conf"
        settings = textwrap.dedent(
            f"""
            listen_addresses = '{self.listen_addresses}'
            port = {self.port}
            unix_socket_directories = '{self.socket_dir}'
            logging_collector = on
            log_destination = 'stderr,csvlog'
            log_directory = 'pg_log'
            log_min_messages = warning
            log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
            log_statement = 'all'
            session_preload_libraries = 'pg_retry'
            fsync = off
            synchronous_commit = off
            full_page_writes = off
            shared_buffers = '128MB'
            max_connections = 50
            statement_timeout = 0
            lock_timeout = 0
            """
        ).strip()
        with conf.open("a", encoding="utf-8") as fh:
            fh.write("\n" + settings + "\n")

    def _run_pg_ctl(self, action: str, extra_args: Sequence[str] | None = None) -> None:
        args = [str(self.pg_ctl), "-D", str(self.data_dir), "-l", str(self.logfile), "-w", "-t", "120", action]
        if extra_args:
            args.extend(extra_args)
        self._run(args, capture_output=True)

    def _run(
        self,
        args: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            check=True,
            env=env,
            text=True,
            capture_output=capture_output,
        )
        return result

    def _run_sql(self, sql: str, dbname: str | None = None, check_exists: bool = False) -> None:
        db = dbname or self.database
        cmd = [
            str(self.psql),
            "-h",
            self.host,
            "-p",
            str(self.port),
            "-d",
            db,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ]
        try:
            self._run(
                cmd,
                env=self.client_env(dbname=db),
                capture_output=check_exists,
            )
        except subprocess.CalledProcessError as exc:
            if check_exists and exc.stderr and "already exists" in exc.stderr:
                return
            raise

    def _load_helper_sql(self) -> None:
        helpers = Path(__file__).parent / "sql" / "helpers.sql"
        if not helpers.exists():
            raise RuntimeError("missing helper SQL: system_tests/sql/helpers.sql")
        cmd = [
            str(self.psql),
            "-h",
            self.host,
            "-p",
            str(self.port),
            "-d",
            self.database,
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(helpers),
        ]
        self._run(cmd, env=self.client_env())

    # ---------- convenience API ----------
    def run_sql(self, sql: str, dbname: str | None = None) -> None:
        self._run_sql(sql, dbname=dbname)

    def run_sql_file(self, path: Path, dbname: str | None = None) -> None:
        db = dbname or self.database
        cmd = [
            str(self.psql),
            "-h",
            self.host,
            "-p",
            str(self.port),
            "-d",
            db,
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(path),
        ]
        self._run(cmd, env=self.client_env(dbname=db))

    def client_env(self, *, dbname: str | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "PGHOST": self.host,
                "PGPORT": str(self.port),
                "PGDATABASE": dbname or self.database,
                "PGUSER": self.user,
            }
        )
        return env

    def dsn(self, *, dbname: str | None = None) -> str:
        db = dbname or self.database
        return f"host={self.host} port={self.port} dbname={db} user={self.user}"

    # ---------- utilities for tests ----------
    def truncate_log(self) -> None:
        if self.logfile.exists():
            self.logfile.write_text("", encoding="utf-8")
        log_dir = self.data_dir / "pg_log"
        if log_dir.exists():
            for path in log_dir.glob("postgresql-*.log"):
                path.unlink()

    def read_log(self) -> str:
        chunks: list[str] = []
        if self.logfile.exists():
            chunks.append(self.logfile.read_text(encoding="utf-8"))
        log_dir = self.data_dir / "pg_log"
        if log_dir.exists():
            for path in sorted(log_dir.glob("postgresql-*.log")):
                chunks.append(path.read_text(encoding="utf-8"))
        return "".join(chunks)

    def pgbench_available(self) -> bool:
        return self.pgbench is not None

    def pgbench_process(
        self,
        script: Path,
        *,
        clients: int = 4,
        threads: int = 2,
        duration: int = 5,
        extra_args: Iterable[str] | None = None,
    ) -> subprocess.Popen[str]:
        if not self.pgbench:
            raise RuntimeError("pgbench binary not found")
        cmd = [
            str(self.pgbench),
            "-h",
            self.host,
            "-p",
            str(self.port),
            "-n",
            "-c",
            str(clients),
            "-j",
            str(threads),
            "-T",
            str(duration),
            "-f",
            str(script),
            self.database,
        ]
        if extra_args:
            cmd.extend(extra_args)
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.client_env(),
        )

    def pgbench_run(self, script: Path, **kwargs) -> subprocess.CompletedProcess[str]:
        proc = self.pgbench_process(script, **kwargs)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"pgbench failed ({proc.returncode}): {stderr}\n{stdout}")
        completed = subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
        return completed


def build_cluster(tmp_path_factory) -> PgTestCluster:
    base = Path(tmp_path_factory.mktemp("pg_retry_cluster"))
    cluster = PgTestCluster(base)
    try:
        cluster.start()
    except ClusterEnvironmentError:
        cluster.destroy()
        raise
    return cluster
