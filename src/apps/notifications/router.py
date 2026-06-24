from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.exceptions import AppException
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.notifications.service import PushNotificationService
from pydantic import BaseModel

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class RegisterDeviceRequest(BaseModel):
    token: str
    platform: str = "expo"


@router.post("/devices", status_code=201)
async def register_device(
    data: RegisterDeviceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from src.apps.tenancy.dependencies import get_current_tenant

    tenant = await get_current_tenant(db, current_user)
    svc = PushNotificationService(db=db, tenant_id=tenant.id)
    await svc.register_device(current_user.id, data.token, data.platform)
    return {"success": True, "message": "Device registered"}


@router.delete("/devices/{token}")
async def unregister_device(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from src.apps.tenancy.dependencies import get_current_tenant

    tenant = await get_current_tenant(db, current_user)
    svc = PushNotificationService(db=db, tenant_id=tenant.id)
    await svc.unregister_device(current_user.id, token)
    return {"success": True, "message": "Device unregistered"}
