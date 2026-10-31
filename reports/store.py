import asyncio
import sys

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from reports.config import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed')),
    input JSONB NOT NULL,
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class Store:
    def __init__(self, database_url: str):
        self.database_url = database_url

    async def connect(self):
        return await AsyncConnection.connect(
            self.database_url,
            row_factory=dict_row,
            connect_timeout=5,
            options="-c statement_timeout=5000",
        )

    async def migrate(self):
        async with await self.connect() as conn:
            # Serialize initial setup when deployment jobs run concurrently.
            await conn.execute("SELECT pg_advisory_xact_lock(730003)")
            await conn.execute(SCHEMA)

    async def ready(self):
        async with await self.connect() as conn:
            await conn.execute("SELECT id FROM reports LIMIT 0")

    async def begin(self, report_id: str, values: list[float]):
        async with await self.connect() as conn:
            await conn.execute(
                "INSERT INTO reports (id, status, input) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                (report_id, "processing", Jsonb(values)),
            )

    async def complete(self, report_id: str, result: dict):
        async with await self.connect() as conn:
            cursor = await conn.execute(
                "UPDATE reports SET status = 'completed', result = %s, "
                "updated_at = CASE WHEN result IS DISTINCT FROM %s "
                "THEN now() ELSE updated_at END WHERE id = %s",
                (Jsonb(result), Jsonb(result), report_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Report must exist before completion")

    async def get(self, report_id: str):
        async with await self.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM reports WHERE id = %s", (report_id,)
            )
            return await cursor.fetchone()

    async def latest(self, limit: int):
        async with await self.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM reports ORDER BY created_at DESC, id DESC LIMIT %s",
                (limit,),
            )
            return await cursor.fetchall()


def main() -> int:
    print("Migration started", flush=True)
    try:
        asyncio.run(Store(Settings.from_env().database_url).migrate())
    except Exception as error:
        # Driver exceptions can contain connection credentials or input data.
        print(f"Migration failed ({type(error).__name__})", file=sys.stderr, flush=True)
        return 1
    print("Migration completed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
