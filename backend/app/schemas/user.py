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
