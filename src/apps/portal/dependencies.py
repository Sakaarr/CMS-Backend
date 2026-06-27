from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.core.database import get_db
from src.core.security import decode_token
from src.core.exceptions import UnauthorizedError
from src.apps.portal.models import SubcontractorUser

bearer_scheme = HTTPBearer(auto_error=False)


async def get_portal_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    if not credentials:
        raise UnauthorizedError("Missing authentication token")
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise UnauthorizedError("Invalid or expired token")
    if payload.get("type") != "portal_access":
        raise UnauthorizedError("Invalid token type")
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")
    request.state.portal_user_id = user_id
    request.state.portal_subcontractor_id = payload.get("subcontractor_id")
    request.state.portal_user_role = payload.get("role")
    return user_id


async def get_portal_user(
    user_id: str = Depends(get_portal_user_id),
    db: AsyncSession = Depends(get_db),
) -> SubcontractorUser:
    result = await db.execute(
        select(SubcontractorUser).where(
            SubcontractorUser.id == user_id,
            SubcontractorUser.is_active.is_(True),
            SubcontractorUser.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("Portal user not found or inactive")
    return user
