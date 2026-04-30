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
        self, data: LoginRequest, device_info: str | None = None, ip: str | None = None
    ) -> TokenResponse:
        # Fetch user
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

        # Build token extra claims
        extra = {"is_superadmin": user.is_superadmin}

        access_token = create_access_token(user.id, extra_data=extra)
        refresh_token = create_refresh_token(user.id)

        # Persist refresh token hash
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
        await self.db.flush()

    async def update_profile(self, user_id: str, data: dict) -> User:
        user = await self.get_user_by_id(user_id)
        for key, value in data.items():
            if value is not None:
                setattr(user, key, value)
        await self.db.flush()
        return user