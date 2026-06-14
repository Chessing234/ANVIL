#!/usr/bin/env python3
"""Initialize SQL tables for TUTORIAL (idempotent create_all)."""

from __future__ import annotations

import asyncio

from api.converters import database_url_to_async
from config.settings import get_settings
from database.connection import DatabaseManager


async def _run() -> None:
    settings = get_settings()
    url = database_url_to_async(settings.database.url)
    mgr = DatabaseManager(url, pool_size=settings.database.pool_size, echo=settings.database.echo)
    await mgr.initialize()
    await mgr.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
