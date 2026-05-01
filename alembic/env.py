import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from src.core.config import settings
from src.core.database import Base

# Import all models so Alembic sees them
from src.apps.identity.models import User, OrganizationMember, RefreshToken
from src.apps.tenancy.models import Tenant
from src.apps.projects.models import Project, Site, Milestone, ProjectMember
from src.apps.boq.models import (
    CostCode, BudgetVersion, BOQItem,
    RateAnalysis, RateAnalysisComponent
)
from src.apps.procurement.models import (
    Vendor, RFQ, RFQItem, RFQVendor,
    Quotation, QuotationItem,
    PurchaseOrder, POItem, GRN, GRNItem,
)
from src.apps.inventory.models import (
    Warehouse, StockItem, StockTransaction,
    MaterialRequest, MaterialRequestItem,
)
from src.apps.site_ops.models import (
    DailyProgressReport, DPRWorkItem,
    LabourAttendance, EquipmentLog,
)
config = context.config
config.set_main_option("sqlalchemy.url", settings.database_sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=settings.database_url,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
