from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MeResponse, TokenResponse
from app.services.auth_service import (
    authenticate_user,
    change_password as change_password_service,
    company_mini_payload,
    company_modules_payload,
    company_user_out_payload,
    create_access_token,
    get_access_token_expire_minutes,
    get_current_company_user,
)

router = APIRouter()


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido.")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization Bearer inválido.")
    return parts[1]


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await authenticate_user(db, payload.email, payload.password)
    expires_in_minutes = get_access_token_expire_minutes()
    access_token = create_access_token(
        {
            "sub": str(user.id),
            "user_id": str(user.id),
            "email": user.email,
            "company_id": str(user.company_id),
            "role": user.role,
        },
        expires_minutes=expires_in_minutes,
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in_minutes * 60,
        user=await company_user_out_payload(db, user),
    )


@router.get("/me", response_model=MeResponse)
async def me(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    token = extract_bearer_token(authorization)
    user = await get_current_company_user(db, token)
    return MeResponse(
        user=await company_user_out_payload(db, user),
        company=await company_mini_payload(db, user.company_id),
        modules=await company_modules_payload(db, user.company_id),
    )


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    token = extract_bearer_token(authorization)
    user = await get_current_company_user(db, token)
    return await change_password_service(db, user, payload.current_password, payload.new_password)


@router.post("/logout")
async def logout():
    return {"ok": True}
