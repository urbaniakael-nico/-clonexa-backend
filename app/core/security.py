from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import jwt

from app.core.config import get_settings

settings = get_settings()


def create_access_token(subject: str, company_id: UUID | None = None, expires_minutes: int | None = None) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expires,
    }
    if company_id:
        payload["company_id"] = str(company_id)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
