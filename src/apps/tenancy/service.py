from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from src.apps.tenancy.models import Tenant, TenantStatus
from src.apps.tenancy.schemas import CreateTenantRequest, UpdateTenantRequest
from src.core.exceptions import ConflictError, NotFoundError, TenantNotFoundError


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: CreateTenantRequest, created_by: str) -> Tenant:
        existing = await self.db.execute(
            select(Tenant).where(
                and_(Tenant.slug == data.slug, Tenant.deleted_at.is_(None))
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Tenant slug '{data.slug}' already taken")

        tenant = Tenant(
            **data.model_dump(),
            created_by=created_by,
        )
        self.db.add(tenant)
        await self.db.flush()
        return tenant

    async def get_by_slug(self, slug: str) -> Tenant:
        result = await self.db.execute(
            select(Tenant).where(
                and_(
                    Tenant.slug == slug,
                    Tenant.is_active.is_(True),
                    Tenant.deleted_at.is_(None),
                )
            )
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundError()
        return tenant

    async def get_by_id(self, tenant_id: str) -> Tenant:
        result = await self.db.execute(
            select(Tenant).where(
                and_(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
            )
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundError("Tenant")
        return tenant

    async def list_all(self, skip: int = 0, limit: int = 50) -> tuple[list[Tenant], int]:
        from sqlalchemy import func
        count_result = await self.db.execute(
            select(func.count()).select_from(Tenant).where(Tenant.deleted_at.is_(None))
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(Tenant)
            .where(Tenant.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
            .order_by(Tenant.created_at.desc())
        )
        tenants = result.scalars().all()
        return list(tenants), total

    async def update(self, tenant_id: str, data: UpdateTenantRequest) -> Tenant:
        tenant = await self.get_by_id(tenant_id)
        for key, value in data.model_dump(exclude_none=True).items():
            setattr(tenant, key, value)
        await self.db.flush()
        return tenant

    async def suspend(self, tenant_id: str) -> Tenant:
        tenant = await self.get_by_id(tenant_id)
        tenant.status = TenantStatus.SUSPENDED
        tenant.is_active = False
        await self.db.flush()
        return tenant

    async def activate(self, tenant_id: str) -> Tenant:
        tenant = await self.get_by_id(tenant_id)
        tenant.status = TenantStatus.ACTIVE
        tenant.is_active = True
        await self.db.flush()
        return tenant