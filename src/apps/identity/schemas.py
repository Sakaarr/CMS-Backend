from pydantic import BaseModel, EmailStr, field_validator, model_validator
from src.apps.identity.models import UserRole, UserStatus
import re



class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v.strip()
    

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    is_superadmin: bool
    status: UserStatus
    avatar_url: str | None
    must_change_password: bool = False 
    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    id: str
    user_id: str
    tenant_id: str
    role: UserRole
    is_owner: bool
    user: UserResponse

    model_config = {"from_attributes": True}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
        return v


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None



class CreateTenantAdminRequest(BaseModel):
    """Used by super admin when creating a tenant — creates the admin user too."""
    email: EmailStr
    full_name: str
    phone: str | None = None


class CreateUserRequest(BaseModel):
    """Used by tenant admin to create users within their org."""
    email: EmailStr
    full_name: str
    phone: str | None = None
    role: UserRole = UserRole.VIEWER

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v.strip()


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserPermissionSchema(BaseModel):
    can_projects: bool = True
    can_boq: bool = False
    can_procurement: bool = False
    can_inventory: bool = False
    can_site_ops: bool = False
    can_finance: bool = False
    can_quality: bool = False
    can_documents: bool = False
    can_subcontractors: bool = False

    model_config = {"from_attributes": True}


class UserWithPermissionsResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    is_superadmin: bool
    status: UserStatus
    must_change_password: bool
    role: UserRole | None = None
    permissions: UserPermissionSchema | None = None

    model_config = {"from_attributes": True}


# Default permissions per role
ROLE_DEFAULT_PERMISSIONS: dict[UserRole, dict] = {
    UserRole.SUPER_ADMIN: {
        "can_projects": True, "can_boq": True, "can_procurement": True,
        "can_inventory": True, "can_site_ops": True, "can_finance": True,
        "can_quality": True, "can_documents": True, "can_subcontractors": True,
    },
    UserRole.COMPANY_ADMIN: {
        "can_projects": True, "can_boq": True, "can_procurement": True,
        "can_inventory": True, "can_site_ops": True, "can_finance": True,
        "can_quality": True, "can_documents": True, "can_subcontractors": True,
    },
    UserRole.PROJECT_MANAGER: {
        "can_projects": True, "can_boq": True, "can_procurement": True,
        "can_inventory": True, "can_site_ops": True, "can_finance": False,
        "can_quality": True, "can_documents": True, "can_subcontractors": False,
    },
    UserRole.SITE_ENGINEER: {
        "can_projects": True, "can_boq": False, "can_procurement": False,
        "can_inventory": True, "can_site_ops": True, "can_finance": False,
        "can_quality": True, "can_documents": True, "can_subcontractors": False,
    },
    UserRole.FINANCE: {
        "can_projects": True, "can_boq": True, "can_procurement": True,
        "can_inventory": False, "can_site_ops": False, "can_finance": True,
        "can_quality": False, "can_documents": True, "can_subcontractors": False,
    },
    UserRole.PROCUREMENT: {
        "can_projects": True, "can_boq": False, "can_procurement": True,
        "can_inventory": True, "can_site_ops": False, "can_finance": False,
        "can_quality": False, "can_documents": True, "can_subcontractors": False,
    },
    UserRole.QA_OFFICER: {
        "can_projects": True, "can_boq": False, "can_procurement": False,
        "can_inventory": False, "can_site_ops": True, "can_finance": False,
        "can_quality": True, "can_documents": True, "can_subcontractors": False,
    },
    UserRole.VIEWER: {
        "can_projects": True, "can_boq": False, "can_procurement": False,
        "can_inventory": False, "can_site_ops": False, "can_finance": False,
        "can_quality": False, "can_documents": False, "can_subcontractors": False,
    },
}
