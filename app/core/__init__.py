from uuid import UUID

from fastapi import Header, HTTPException, status


async def require_company_id(x_company_id: str | None = Header(default=None)) -> UUID:
    if not x_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Company-Id header is required",
        )

    try:
        return UUID(x_company_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Company-Id header",
        ) from exc

