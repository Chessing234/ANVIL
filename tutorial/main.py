#!/usr/bin/env python3
"""
TUTORIAL — The World's First Agentic AI That Learns by Teaching
Main application entry point.
"""

from __future__ import annotations

import argparse
import asyncio

from tutorial.bootstrap import Bootstrap


async def main() -> None:
    parser = argparse.ArgumentParser(description="TUTORIAL Security Education System")
    parser.add_argument(
        "--mode",
        choices=["api", "agent", "full"],
        default="full",
        help="Run mode: api (REST API only), agent (agents only), full (API + wait)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="API host")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--init-db", action="store_true", help="Initialize database on startup")
    parser.add_argument("--seed", action="store_true", help="Seed test data")
    args = parser.parse_args()

    bootstrap = Bootstrap()
    try:
        if args.init_db:
            await bootstrap.init_database()
        if args.seed:
            await bootstrap.seed_data()

        if args.mode == "agent":
            await bootstrap.start_message_bus()
            await bootstrap.start_agents()
            await bootstrap.run_forever()
        elif args.mode == "full":
            await bootstrap.run_full_stack_background_api(args.host, args.port)
        else:
            await bootstrap.start_api(host=args.host, port=args.port)
    finally:
        await bootstrap.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
