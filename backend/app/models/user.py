from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone = Column(String(20), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    nickname = Column(String(60), default="")
    avatar_url = Column(String(500), default="")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True)
    expires_at = Column(String(30), nullable=False)
    revoked = Column(Integer, default=0)
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
