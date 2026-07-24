from __future__ import annotations

from pydantic import BaseModel, Field


class CaptchaResponse(BaseModel):
    captcha_id: str
    image_base64: str


class RegisterRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    password: str = Field(min_length=6, max_length=64)
    nickname: str = Field(default="", max_length=60)
    captcha_id: str
    captcha_text: str = Field(min_length=1, max_length=6)


class LoginRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    password: str = Field(min_length=1, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    phone: str
    nickname: str
    avatar_url: str | None = None
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserUpdateRequest(BaseModel):
    nickname: str | None = Field(default=None, max_length=60)
    avatar_url: str | None = Field(default=None, max_length=500)


# ── UserPlan ──

class UserPlanCreateRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=1, max_length=100)
    date_range: str = Field(default="", max_length=60)
    day_count: int = Field(default=1, ge=1, le=30)
    preferences: str = Field(default="[]", max_length=2000)
    plan_data: str = Field(default="{}", max_length=100000)


class UserPlanResponse(BaseModel):
    id: str
    user_id: str
    title: str
    destination: str
    date_range: str
    day_count: int
    preferences: str
    plan_data: str
    created_at: str
    updated_at: str


class UserPlanUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    destination: str | None = Field(default=None, max_length=100)
    date_range: str | None = Field(default=None, max_length=60)
    day_count: int | None = Field(default=None, ge=1, le=30)
    preferences: str | None = Field(default=None, max_length=2000)
    plan_data: str | None = Field(default=None, max_length=100000)


# ── UserJournal ──

class UserJournalCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)
    date: str = Field(default="", max_length=30)
    body: str = Field(default="", max_length=10000)
    photos: str = Field(default="[]", max_length=100000)


class UserJournalUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    date: str | None = Field(default=None, max_length=30)
    body: str | None = Field(default=None, max_length=10000)
    photos: str | None = Field(default=None, max_length=100000)


class UserJournalResponse(BaseModel):
    id: str
    user_id: str
    title: str
    location: str
    date: str
    body: str
    photos: str
    created_at: str
    updated_at: str


# ── UserFootprint ──

class UserFootprintCreateRequest(BaseModel):
    city_name: str = Field(min_length=1, max_length=60)
    province_name: str = Field(default="", max_length=60)
    latitude: float | None = None
    longitude: float | None = None


class UserFootprintResponse(BaseModel):
    id: str
    user_id: str
    city_name: str
    province_name: str
    latitude: float | None
    longitude: float | None
    visit_count: int
    first_visited_at: str
    last_visited_at: str
