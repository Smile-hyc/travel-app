from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Float, Integer, String, Text, ForeignKey
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


class UserPlan(Base):
    __tablename__ = "user_plans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(100), nullable=False, default="")
    destination = Column(String(100), nullable=False, default="")
    date_range = Column(String(60), default="")
    day_count = Column(Integer, default=1)
    preferences = Column(Text, default="[]")
    plan_data = Column(Text, default="{}")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())


class UserJournal(Base):
    __tablename__ = "user_journals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="")
    location = Column(String(200), default="")
    date = Column(String(30), default="")
    body = Column(Text, default="")
    photos = Column(Text, default="[]")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())


class UserFootprint(Base):
    __tablename__ = "user_footprints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(60), nullable=False)
    province_name = Column(String(60), default="")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    visit_count = Column(Integer, default=1)
    first_visited_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    last_visited_at = Column(String(30), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
