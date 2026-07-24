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
from app.models.user import RefreshToken, User, UserPlan, UserFootprint, UserJournal
from app.schemas.user import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserFootprintCreateRequest,
    UserFootprintResponse,
    UserJournalCreateRequest,
    UserJournalResponse,
    UserJournalUpdateRequest,
    UserPlanCreateRequest,
    UserPlanResponse,
    UserPlanUpdateRequest,
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


# ── UserPlan CRUD ──

async def get_user_plans(db: AsyncSession, user_id: str) -> list[UserPlanResponse]:
    result = await db.execute(
        select(UserPlan).where(UserPlan.user_id == user_id).order_by(UserPlan.updated_at.desc())
    )
    plans = result.scalars().all()
    return [_plan_to_response(p) for p in plans]


async def create_user_plan(db: AsyncSession, user_id: str, request: UserPlanCreateRequest) -> UserPlanResponse:
    now = datetime.now(timezone.utc).isoformat()
    plan = UserPlan(
        user_id=user_id,
        title=request.title.strip(),
        destination=request.destination.strip(),
        date_range=request.date_range.strip(),
        day_count=request.day_count,
        preferences=request.preferences,
        plan_data=request.plan_data,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    await db.commit()
    return _plan_to_response(plan)


def _plan_to_response(plan: UserPlan) -> UserPlanResponse:
    return UserPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        title=plan.title,
        destination=plan.destination,
        date_range=plan.date_range,
        day_count=plan.day_count,
        preferences=plan.preferences,
        plan_data=plan.plan_data,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


async def update_user_plan(
    db: AsyncSession, user_id: str, plan_id: str, request: "UserPlanUpdateRequest",
) -> UserPlanResponse:
    result = await db.execute(
        select(UserPlan).where(UserPlan.id == plan_id, UserPlan.user_id == user_id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise ValueError("计划不存在或不属于当前用户")
    now = datetime.now(timezone.utc).isoformat()
    if request.title is not None:
        plan.title = request.title
    if request.destination is not None:
        plan.destination = request.destination
    if request.date_range is not None:
        plan.date_range = request.date_range
    if request.day_count is not None:
        plan.day_count = request.day_count
    if request.preferences is not None:
        plan.preferences = request.preferences
    if request.plan_data is not None:
        plan.plan_data = request.plan_data
    plan.updated_at = now
    await db.commit()
    return _plan_to_response(plan)


async def delete_user_plan(db: AsyncSession, user_id: str, plan_id: str) -> None:
    result = await db.execute(
        select(UserPlan).where(UserPlan.id == plan_id, UserPlan.user_id == user_id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise ValueError("计划不存在或不属于当前用户")
    await db.delete(plan)
    await db.commit()


# ── UserFootprint CRUD ──

async def get_user_footprints(db: AsyncSession, user_id: str) -> list[UserFootprintResponse]:
    result = await db.execute(
        select(UserFootprint).where(UserFootprint.user_id == user_id).order_by(UserFootprint.last_visited_at.desc())
    )
    footprints = result.scalars().all()
    return [_footprint_to_response(f) for f in footprints]


async def add_user_footprint(db: AsyncSession, user_id: str, request: UserFootprintCreateRequest) -> UserFootprintResponse:
    # Check if city already exists for this user — if so, bump visit count
    result = await db.execute(
        select(UserFootprint).where(
            UserFootprint.user_id == user_id,
            UserFootprint.city_name == request.city_name.strip(),
        )
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(timezone.utc).isoformat()
    if existing is not None:
        existing.visit_count += 1
        existing.last_visited_at = now
        await db.commit()
        return _footprint_to_response(existing)

    footprint = UserFootprint(
        user_id=user_id,
        city_name=request.city_name.strip(),
        province_name=request.province_name.strip(),
        latitude=request.latitude,
        longitude=request.longitude,
        visit_count=1,
        first_visited_at=now,
        last_visited_at=now,
    )
    db.add(footprint)
    await db.commit()
    return _footprint_to_response(footprint)


def _footprint_to_response(fp: UserFootprint) -> UserFootprintResponse:
    return UserFootprintResponse(
        id=fp.id,
        user_id=fp.user_id,
        city_name=fp.city_name,
        province_name=fp.province_name,
        latitude=fp.latitude,
        longitude=fp.longitude,
        visit_count=fp.visit_count,
        first_visited_at=fp.first_visited_at,
        last_visited_at=fp.last_visited_at,
    )


# ── UserJournal CRUD ──

async def get_user_journals(db: AsyncSession, user_id: str) -> list[UserJournalResponse]:
    result = await db.execute(
        select(UserJournal)
        .where(UserJournal.user_id == user_id)
        .order_by(UserJournal.date.desc(), UserJournal.created_at.desc())
    )
    journals = result.scalars().all()
    return [_journal_to_response(j) for j in journals]


async def create_user_journal(
    db: AsyncSession, user_id: str, request: UserJournalCreateRequest,
) -> UserJournalResponse:
    now = datetime.now(timezone.utc).isoformat()
    journal = UserJournal(
        user_id=user_id,
        title=request.title.strip(),
        location=request.location.strip(),
        date=request.date.strip(),
        body=request.body,
        photos=request.photos,
        created_at=now,
        updated_at=now,
    )
    db.add(journal)
    await db.commit()
    return _journal_to_response(journal)


async def update_user_journal(
    db: AsyncSession, user_id: str, journal_id: str, request: UserJournalUpdateRequest,
) -> UserJournalResponse:
    result = await db.execute(
        select(UserJournal).where(UserJournal.id == journal_id, UserJournal.user_id == user_id)
    )
    journal = result.scalar_one_or_none()
    if journal is None:
        raise ValueError("日记不存在或不属于当前用户")
    now = datetime.now(timezone.utc).isoformat()
    if request.title is not None:
        journal.title = request.title.strip()
    if request.location is not None:
        journal.location = request.location.strip()
    if request.date is not None:
        journal.date = request.date.strip()
    if request.body is not None:
        journal.body = request.body
    if request.photos is not None:
        journal.photos = request.photos
    journal.updated_at = now
    await db.commit()
    return _journal_to_response(journal)


async def delete_user_journal(db: AsyncSession, user_id: str, journal_id: str) -> None:
    result = await db.execute(
        select(UserJournal).where(UserJournal.id == journal_id, UserJournal.user_id == user_id)
    )
    journal = result.scalar_one_or_none()
    if journal is None:
        raise ValueError("日记不存在或不属于当前用户")
    await db.delete(journal)
    await db.commit()


def _journal_to_response(j: UserJournal) -> UserJournalResponse:
    return UserJournalResponse(
        id=j.id,
        user_id=j.user_id,
        title=j.title,
        location=j.location,
        date=j.date,
        body=j.body,
        photos=j.photos,
        created_at=j.created_at,
        updated_at=j.updated_at,
    )
