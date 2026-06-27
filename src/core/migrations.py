"""Schema migrations for columns added to existing tables.
SQLAlchemy create_all does not alter existing tables, so new columns
on tables that already exist in the database must be added via ALTER TABLE.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

_MIGRATIONS: list[str] = [
    # Progress entries — version column for optimistic concurrency
    "ALTER TABLE progress_entries ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
    # Subcontractor certificates — link to finance invoice, version for concurrency
    "ALTER TABLE subcontractor_certificates ADD COLUMN IF NOT EXISTS invoice_id VARCHAR(36) REFERENCES invoices(id) ON DELETE SET NULL",
    "ALTER TABLE subcontractor_certificates ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
    # Quality — subcontractor FK columns
    "ALTER TABLE inspections ADD COLUMN IF NOT EXISTS subcontractor_id VARCHAR(36) REFERENCES subcontractors(id) ON DELETE SET NULL",
    "ALTER TABLE ncrs ADD COLUMN IF NOT EXISTS subcontractor_id VARCHAR(36) REFERENCES subcontractors(id) ON DELETE SET NULL",
    "ALTER TABLE safety_incidents ADD COLUMN IF NOT EXISTS subcontractor_id VARCHAR(36) REFERENCES subcontractors(id) ON DELETE SET NULL",
    "ALTER TABLE punch_list_items ADD COLUMN IF NOT EXISTS subcontractor_id VARCHAR(36) REFERENCES subcontractors(id) ON DELETE SET NULL",
    "ALTER TABLE toolbox_talks ADD COLUMN IF NOT EXISTS subcontractor_id VARCHAR(36) REFERENCES subcontractors(id) ON DELETE SET NULL",
    "ALTER TABLE safety_violations ADD COLUMN IF NOT EXISTS subcontractor_id VARCHAR(36) REFERENCES subcontractors(id) ON DELETE SET NULL",
    "ALTER TABLE safety_observations ADD COLUMN IF NOT EXISTS subcontractor_id VARCHAR(36) REFERENCES subcontractors(id) ON DELETE SET NULL",
    # Portal — subcontractor users table (created by create_all, but ensure FK)
    "ALTER TABLE subcontractor_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE subcontractor_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE",
]


async def run_migrations(conn: AsyncConnection) -> None:
    """Execute ALTER TABLE statements, ignoring if column already exists."""
    for stmt in _MIGRATIONS:
        try:
            await conn.execute(text(stmt))
            logger.info("Migration OK: %s", stmt[:80])
        except Exception as e:
            logger.warning("Migration skipped (likely already applied): %s — %s", stmt[:80], e)
