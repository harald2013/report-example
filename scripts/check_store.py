#!/usr/bin/env python3
"""Check replay-safe database writes inside the local API container."""

import asyncio
import os
from uuid import uuid4

from reports.store import Store


async def main():
    store = Store(os.environ["DATABASE_URL"])
    report_id = str(uuid4())
    newer_id = str(uuid4())
    try:
        await store.begin(report_id, [1, 2])
        await store.begin(report_id, [1, 2])
        await store.complete(report_id, {"sum": 3})
        original = await store.get(report_id)
        await store.complete(report_id, {"sum": 3})
        await store.begin(report_id, [1, 2])
        report = await store.get(report_id)
        assert report["status"] == "completed", report
        assert report["input"] == [1, 2], report
        assert report["result"] == {"sum": 3}, report
        assert report["updated_at"] == original["updated_at"], report
        print("PostgreSQL: repeated activity writes preserve the completed report")
        await store.begin(newer_id, [3])
        listed = [str(row["id"]) for row in await store.latest(100)]
        assert listed.index(newer_id) < listed.index(report_id), listed
        assert len(await store.latest(1)) == 1
        print("PostgreSQL: latest reports are listed newest first")
    finally:
        async with await store.connect() as conn:
            await conn.execute(
                "DELETE FROM reports WHERE id = ANY(%s)", ([report_id, newer_id],)
            )


if __name__ == "__main__":
    asyncio.run(main())
