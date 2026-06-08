import hashlib
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from src.apps.identity.models import User, RefreshToken, UserRole, OrganizationMember
from src.apps.identity.schemas import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
)
from src.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.core.exceptions import (
    ConflictError,
    UnauthorizedError,
    NotFoundError,
    ValidationError,
)
from src.core.config import settings
import secrets
import string
from src.apps.identity.models import UserPermission, OrganizationMember
from src.apps.identity.schemas import (
    CreateUserRequest, UpdateUserRequest,
    UserPermissionSchema, ROLE_DEFAULT_PERMISSIONS,
    CreateTenantAdminRequest,
)
from src.core.email import send_user_welcome, send_tenant_admin_welcome


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: RegisterRequest) -> User:
        # Check email uniqueness
        existing = await self.db.execute(
            select(User).where(User.email == data.email, User.deleted_at.is_(None))
        )
        if existing.scalar_one_or_none():
            raise ConflictError("Email already registered")

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            phone=data.phone,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def login(
        self,
        data: LoginRequest,
        device_info: str | None = None,
        ip: str | None = None,
        tenant_slug: str | None = None,  # ← new param
    ) -> TokenResponse:
        

        # Fetch user by email
        result = await self.db.execute(
            select(User).where(
                and_(User.email == data.email, User.deleted_at.is_(None))
            )
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password")

        if not user.is_active:
            raise UnauthorizedError("Account is inactive")

        # Superadmin can log in without a tenant slug
        if not user.is_superadmin:
            if not tenant_slug:
                raise UnauthorizedError(
                    "Organisation slug is required"
                )

            # Validate that user is actually a member of this tenant
            from src.apps.tenancy.models import Tenant
            from src.apps.identity.models import OrganizationMember

            tenant_result = await self.db.execute(
                select(Tenant).where(
                    and_(
                        Tenant.slug == tenant_slug,
                        Tenant.is_active.is_(True),
                        Tenant.deleted_at.is_(None),
                    )
                )
            )
            tenant = tenant_result.scalar_one_or_none()
            if not tenant:
                raise UnauthorizedError(
                    "Organisation not found or inactive"
                )

            member_result = await self.db.execute(
                select(OrganizationMember).where(
                    and_(
                        OrganizationMember.user_id == user.id,
                        OrganizationMember.tenant_id == tenant.id,
                        OrganizationMember.deleted_at.is_(None),
                    )
                )
            )
            member = member_result.scalar_one_or_none()
            if not member:
                raise UnauthorizedError(
                    "You are not a member of this organisation"
                )

        extra = {
            "is_superadmin": user.is_superadmin,
            "must_change_password": user.must_change_password,
        }
        access_token = create_access_token(user.id, extra_data=extra)
        refresh_token = create_refresh_token(user.id)

        token_record = RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(refresh_token),
            device_info=device_info,
            ip_address=ip,
        )
        self.db.add(token_record)
        await self.db.flush()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise UnauthorizedError("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")

        token_hash = _hash_token(refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.is_revoked.is_(False),
                )
            )
        )
        token_record = result.scalar_one_or_none()
        if not token_record:
            raise UnauthorizedError("Refresh token revoked or not found")

        # Rotate: revoke old, issue new
        token_record.is_revoked = True

        user_id = payload["sub"]
        result = await self.db.execute(
            select(User).where(
                and_(User.id == user_id, User.deleted_at.is_(None))
            )
        )
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise UnauthorizedError("User not found or inactive")

        extra = {"is_superadmin": user.is_superadmin}
        new_access = create_access_token(user.id, extra_data=extra)
        new_refresh = create_refresh_token(user.id)

        new_record = RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(new_refresh),
            device_info=token_record.device_info,
            ip_address=token_record.ip_address,
        )
        self.db.add(new_record)
        await self.db.flush()

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )

    async def logout(self, refresh_token: str) -> None:
        token_hash = _hash_token(refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()
        if record:
            record.is_revoked = True
        await self.db.flush()

    async def get_user_by_id(self, user_id: str) -> User:
        result = await self.db.execute(
            select(User).where(
                and_(User.id == user_id, User.deleted_at.is_(None))
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User")
        return user

    async def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        user = await self.get_user_by_id(user_id)
        if not verify_password(current_password, user.hashed_password):
            raise ValidationError("Current password is incorrect")
        user.hashed_password = hash_password(new_password)
        user.must_change_password = False  # ← clear the flag
        user.updated_by = user_id
        await self.db.flush()

    async def update_profile(self, user_id: str, data: dict) -> User:
        user = await self.get_user_by_id(user_id)
        for key, value in data.items():
            if value is not None:
                setattr(user, key, value)
        await self.db.flush()
        return user


def generate_temp_password(length: int = 12) -> str:
    """Generate a secure readable temporary password."""
    alphabet = string.ascii_letters + string.digits
    # Ensure at least one uppercase, one digit
    password = (
        secrets.choice(string.ascii_uppercase) +
        secrets.choice(string.digits) +
        "".join(secrets.choice(alphabet) for _ in range(length - 2))
    )
    # Shuffle
    chars = list(password)
    secrets.SystemRandom().shuffle(chars)
    print(chars)
    return "".join(chars)


class UserManagementService:
    def __init__(self, db: AsyncSession, tenant_id: str, acting_user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.acting_user_id = acting_user_id

    # ── Create tenant admin (called by super admin) ───────────────

    async def create_tenant_admin(
        self,
        tenant_id: str,
        tenant_name: str,
        tenant_slug: str,
        data: "CreateTenantAdminRequest",
    ) -> tuple["User", str]:
        """
        Creates a user + marks them as company_admin for the tenant.
        Returns (user, temp_password).
        """
        from src.apps.identity.models import User, OrganizationMember, UserRole

        # Check email not already used
        existing = await self.db.execute(
            select(User).where(
                and_(User.email == data.email, User.deleted_at.is_(None))
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError("Email already registered")

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

        # Create org membership as company_admin
        member = OrganizationMember(
            user_id=user.id,
            tenant_id=tenant_id,
            role=UserRole.COMPANY_ADMIN,
            is_owner=True,
            invited_by=self.acting_user_id,
            created_by=self.acting_user_id,
        )
        self.db.add(member)

        # Create full permissions for company admin
        perms = UserPermission(
            user_id=user.id,
            tenant_id=tenant_id,
            created_by=self.acting_user_id,
            **ROLE_DEFAULT_PERMISSIONS[UserRole.COMPANY_ADMIN],
        )
        self.db.add(perms)
        await self.db.flush()

        # Send welcome email
        send_tenant_admin_welcome(
            to=data.email,
            full_name=data.full_name,
            tenant_name=tenant_name,
            tenant_slug=tenant_slug,
            temp_password=temp_password,
            dashboard_url=settings.dashboard_url,
        )

        return user, temp_password

    # ── Create user (called by tenant admin) ─────────────────────

    async def create_user(
        self,
        tenant_slug: str,
        tenant_name: str,
        data: "CreateUserRequest",
    ) -> tuple["User", str]:
        from src.apps.identity.models import User, OrganizationMember

        # Check email uniqueness globally
        existing = await self.db.execute(
            select(User).where(
                and_(User.email == data.email, User.deleted_at.is_(None))
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError("Email already registered")

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
        default_perms = ROLE_DEFAULT_PERMISSIONS.get(data.role, {})
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
        users = []
        for member, user, perms in rows:
            users.append({
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
            })
        return users

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

    async def update_user(self, user_id: str, data: "UpdateUserRequest") -> dict:
        # Update User model fields
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

        # Update role in membership
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
        self, user_id: str, data: "UserPermissionSchema"
    ) -> "UserPermission":
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
        user_result = await self.db.execute(
            select(User).where(
                and_(User.id == user_id, User.deleted_at.is_(None))
            )
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User")

        # Prevent deactivating yourself
        if user_id == self.acting_user_id:
            raise ValidationError("You cannot deactivate your own account")

        user.is_active = False
        await self.db.flush()

    # ── Reset password (resend credentials) ──────────────────────

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

    # ── Get permissions for current user ─────────────────────────

    async def get_my_permissions(self, user_id: str) -> "UserPermission | None":
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