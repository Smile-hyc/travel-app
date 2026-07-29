from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import (
    CaptchaResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth_service import login, refresh, register
from app.services.captcha_service import generate_captcha

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/captcha", response_model=CaptchaResponse)
async def get_captcha():
    """Generate a captcha image. Returns captcha_id and base64-encoded PNG."""
    captcha_id, image_base64 = generate_captcha()
    return CaptchaResponse(captcha_id=captcha_id, image_base64=image_base64)


@router.post("/register", response_model=TokenResponse)
async def register_user(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    try:
        return await register(db, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login_user(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with phone and password."""
    try:
        return await login(db, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token."""
    try:
        return await refresh(db, request.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
