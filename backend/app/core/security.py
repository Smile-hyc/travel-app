from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import RefreshToken, User

settings = get_settings()
_bearer_scheme = HTTPBearer(auto_error=False)


def _secret() -> str:
    return settings.jwt_secret


def _b64url_encode(data: bytes) -> str:
    """Base64URL encode without padding, per RFC 7515."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(encoded: str) -> bytes:
    """Base64URL decode, auto-adds padding if needed."""
    padding = 4 - len(encoded) % 4
    if padding != 4:
        encoded += "=" * padding
    return base64.urlsafe_b64decode(encoded)


def _sign(data: str) -> str:
    """Create an HMAC-SHA256 signature over *data* and base64url-encode it."""
    mac = hmac.new(
        _secret().encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    )
    return _b64url_encode(mac.digest())


def create_access_token(user_id: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + settings.access_token_expire_minutes * 60,
        "type": "access",
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}"
    return f"{signing_input}.{_sign(signing_input)}"


def create_refresh_token(user_id: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + settings.refresh_token_expire_days * 86400,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}"
    return f"{signing_input}.{_sign(signing_input)}"


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT access/refresh token.  Raises ValueError on any failure."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("令牌格式无效: JWT 必须包含三个部分")

    header_b64, payload_b64, sig_b64 = parts

    # 1. Verify signature (constant-time comparison)
    signing_input = f"{header_b64}.{payload_b64}"
    expected_sig = _sign(signing_input)
    if not hmac.compare_digest(sig_b64, expected_sig):
        raise ValueError("签名验证失败")

    # 2. Decode payload
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload: dict[str, Any] = json.loads(payload_bytes)
    except Exception as e:
        raise ValueError(f"载荷解析失败: {e}")

    # 3. Validate expiration
    exp = payload.get("exp", 0)
    now = int(time.time())
    if not isinstance(exp, (int, float)) or exp < now:
        raise ValueError(f"令牌已过期 (exp={exp}, now={now}, diff={now - exp}s)")

    return payload


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"令牌无效: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌类型无效",
        )
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌载荷缺少 sub",
        )
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user
