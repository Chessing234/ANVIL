#!/usr/bin/env python3
"""Seed base catalog data plus rich demo fixtures (idempotent)."""

from __future__ import annotations

import asyncio

from api.converters import database_url_to_async
from config.settings import get_settings
from database.connection import DatabaseManager
from database.seed_data import seed_database
from database.seed_rich_demo import seed_rich_demo


async def _run() -> None:
    settings = get_settings()
    url = database_url_to_async(settings.database.url)
    mgr = DatabaseManager(url, pool_size=settings.database.pool_size, echo=settings.database.echo)
    await mgr.initialize()
    async with mgr.session() as session:
        await seed_database(session)
        await seed_rich_demo(session)
    await mgr.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
