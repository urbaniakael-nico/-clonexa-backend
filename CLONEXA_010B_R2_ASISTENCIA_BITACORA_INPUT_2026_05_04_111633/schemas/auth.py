from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClonexaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


class LoginRequest(ClonexaSchema):
    email: str
    password: str = Field(min_length=1)


class ChangePasswordRequest(ClonexaSchema):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=72)


class CompanyUserOut(ClonexaSchema):
    id: UUID
    company_id: UUID
    email: str
    full_name: str
    role: str
    status: str
    must_change_password: bool
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None
    last_password_reset_at: Optional[datetime] = None
    company_name: Optional[str] = None
    company_slug: Optional[str] = None


class TokenResponse(ClonexaSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: CompanyUserOut


class CompanyMiniOut(ClonexaSchema):
    id: UUID
    name: str
    slug: str
    timezone: Optional[str] = None
    status: Optional[str] = None
    plan: Optional[str] = None


class MeResponse(ClonexaSchema):
    user: CompanyUserOut
    company: CompanyMiniOut
    modules: list[dict[str, Any]] = []


class AdminCreateCompanyUserRequest(ClonexaSchema):
    email: str
    full_name: str
    role: str = "company_admin"
    password: str = Field(min_length=1, max_length=72)
    status: str = "active"


class AdminUpdateCompanyUserRequest(ClonexaSchema):
    full_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None


class AdminResetPasswordRequest(ClonexaSchema):
    password: Optional[str] = Field(default=None, max_length=72)


class AdminResetPasswordResponse(ClonexaSchema):
    ok: bool
    temporary_password: str
    must_change_password: bool


class UnlockUserResponse(ClonexaSchema):
    ok: bool
