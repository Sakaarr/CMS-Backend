import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.core.config import settings
from src.core.database import create_all_tables
from src.core.exceptions import AppException
from src.core.middleware import RequestIDMiddleware, TimingMiddleware, TenantMiddleware
from src.apps.identity.router import router as auth_router
from src.apps.tenancy.router import router as tenancy_router
from src.apps.projects.router import router as projects_router
from src.apps.boq.router import router as boq_router
from src.apps.procurement.router import router as procurement_router
from src.apps.inventory.router import router as inventory_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting CMS Platform API...")
    await create_all_tables()
    await seed_superadmin()
    logger.info("Startup complete.")
    yield
    logger.info("Shutting down...")


async def seed_superadmin():
    """Creates the first superadmin on fresh startup if not exists."""
    from src.core.database import AsyncSessionLocal
    from src.apps.identity.models import User
    from src.core.security import hash_password
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.email == settings.first_superadmin_email)
        )
        if not result.scalar_one_or_none():
            admin = User(
                email=settings.first_superadmin_email,
                hashed_password=hash_password(settings.first_superadmin_password),
                full_name="Super Admin",
                is_superadmin=True,
            )
            db.add(admin)
            await db.commit()
            logger.info(f"Superadmin seeded: {settings.first_superadmin_email}")


app = FastAPI(
    title="CMS Platform API",
    description="Construction Management System — Multi-tenant SaaS",
    version="0.1.0",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

# Middleware (order matters — outermost runs first)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "error_code": getattr(exc, "error_code", None),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error"},
    )


# Routers
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(tenancy_router, prefix=settings.api_prefix)
app.include_router(projects_router, prefix=settings.api_prefix)
app.include_router(boq_router, prefix=settings.api_prefix)
app.include_router(procurement_router, prefix=settings.api_prefix)
app.include_router(inventory_router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
