import logging
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.apps.notifications.models import DeviceToken

logger = logging.getLogger(__name__)


class PushNotificationService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def register_device(
        self, user_id: str, token: str, platform: str = "expo"
    ) -> DeviceToken:
        existing = await self.db.execute(
            select(DeviceToken).where(
                DeviceToken.user_id == user_id,
                DeviceToken.token == token,
                DeviceToken.tenant_id == self.tenant_id,
                DeviceToken.deleted_at.is_(None),
            )
        )
        dt = existing.scalar_one_or_none()
        if dt:
            dt.is_active = True
            await self.db.flush()
            return dt

        dt = DeviceToken(
            user_id=user_id,
            token=token,
            platform=platform,
            tenant_id=self.tenant_id,
        )
        self.db.add(dt)
        await self.db.flush()
        return dt

    async def unregister_device(self, user_id: str, token: str) -> None:
        await self.db.execute(
            delete(DeviceToken).where(
                DeviceToken.user_id == user_id,
                DeviceToken.token == token,
                DeviceToken.tenant_id == self.tenant_id,
            )
        )
        await self.db.flush()

    async def get_tokens_for_user(self, user_id: str) -> list[str]:
        result = await self.db.execute(
            select(DeviceToken.token).where(
                DeviceToken.user_id == user_id,
                DeviceToken.tenant_id == self.tenant_id,
                DeviceToken.is_active.is_(True),
                DeviceToken.deleted_at.is_(None),
            )
        )
        return [row[0] for row in result.all() if row[0]]


async def send_push_notification(
    push_tokens: list[str],
    title: str,
    body: str,
    data: dict | None = None,
) -> int:
    if not push_tokens:
        return 0

    try:
        import httpx

        messages = [
            {
                "to": token,
                "sound": "default",
                "title": title,
                "body": body,
                "data": data or {},
                "priority": "high",
            }
            for token in push_tokens
        ]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=messages,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.error(
                    "Expo push API error: %s %s", resp.status_code, resp.text
                )
            return len(messages)
    except ImportError:
        logger.warning("httpx not installed, cannot send push notifications")
        return 0
    except Exception as e:
        logger.error("Failed to send push notifications: %s", e)
        return 0
