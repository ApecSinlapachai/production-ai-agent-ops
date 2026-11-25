"""PostgreSQL connection pool compatible with local PG16 and Supabase PgBouncer."""

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class DatabasePool:
    """Synchronous psycopg3 pool with prepared statements disabled for PgBouncer safety."""

    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 5) -> None:
        self._dsn = dsn
        self._pool = ConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={"prepare_threshold": None, "row_factory": dict_row},
        )
        self._is_open = False

    def open(self) -> None:
        """Open the connection pool and wait briefly for initial connectivity."""
        if not self._is_open:
            self._pool.open(wait=True, timeout=5.0)
            self._is_open = True

    def close(self) -> None:
        """Close the connection pool cleanly."""
        if self._is_open:
            self._pool.close()
            self._is_open = False

    @contextmanager
    def get_connection(self) -> Iterator[Connection]:
        """Yield a pooled database connection."""
        if not self._is_open:
            self.open()
        with self._pool.connection() as conn:
            yield conn

    def check_health(self) -> bool:
        """Return True if PostgreSQL answers SELECT 1, False otherwise."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok")
                    row = cur.fetchone()
                    return bool(row and row.get("ok") == 1)
        except Exception:
            return False
