from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user import (
    UserFootprintCreateRequest,
    UserFootprintResponse,
    UserPlanCreateRequest,
    UserPlanResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.auth_service import (
    add_user_footprint,
    create_user_plan,
    get_user,
    get_user_footprints,
    get_user_plans,
    update_user,
)

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)):
    """Get current authenticated user's profile."""
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


# ── User Plans ──

@router.get("/plans", response_model=list[UserPlanResponse])
async def list_user_plans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all plans for the current user."""
    return await get_user_plans(db, current_user.id)


@router.post("/plans", response_model=UserPlanResponse, status_code=201)
async def create_plan(
    request: UserPlanCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a travel plan to the current user's account."""
    try:
        return await create_user_plan(db, current_user.id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── User Footprints ──

@router.get("/footprints", response_model=list[UserFootprintResponse])
async def list_user_footprints(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all footprint records for the current user."""
    return await get_user_footprints(db, current_user.id)


@router.post("/footprints", response_model=UserFootprintResponse, status_code=201)
async def add_footprint(
    request: UserFootprintCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a city to the user's travel footprint."""
    try:
        return await add_user_footprint(db, current_user.id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
