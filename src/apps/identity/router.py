from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import CurrentUserID
from src.apps.identity.service import AuthService
from src.apps.identity.schemas import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
    ChangePasswordRequest,
    UpdateProfileRequest,
)
from src.apps.identity.dependencies import CurrentUser
from src.shared.response import APIResponse, success_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=APIResponse[UserResponse], status_code=201)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.register(data)
    return success_response(
        data=UserResponse.model_validate(user),
        message="Account created successfully",
    )


@router.post("/login", response_model=APIResponse[TokenResponse])
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    device_info = request.headers.get("User-Agent")
    ip = request.client.host if request.client else None
    tokens = await service.login(data, device_info=device_info, ip=ip)
    return success_response(data=tokens, message="Login successful")


@router.post("/refresh", response_model=APIResponse[TokenResponse])
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    tokens = await service.refresh(data.refresh_token)
    return success_response(data=tokens, message="Token refreshed")


@router.post("/logout", response_model=APIResponse[None])
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    await service.logout(data.refresh_token)
    return success_response(message="Logged out successfully")


@router.get("/me", response_model=APIResponse[UserResponse])
async def get_me(current_user: CurrentUser):
    return success_response(data=UserResponse.model_validate(current_user))


@router.patch("/me", response_model=APIResponse[UserResponse])
async def update_profile(
    data: UpdateProfileRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    updated = await service.update_profile(
        current_user.id,
        data.model_dump(exclude_none=True),
    )
    return success_response(
        data=UserResponse.model_validate(updated),
        message="Profile updated",
    )


@router.post("/change-password", response_model=APIResponse[None])
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    await service.change_password(
        current_user.id, data.current_password, data.new_password
    )
    return success_response(message="Password changed successfully")