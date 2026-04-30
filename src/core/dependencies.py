from typing import Annotated
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.security import decode_token
from src.core.exceptions import UnauthorizedError, ForbiddenError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> str:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedError("Invalid token payload")
        return user_id
    except ValueError:
        raise UnauthorizedError("Invalid or expired token")


class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, roles: list[str]) -> bool:
        for role in roles:
            if role in self.allowed_roles:
                return True
        raise ForbiddenError(
            f"Required roles: {', '.join(self.allowed_roles)}"
        )


# Type aliases for cleaner route signatures
DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUserID = Annotated[str, Depends(get_current_user_id)]