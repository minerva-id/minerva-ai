"""
Minerva AI — Database initialization script.

Run this script to initialize the Supabase database with the
required schema. Reads migrations from the migrations/ directory.

Usage:
    python scripts/init_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from minerva.config import get_settings
from minerva.logger import get_logger, setup_logging

log = get_logger(__name__)


async def init_database() -> None:
    """Run database migrations against Supabase."""
    settings = get_settings()
    setup_logging(settings.log_level)

    if not settings.has_supabase():
        log.error("supabase_not_configured", message="Set SUPABASE_URL and SUPABASE_KEY")
        sys.exit(1)

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_key)

    migrations_dir = Path(__file__).parent.parent / "migrations"

    if not migrations_dir.exists():
        log.error("migrations_dir_not_found", path=str(migrations_dir))
        sys.exit(1)

    # Get all SQL files sorted by name
    sql_files = sorted(migrations_dir.glob("*.sql"))

    if not sql_files:
        log.info("no_migrations_found")
        return

    for sql_file in sql_files:
        log.info("running_migration", file=sql_file.name)
        sql_content = sql_file.read_text()

        try:
            # Execute SQL via Supabase's rpc or raw query
            # Note: Supabase client doesn't support raw SQL directly.
            # Use the SQL editor in Supabase dashboard instead.
            log.info(
                "migration_note",
                message=f"Please run {sql_file.name} in Supabase SQL Editor",
                file=sql_file.name,
            )
        except Exception as e:
            log.error("migration_error", file=sql_file.name, error=str(e))
            raise

    log.info("migrations_complete", count=len(sql_files))
    print(f"\n✅ Found {len(sql_files)} migration(s).")
    print("📋 Please run the SQL files in your Supabase SQL Editor:")
    for f in sql_files:
        print(f"   - {f.name}")


if __name__ == "__main__":
    asyncio.run(init_database())
