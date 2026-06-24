import logging
from src.core.config import settings

logger = logging.getLogger(__name__)

def init_sentry() -> None:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.2 if settings.is_production else 0.0,
            send_default_pii=False,
        )
        logger.info("Sentry initialized")
    except ImportError:
        logger.info("sentry-sdk not installed, skipping Sentry init")
