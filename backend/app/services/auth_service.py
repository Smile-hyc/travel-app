from __future__ import annotations

from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)
from app.models.user import RefreshToken, User
from app.schemas.user import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.captcha_service import verify_captcha

settings = get_settings()
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def _verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        phone=_mask_phone(user.phone),
        nickname=user.nickname,
        avatar_url=user.avatar_url or None,
        created_at=user.created_at,
    )


def _mask_phone(phone: str) -> str:
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone


async def register(db: AsyncSession, request: RegisterRequest) -> TokenResponse:
    """Register a new user."""
    # Verify captcha
    if not verify_captcha(request.captcha_id, request.captcha_text):
        raise ValueError("验证码错误或已过期")

    # Check phone uniqueness
    result = await db.execute(select(User).where(User.phone == request.phone.strip()))
    if result.scalar_one_or_none() is not None:
        raise ValueError("该手机号已注册")

    # Create user
    now = datetime.now(timezone.utc).isoformat()
    user = User(
        phone=request.phone.strip(),
        password_hash=_hash_password(request.password),
        nickname=request.nickname.strip() or f"旅行者{request.phone.strip()[-4:]}",
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.commit()

    return await _create_token_pair(db, user)


async def login(db: AsyncSession, request: LoginRequest) -> TokenResponse:
    """Login with phone and password."""
    result = await db.execute(select(User).where(User.phone == request.phone.strip()))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("手机号未注册")
    if not _verify_password(request.password, user.password_hash):
        raise ValueError("密码错误")
    return await _create_token_pair(db, user)


async def refresh(db: AsyncSession, refresh_token_str: str) -> TokenResponse:
    """Refresh access token using refresh token."""
    token_hash = hash_token(refresh_token_str)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == 0,
        )
    )
    stored = result.scalar_one_or_none()
    if stored is None:
        raise ValueError("刷新令牌无效")

    if stored.expires_at < datetime.now(timezone.utc).isoformat():
        raise ValueError("刷新令牌已过期，请重新登录")

    # Revoke old token
    stored.revoked = 1
    await db.commit()

    # Get user
    result = await db.execute(select(User).where(User.id == stored.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    return await _create_token_pair(db, user)


async def get_user(db: AsyncSession, user_id: str) -> UserResponse:
    """Get user by id."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")
    return _user_to_response(user)


async def update_user(db: AsyncSession, user_id: str, request: UserUpdateRequest) -> UserResponse:
    """Update user profile."""
    values: dict[str, object] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if request.nickname is not None:
        values["nickname"] = request.nickname.strip()
    if request.avatar_url is not None:
        values["avatar_url"] = request.avatar_url.strip()

    await db.execute(update(User).where(User.id == user_id).values(**values))
    await db.commit()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")
    return _user_to_response(user)


async def _create_token_pair(db: AsyncSession, user: User) -> TokenResponse:
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    # Store refresh token hash
    token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=(datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)).isoformat(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(token_record)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=_user_to_response(user),
    )
