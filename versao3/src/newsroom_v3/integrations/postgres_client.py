from contextlib import contextmanager
from typing import Any, Iterator

import psycopg


class PostgresClient:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self._dsn) as conn:
            yield conn

    def healthcheck(self) -> bool:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
                return cur.fetchone() == (1,)

    async def execute(self, query: str, *params: Any) -> None:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()

    async def fetch(self, query: str, *params: Any) -> list[dict[str, Any]]:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                cols = [desc.name for desc in cur.description] if cur.description else []
                rows = cur.fetchall()
                return [dict(zip(cols, row)) for row in rows]
