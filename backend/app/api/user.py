from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdateRequest
from app.services.auth_service import get_user, update_user

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)):
    """Get current authenticated user's profile."""
    # current_user is already fetched by get_current_user dependency
    return UserResponse(
        id=current_user.id,
        phone=_mask(current_user.phone),
        nickname=current_user.nickname,
        avatar_url=current_user.avatar_url or None,
        created_at=current_user.created_at,
    )


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    request: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    try:
        return await update_user(db, current_user.id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _mask(phone: str) -> str:
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone
