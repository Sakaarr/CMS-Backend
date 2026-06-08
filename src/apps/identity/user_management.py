import secrets
import string
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from src.apps.identity.models import (
    User, OrganizationMember, UserPermission, UserRole, UserStatus
)
from src.apps.identity.schemas import (
    CreateUserRequest, UpdateUserRequest,
    UserPermissionSchema, ROLE_DEFAULT_PERMISSIONS,
    CreateTenantAdminRequest,
)
from src.core.security import hash_password
from src.core.exceptions import (
    NotFoundError, ConflictError, ValidationError
)
from src.core.email import send_user_welcome, send_tenant_admin_welcome
from src.core.config import settings

logger = logging.getLogger(__name__)


def generate_temp_password(length: int = 12) -> str:
    """Generates a secure, readable temporary password."""
    upper = secrets.choice(string.ascii_uppercase)
    digit = secrets.choice(string.digits)
    rest_length = max(length - 2, 6)
    rest = "".join(
        secrets.choice(string.ascii_letters + string.digits)
        for _ in range(rest_length)
    )
    chars = list(upper + digit + rest)
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


class UserManagementService:
    def __init__(
        self,
        db: AsyncSession,
        tenant_id: str,
        acting_user_id: str,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.acting_user_id = acting_user_id

    # ── Create tenant admin (called by super admin) ───────────────

    async def create_tenant_admin(
        self,
        tenant_id: str,
        tenant_name: str,
        tenant_slug: str,
        data: CreateTenantAdminRequest,
    ) -> tuple[User, str]:
        """Creates company_admin user for a tenant. Returns (user, temp_password)."""

        # Check email uniqueness
        existing = await self.db.execute(
            select(User).where(
                and_(User.email == data.email, User.deleted_at.is_(None))
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Email '{data.email}' is already registered")

        temp_password = generate_temp_password()

        user = User(
            email=data.email,
            hashed_password=hash_password(temp_password),
            full_name=data.full_name,
            phone=data.phone,
            must_change_password=True,
            created_by=self.acting_user_id,
        )
        self.db.add(user)
        await self.db.flush()

        # Org membership — company admin, is_owner=True
        member = OrganizationMember(
            user_id=user.id,
            tenant_id=tenant_id,
            role=UserRole.COMPANY_ADMIN,
            is_owner=True,
            invited_by=self.acting_user_id,
            created_by=self.acting_user_id,
        )
        self.db.add(member)

        # Full permissions for company admin
        default_perms = ROLE_DEFAULT_PERMISSIONS[UserRole.COMPANY_ADMIN]
        perms = UserPermission(
            user_id=user.id,
            tenant_id=tenant_id,
            created_by=self.acting_user_id,
            **default_perms,
        )
        self.db.add(perms)
        await self.db.flush()

        # Send welcome email (logs to console in dev)
        send_tenant_admin_welcome(
            to=data.email,
            full_name=data.full_name,
            tenant_name=tenant_name,
            tenant_slug=tenant_slug,
            temp_password=temp_password,
            dashboard_url=settings.dashboard_url,
        )

        logger.info(
            f"Tenant admin created: {data.email} for tenant {tenant_slug}"
        )
        return user, temp_password

    # ── Create user (called by tenant admin) ─────────────────────

    async def create_user(
        self,
        tenant_slug: str,
        tenant_name: str,
        data: CreateUserRequest,
    ) -> tuple[User, str]:
        """Creates a user within the tenant. Returns (user, temp_password)."""

        existing = await self.db.execute(
            select(User).where(
                and_(User.email == data.email, User.deleted_at.is_(None))
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Email '{data.email}' is already registered")

        temp_password = generate_temp_password()

        user = User(
            email=data.email,
            hashed_password=hash_password(temp_password),
            full_name=data.full_name,
            phone=data.phone,
            must_change_password=True,
            created_by=self.acting_user_id,
        )
        self.db.add(user)
        await self.db.flush()

        # Org membership
        member = OrganizationMember(
            user_id=user.id,
            tenant_id=self.tenant_id,
            role=data.role,
            is_owner=False,
            invited_by=self.acting_user_id,
            created_by=self.acting_user_id,
        )
        self.db.add(member)

        # Default permissions based on role
        default_perms = ROLE_DEFAULT_PERMISSIONS.get(
            data.role, ROLE_DEFAULT_PERMISSIONS[UserRole.VIEWER]
        )
        perms = UserPermission(
            user_id=user.id,
            tenant_id=self.tenant_id,
            created_by=self.acting_user_id,
            **default_perms,
        )
        self.db.add(perms)
        await self.db.flush()

        # Send welcome email
        send_user_welcome(
            to=data.email,
            full_name=data.full_name,
            tenant_name=tenant_name,
            tenant_slug=tenant_slug,
            role=data.role.value,
            temp_password=temp_password,
            dashboard_url=settings.dashboard_url,
        )

        logger.info(
            f"User created: {data.email} role={data.role.value} "
            f"tenant={tenant_slug}"
        )
        return user, temp_password

    # ── List users in tenant ──────────────────────────────────────

    async def list_users(self) -> list[dict]:
        result = await self.db.execute(
            select(OrganizationMember, User, UserPermission)
            .join(User, User.id == OrganizationMember.user_id)
            .outerjoin(
                UserPermission,
                and_(
                    UserPermission.user_id == OrganizationMember.user_id,
                    UserPermission.tenant_id == self.tenant_id,
                    UserPermission.deleted_at.is_(None),
                ),
            )
            .where(
                and_(
                    OrganizationMember.tenant_id == self.tenant_id,
                    OrganizationMember.deleted_at.is_(None),
                    User.deleted_at.is_(None),
                )
            )
            .order_by(OrganizationMember.created_at.asc())
        )
        rows = result.all()
        return [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
                "is_active": user.is_active,
                "is_superadmin": user.is_superadmin,
                "status": user.status,
                "must_change_password": user.must_change_password,
                "role": member.role,
                "is_owner": member.is_owner,
                "permissions": perms,
            }
            for member, user, perms in rows
        ]

    # ── Get single user ───────────────────────────────────────────

    async def get_user(self, user_id: str) -> dict:
        result = await self.db.execute(
            select(OrganizationMember, User, UserPermission)
            .join(User, User.id == OrganizationMember.user_id)
            .outerjoin(
                UserPermission,
                and_(
                    UserPermission.user_id == OrganizationMember.user_id,
                    UserPermission.tenant_id == self.tenant_id,
                    UserPermission.deleted_at.is_(None),
                ),
            )
            .where(
                and_(
                    OrganizationMember.user_id == user_id,
                    OrganizationMember.tenant_id == self.tenant_id,
                    OrganizationMember.deleted_at.is_(None),
                    User.deleted_at.is_(None),
                )
            )
        )
        row = result.first()
        if not row:
            raise NotFoundError("User")
        member, user, perms = row
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_active": user.is_active,
            "is_superadmin": user.is_superadmin,
            "status": user.status,
            "must_change_password": user.must_change_password,
            "role": member.role,
            "is_owner": member.is_owner,
            "permissions": perms,
        }

    # ── Update user ───────────────────────────────────────────────

    async def update_user(self, user_id: str, data: UpdateUserRequest) -> dict:
        user_result = await self.db.execute(
            select(User).where(
                and_(User.id == user_id, User.deleted_at.is_(None))
            )
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User")

        if data.full_name is not None:
            user.full_name = data.full_name
        if data.phone is not None:
            user.phone = data.phone
        if data.is_active is not None:
            user.is_active = data.is_active
        user.updated_by = self.acting_user_id

        if data.role is not None:
            member_result = await self.db.execute(
                select(OrganizationMember).where(
                    and_(
                        OrganizationMember.user_id == user_id,
                        OrganizationMember.tenant_id == self.tenant_id,
                        OrganizationMember.deleted_at.is_(None),
                    )
                )
            )
            member = member_result.scalar_one_or_none()
            if member:
                member.role = data.role

        await self.db.flush()
        return await self.get_user(user_id)

    # ── Update permissions ────────────────────────────────────────

    async def update_permissions(
        self, user_id: str, data: UserPermissionSchema
    ) -> UserPermission:
        result = await self.db.execute(
            select(UserPermission).where(
                and_(
                    UserPermission.user_id == user_id,
                    UserPermission.tenant_id == self.tenant_id,
                    UserPermission.deleted_at.is_(None),
                )
            )
        )
        perms = result.scalar_one_or_none()

        if perms:
            for k, v in data.model_dump().items():
                setattr(perms, k, v)
            perms.updated_by = self.acting_user_id
        else:
            perms = UserPermission(
                user_id=user_id,
                tenant_id=self.tenant_id,
                created_by=self.acting_user_id,
                **data.model_dump(),
            )
            self.db.add(perms)

        await self.db.flush()
        return perms

    # ── Deactivate user ───────────────────────────────────────────

    async def deactivate_user(self, user_id: str) -> None:
        if user_id == self.acting_user_id:
            raise ValidationError("You cannot deactivate your own account")

        user_result = await self.db.execute(
            select(User).where(
                and_(User.id == user_id, User.deleted_at.is_(None))
            )
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User")
        user.is_active = False
        user.updated_by = self.acting_user_id
        await self.db.flush()

    # ── Reset password ────────────────────────────────────────────

    async def reset_user_password(
        self, user_id: str, tenant_slug: str, tenant_name: str
    ) -> None:
        user_data = await self.get_user(user_id)

        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()

        temp_password = generate_temp_password()
        user.hashed_password = hash_password(temp_password)
        user.must_change_password = True
        user.updated_by = self.acting_user_id
        await self.db.flush()

        send_user_welcome(
            to=user.email,
            full_name=user.full_name,
            tenant_name=tenant_name,
            tenant_slug=tenant_slug,
            role=str(user_data.get("role", "viewer")),
            temp_password=temp_password,
            dashboard_url=settings.dashboard_url,
        )

    # ── Get my permissions ────────────────────────────────────────

    async def get_my_permissions(self, user_id: str) -> UserPermission | None:
        result = await self.db.execute(
            select(UserPermission).where(
                and_(
                    UserPermission.user_id == user_id,
                    UserPermission.tenant_id == self.tenant_id,
                    UserPermission.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()