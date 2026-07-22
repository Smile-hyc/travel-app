from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


JsonObject = Mapping[str, Any]


def hash_author_identifier(identifier: str, *, salt: str) -> str:
    """Return a stable, one-way author identifier suitable for persistence."""
    if not salt:
        raise ValueError("salt must not be empty")
    return hashlib.sha256(f"{salt}:{identifier}".encode("utf-8")).hexdigest()


class ReviewStore:
    """SQLite persistence for normalized place facts and review evidence.

    This store deliberately has no columns for UGC raw text, images, videos, or
    an author's original account identifier. Callers must pass an anonymized
    ``author_hash`` when saving evidence.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.path,
            timeout=30,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._closed = False
        self._configure()
        self._create_schema()

    def _configure(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 30000")
            if self.path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")

    def _create_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS place_profiles (
            poi_id TEXT PRIMARY KEY,
            source TEXT NOT NULL DEFAULT 'AMAP',
            name TEXT NOT NULL,
            category TEXT,
            category_code TEXT,
            address TEXT,
            province_name TEXT,
            city_name TEXT,
            district_name TEXT,
            ad_code TEXT,
            latitude REAL,
            longitude REAL,
            opening_hours_today TEXT,
            opening_hours_week TEXT,
            rating TEXT,
            phone TEXT,
            route_json TEXT NOT NULL DEFAULT '{}',
            facts_updated_at TEXT NOT NULL,
            facts_expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_place_profiles_city
            ON place_profiles(city_name, district_name);
        CREATE INDEX IF NOT EXISTS idx_place_profiles_facts_expiry
            ON place_profiles(facts_expires_at);

        CREATE TABLE IF NOT EXISTS official_notices (
            notice_id TEXT PRIMARY KEY,
            poi_id TEXT NOT NULL,
            notice_type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            source_url TEXT NOT NULL,
            reservation_url TEXT,
            ticket_price TEXT,
            effective_from TEXT,
            effective_to TEXT,
            published_at TEXT,
            verified_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (poi_id) REFERENCES place_profiles(poi_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_official_notices_poi_active
            ON official_notices(poi_id, deleted, effective_to);

        CREATE TABLE IF NOT EXISTS official_source_directory (
            source_id TEXT PRIMARY KEY,
            poi_id TEXT,
            official_name TEXT NOT NULL,
            province_name TEXT,
            city_name TEXT NOT NULL,
            scenic_grade TEXT,
            website_url TEXT,
            wechat_name TEXT,
            mini_program_name TEXT,
            ticketing_url TEXT,
            adapter_kind TEXT NOT NULL DEFAULT 'DOCUMENT',
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            max_daily_capacity INTEGER,
            discovery_status TEXT NOT NULL DEFAULT 'VERIFIED',
            verified_at TEXT,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_official_directory_city
            ON official_source_directory(city_name, active, scenic_grade);
        CREATE INDEX IF NOT EXISTS idx_official_directory_poi
            ON official_source_directory(poi_id, active);

        CREATE TABLE IF NOT EXISTS ugc_evidence (
            evidence_id TEXT PRIMARY KEY,
            poi_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            source_note_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            published_at TEXT,
            author_hash TEXT,
            relevance_score REAL NOT NULL CHECK (relevance_score >= 0 AND relevance_score <= 1),
            tags_json TEXT NOT NULL DEFAULT '[]',
            short_summary TEXT NOT NULL,
            mention_count INTEGER NOT NULL DEFAULT 1 CHECK (mention_count >= 1),
            summary_version TEXT NOT NULL,
            data_updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (poi_id) REFERENCES place_profiles(poi_id) ON DELETE CASCADE,
            UNIQUE (provider, source_note_id, poi_id)
        );

        CREATE INDEX IF NOT EXISTS idx_ugc_evidence_poi_active
            ON ugc_evidence(poi_id, deleted, relevance_score DESC, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_ugc_evidence_refresh
            ON ugc_evidence(data_updated_at, deleted);

        CREATE TABLE IF NOT EXISTS review_aggregates (
            poi_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '{}',
            insights_json TEXT NOT NULL DEFAULT '{}',
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
            independent_source_count INTEGER NOT NULL DEFAULT 0
                CHECK (independent_source_count >= 0),
            confidence REAL NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
            summary_version TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            expires_at TEXT,
            data_updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready',
            deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (poi_id) REFERENCES place_profiles(poi_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_review_aggregates_expiry
            ON review_aggregates(deleted, expires_at);

        CREATE TABLE IF NOT EXISTS collection_targets (
            poi_id TEXT PRIMARY KEY,
            priority INTEGER NOT NULL DEFAULT 0,
            tier TEXT NOT NULL DEFAULT 'cold',
            refresh_interval_hours INTEGER NOT NULL DEFAULT 168
                CHECK (refresh_interval_hours > 0),
            last_collected_at TEXT,
            next_collection_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            last_error TEXT,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_collection_targets_due
            ON collection_targets(active, next_collection_at, priority DESC);
        CREATE INDEX IF NOT EXISTS idx_collection_targets_tier
            ON collection_targets(tier, active, priority DESC);

        CREATE TABLE IF NOT EXISTS ingestion_runs (
            run_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            target_count INTEGER NOT NULL DEFAULT 0 CHECK (target_count >= 0),
            fetched_count INTEGER NOT NULL DEFAULT 0 CHECK (fetched_count >= 0),
            accepted_count INTEGER NOT NULL DEFAULT 0 CHECK (accepted_count >= 0),
            saved_count INTEGER NOT NULL DEFAULT 0 CHECK (saved_count >= 0),
            skipped_count INTEGER NOT NULL DEFAULT 0 CHECK (skipped_count >= 0),
            failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ingestion_runs_recent
            ON ingestion_runs(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status
            ON ingestion_runs(status, started_at DESC);
        """
        with self._transaction():
            self._connection.executescript(schema)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._ensure_open()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def upsert_place_profile(self, place: JsonObject | Any) -> dict[str, Any]:
        item = _as_mapping(place)
        poi_id = _required(item, "poi_id", "sourcePoiId", "poiId")
        now = _utc_now()
        values = {
            "poi_id": poi_id,
            "source": _value(item, "source") or "AMAP",
            "name": _required(item, "name"),
            "category": _value(item, "category", "typeName"),
            "category_code": _value(item, "category_code", "categoryCode", "typeCode"),
            "address": _value(item, "address"),
            "province_name": _value(item, "province_name", "provinceName"),
            "city_name": _value(item, "city_name", "cityName"),
            "district_name": _value(item, "district_name", "districtName"),
            "ad_code": _value(item, "ad_code", "adCode"),
            "latitude": _value(item, "latitude"),
            "longitude": _value(item, "longitude"),
            "opening_hours_today": _value(item, "opening_hours_today", "openingHoursToday"),
            "opening_hours_week": _value(item, "opening_hours_week", "openingHoursWeek"),
            "rating": _value(item, "rating"),
            "phone": _value(item, "phone"),
            "route_json": _json_dump(_value(item, "route", "route_info", "routeInfo") or {}),
            "facts_updated_at": _iso(_value(item, "facts_updated_at", "factsUpdatedAt") or now),
            "facts_expires_at": _iso_or_none(
                _value(item, "facts_expires_at", "factsExpiresAt")
            ),
            "created_at": now,
            "updated_at": now,
        }
        sql = """
            INSERT INTO place_profiles (
                poi_id, source, name, category, category_code, address,
                province_name, city_name, district_name, ad_code, latitude,
                longitude, opening_hours_today, opening_hours_week, rating,
                phone, route_json, facts_updated_at, facts_expires_at,
                created_at, updated_at
            ) VALUES (
                :poi_id, :source, :name, :category, :category_code, :address,
                :province_name, :city_name, :district_name, :ad_code, :latitude,
                :longitude, :opening_hours_today, :opening_hours_week, :rating,
                :phone, :route_json, :facts_updated_at, :facts_expires_at,
                :created_at, :updated_at
            )
            ON CONFLICT(poi_id) DO UPDATE SET
                source = excluded.source,
                name = excluded.name,
                category = excluded.category,
                category_code = excluded.category_code,
                address = excluded.address,
                province_name = excluded.province_name,
                city_name = excluded.city_name,
                district_name = excluded.district_name,
                ad_code = excluded.ad_code,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                opening_hours_today = excluded.opening_hours_today,
                opening_hours_week = excluded.opening_hours_week,
                rating = excluded.rating,
                phone = excluded.phone,
                route_json = excluded.route_json,
                facts_updated_at = excluded.facts_updated_at,
                facts_expires_at = excluded.facts_expires_at,
                updated_at = excluded.updated_at
        """
        with self._transaction():
            self._connection.execute(sql, values)
        return self.get_place_profile(poi_id)  # type: ignore[return-value]

    def upsert_place_profiles(self, places: Iterable[JsonObject | Any]) -> list[dict[str, Any]]:
        return [self.upsert_place_profile(place) for place in places]

    def get_place_profile(self, poi_id: str) -> dict[str, Any] | None:
        row = self._fetchone("SELECT * FROM place_profiles WHERE poi_id = ?", (poi_id,))
        return _decode_row(row, json_columns=("route_json",))

    def get_place_profiles(self, poi_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        identifiers = list(dict.fromkeys(poi_ids))
        if not identifiers:
            return {}
        rows = self._fetchall(
            f"SELECT * FROM place_profiles WHERE poi_id IN ({_placeholders(identifiers)})",
            identifiers,
        )
        decoded = (_decode_row(row, json_columns=("route_json",)) for row in rows)
        return {item["poi_id"]: item for item in decoded if item is not None}

    def upsert_official_notice(self, notice: JsonObject | Any) -> dict[str, Any]:
        item = _as_mapping(notice)
        now = _utc_now()
        values = {
            "notice_id": _required(item, "notice_id", "noticeId"),
            "poi_id": _required(item, "poi_id", "poiId", "sourcePoiId"),
            "notice_type": _required(item, "notice_type", "noticeType", "type"),
            "title": _required(item, "title"),
            "summary": _value(item, "summary"),
            "source_url": _required(item, "source_url", "sourceUrl"),
            "reservation_url": _value(item, "reservation_url", "reservationUrl"),
            "ticket_price": _value(item, "ticket_price", "ticketPrice"),
            "effective_from": _iso_or_none(_value(item, "effective_from", "effectiveFrom")),
            "effective_to": _iso_or_none(_value(item, "effective_to", "effectiveTo")),
            "published_at": _iso_or_none(_value(item, "published_at", "publishedAt")),
            "verified_at": _iso(_value(item, "verified_at", "verifiedAt") or now),
            "deleted": int(bool(_value(item, "deleted") or False)),
            "created_at": now,
            "updated_at": now,
        }
        sql = """
            INSERT INTO official_notices (
                notice_id, poi_id, notice_type, title, summary, source_url,
                reservation_url, ticket_price, effective_from, effective_to,
                published_at, verified_at, deleted, created_at, updated_at
            ) VALUES (
                :notice_id, :poi_id, :notice_type, :title, :summary, :source_url,
                :reservation_url, :ticket_price, :effective_from, :effective_to,
                :published_at, :verified_at, :deleted, :created_at, :updated_at
            )
            ON CONFLICT(notice_id) DO UPDATE SET
                poi_id = excluded.poi_id,
                notice_type = excluded.notice_type,
                title = excluded.title,
                summary = excluded.summary,
                source_url = excluded.source_url,
                reservation_url = excluded.reservation_url,
                ticket_price = excluded.ticket_price,
                effective_from = excluded.effective_from,
                effective_to = excluded.effective_to,
                published_at = excluded.published_at,
                verified_at = excluded.verified_at,
                deleted = excluded.deleted,
                updated_at = excluded.updated_at
        """
        with self._transaction():
            self._connection.execute(sql, values)
        row = self._fetchone(
            "SELECT * FROM official_notices WHERE notice_id = ?", (values["notice_id"],)
        )
        return _decode_row(row)  # type: ignore[return-value]

    def list_official_notices(
        self,
        poi_id: str,
        *,
        active_only: bool = True,
        at: str | datetime | None = None,
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = [poi_id]
        where = "poi_id = ?"
        if active_only:
            moment = _iso(at or _utc_now())
            where += " AND deleted = 0 AND (effective_from IS NULL OR effective_from <= ?)"
            where += " AND (effective_to IS NULL OR effective_to >= ?)"
            parameters.extend((moment, moment))
        rows = self._fetchall(
            f"SELECT * FROM official_notices WHERE {where} "
            "ORDER BY COALESCE(effective_from, published_at, verified_at) DESC",
            parameters,
        )
        return [_decode_row(row) for row in rows]  # type: ignore[misc]

    def upsert_official_source(self, source: JsonObject | Any) -> dict[str, Any]:
        item = _as_mapping(source)
        now = _utc_now()
        capacity = _value(item, "max_daily_capacity", "maxDailyCapacity")
        values = {
            "source_id": _required(item, "source_id", "sourceId"),
            "poi_id": _value(item, "poi_id", "poiId", "sourcePoiId"),
            "official_name": _required(item, "official_name", "officialName", "name"),
            "province_name": _value(item, "province_name", "provinceName"),
            "city_name": _required(item, "city_name", "cityName"),
            "scenic_grade": _value(item, "scenic_grade", "scenicGrade"),
            "website_url": _value(item, "website_url", "websiteUrl"),
            "wechat_name": _value(item, "wechat_name", "wechatName"),
            "mini_program_name": _value(item, "mini_program_name", "miniProgramName"),
            "ticketing_url": _value(item, "ticketing_url", "ticketingUrl"),
            "adapter_kind": _value(item, "adapter_kind", "adapterKind") or "DOCUMENT",
            "capabilities_json": _json_dump(_value(item, "capabilities") or []),
            "max_daily_capacity": int(capacity) if capacity is not None else None,
            "discovery_status": (
                _value(item, "discovery_status", "discoveryStatus") or "VERIFIED"
            ),
            "verified_at": _iso_or_none(_value(item, "verified_at", "verifiedAt")),
            "active": int(bool(_value(item, "active") if "active" in item else True)),
            "created_at": now,
            "updated_at": now,
        }
        if values["max_daily_capacity"] is not None and values["max_daily_capacity"] < 0:
            raise ValueError("max_daily_capacity must be non-negative")
        sql = """
            INSERT INTO official_source_directory (
                source_id, poi_id, official_name, province_name, city_name,
                scenic_grade, website_url, wechat_name, mini_program_name,
                ticketing_url, adapter_kind, capabilities_json,
                max_daily_capacity, discovery_status, verified_at, active,
                created_at, updated_at
            ) VALUES (
                :source_id, :poi_id, :official_name, :province_name, :city_name,
                :scenic_grade, :website_url, :wechat_name, :mini_program_name,
                :ticketing_url, :adapter_kind, :capabilities_json,
                :max_daily_capacity, :discovery_status, :verified_at, :active,
                :created_at, :updated_at
            )
            ON CONFLICT(source_id) DO UPDATE SET
                poi_id = COALESCE(excluded.poi_id, official_source_directory.poi_id),
                official_name = excluded.official_name,
                province_name = excluded.province_name,
                city_name = excluded.city_name,
                scenic_grade = excluded.scenic_grade,
                website_url = excluded.website_url,
                wechat_name = excluded.wechat_name,
                mini_program_name = excluded.mini_program_name,
                ticketing_url = excluded.ticketing_url,
                adapter_kind = excluded.adapter_kind,
                capabilities_json = excluded.capabilities_json,
                max_daily_capacity = COALESCE(
                    excluded.max_daily_capacity,
                    official_source_directory.max_daily_capacity
                ),
                discovery_status = excluded.discovery_status,
                verified_at = excluded.verified_at,
                active = excluded.active,
                updated_at = excluded.updated_at
        """
        with self._transaction():
            self._connection.execute(sql, values)
        return self.get_official_source(values["source_id"])  # type: ignore[return-value]

    def get_official_source(self, source_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM official_source_directory WHERE source_id = ?",
            (source_id,),
        )
        return _decode_row(row, json_columns=("capabilities_json",))

    def get_official_source_by_poi(self, poi_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM official_source_directory "
            "WHERE poi_id = ? AND active = 1 "
            "ORDER BY CASE discovery_status WHEN 'VERIFIED' THEN 0 ELSE 1 END LIMIT 1",
            (poi_id,),
        )
        return _decode_row(row, json_columns=("capabilities_json",))

    def list_official_sources(
        self,
        *,
        city_name: str | None = None,
        active_only: bool = True,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if city_name:
            conditions.append("city_name = ?")
            parameters.append(city_name)
        if active_only:
            conditions.append("active = 1")
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(max(1, min(limit, 1000)))
        rows = self._fetchall(
            "SELECT * FROM official_source_directory"
            f"{where} ORDER BY city_name, scenic_grade DESC, official_name LIMIT ?",
            parameters,
        )
        return [
            _decode_row(row, json_columns=("capabilities_json",)) for row in rows
        ]  # type: ignore[misc]

    def save_evidence(self, evidence: JsonObject | Any) -> dict[str, Any]:
        item = _as_mapping(evidence)
        now = _utc_now()
        values = {
            "evidence_id": _required(item, "evidence_id", "evidenceId", "id"),
            "poi_id": _required(item, "poi_id", "poiId", "sourcePoiId"),
            "provider": _value(item, "provider", "platform") or "xiaohongshu",
            "source_note_id": _required(item, "source_note_id", "sourceNoteId", "noteId"),
            "source_url": _required(
                item, "source_url", "sourceUrl", "original_url", "originalUrl", "url"
            ),
            "published_at": _iso_or_none(_value(item, "published_at", "publishedAt")),
            "author_hash": _value(item, "author_hash", "authorHash"),
            "relevance_score": float(
                _required(item, "relevance_score", "relevanceScore")
            ),
            "tags_json": _json_dump(_value(item, "tags") or []),
            "short_summary": _required(item, "short_summary", "shortSummary", "summary"),
            "mention_count": int(_value(item, "mention_count", "mentionCount") or 1),
            "summary_version": _required(item, "summary_version", "summaryVersion"),
            "data_updated_at": _iso(
                _value(
                    item,
                    "data_updated_at",
                    "dataUpdatedAt",
                    "collected_at",
                    "collectedAt",
                    "updated_at",
                    "updatedAt",
                )
                or now
            ),
            "deleted": int(bool(_value(item, "deleted") or False)),
            "created_at": now,
            "updated_at": now,
        }
        sql = """
            INSERT INTO ugc_evidence (
                evidence_id, poi_id, provider, source_note_id, source_url,
                published_at, author_hash, relevance_score, tags_json,
                short_summary, mention_count, summary_version, data_updated_at,
                deleted, created_at, updated_at
            ) VALUES (
                :evidence_id, :poi_id, :provider, :source_note_id, :source_url,
                :published_at, :author_hash, :relevance_score, :tags_json,
                :short_summary, :mention_count, :summary_version, :data_updated_at,
                :deleted, :created_at, :updated_at
            )
            ON CONFLICT(evidence_id) DO UPDATE SET
                poi_id = excluded.poi_id,
                provider = excluded.provider,
                source_note_id = excluded.source_note_id,
                source_url = excluded.source_url,
                published_at = excluded.published_at,
                author_hash = excluded.author_hash,
                relevance_score = excluded.relevance_score,
                tags_json = excluded.tags_json,
                short_summary = excluded.short_summary,
                mention_count = excluded.mention_count,
                summary_version = excluded.summary_version,
                data_updated_at = excluded.data_updated_at,
                deleted = excluded.deleted,
                updated_at = excluded.updated_at
        """
        with self._transaction():
            self._connection.execute(sql, values)
        row = self._fetchone(
            "SELECT * FROM ugc_evidence WHERE evidence_id = ?", (values["evidence_id"],)
        )
        return _decode_row(row, json_columns=("tags_json",))  # type: ignore[return-value]

    def save_evidence_batch(self, evidence: Iterable[JsonObject | Any]) -> list[dict[str, Any]]:
        return [self.save_evidence(item) for item in evidence]

    def list_active_evidence(
        self,
        poi_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT * FROM ugc_evidence WHERE poi_id = ? AND deleted = 0 "
            "ORDER BY relevance_score DESC, published_at DESC, evidence_id"
        )
        parameters: list[Any] = [poi_id]
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be non-negative")
            sql += " LIMIT ?"
            parameters.append(limit)
        rows = self._fetchall(sql, parameters)
        return [
            _decode_row(row, json_columns=("tags_json",)) for row in rows
        ]  # type: ignore[misc]

    def mark_evidence_deleted(self, evidence_id: str, *, deleted: bool = True) -> bool:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE ugc_evidence SET deleted = ?, updated_at = ? WHERE evidence_id = ?",
                (int(deleted), _utc_now(), evidence_id),
            )
        return cursor.rowcount > 0

    def save_aggregate(self, aggregate: JsonObject | Any) -> dict[str, Any]:
        item = _as_mapping(aggregate)
        now = _utc_now()
        evidence_ids = _value(item, "evidence_ids", "evidenceIds") or []
        values = {
            "poi_id": _required(item, "poi_id", "poiId", "sourcePoiId"),
            "summary": _value(item, "summary") or "",
            "tags_json": _json_dump(_value(item, "tags") or {}),
            "insights_json": _json_dump(
                _value(item, "insights", "insights_json", "insightsJson") or {}
            ),
            "evidence_ids_json": _json_dump(evidence_ids),
            "evidence_count": int(
                _value(item, "evidence_count", "evidenceCount")
                if _value(item, "evidence_count", "evidenceCount") is not None
                else len(evidence_ids)
            ),
            "independent_source_count": int(
                _value(item, "independent_source_count", "independentSourceCount") or 0
            ),
            "confidence": float(_value(item, "confidence") or 0),
            "summary_version": _required(item, "summary_version", "summaryVersion"),
            "generated_at": _iso(_value(item, "generated_at", "generatedAt") or now),
            "expires_at": _iso_or_none(_value(item, "expires_at", "expiresAt")),
            "data_updated_at": _iso(
                _value(item, "data_updated_at", "dataUpdatedAt", "updated_at", "updatedAt")
                or now
            ),
            "status": _value(item, "status") or "ready",
            "deleted": int(bool(_value(item, "deleted") or False)),
            "created_at": now,
            "updated_at": now,
        }
        sql = """
            INSERT INTO review_aggregates (
                poi_id, summary, tags_json, insights_json, evidence_ids_json, evidence_count,
                independent_source_count, confidence, summary_version,
                generated_at, expires_at, data_updated_at, status, deleted, created_at,
                updated_at
            ) VALUES (
                :poi_id, :summary, :tags_json, :insights_json, :evidence_ids_json, :evidence_count,
                :independent_source_count, :confidence, :summary_version,
                :generated_at, :expires_at, :data_updated_at, :status, :deleted, :created_at,
                :updated_at
            )
            ON CONFLICT(poi_id) DO UPDATE SET
                summary = excluded.summary,
                tags_json = excluded.tags_json,
                insights_json = excluded.insights_json,
                evidence_ids_json = excluded.evidence_ids_json,
                evidence_count = excluded.evidence_count,
                independent_source_count = excluded.independent_source_count,
                confidence = excluded.confidence,
                summary_version = excluded.summary_version,
                generated_at = excluded.generated_at,
                expires_at = excluded.expires_at,
                data_updated_at = excluded.data_updated_at,
                status = excluded.status,
                deleted = excluded.deleted,
                updated_at = excluded.updated_at
        """
        with self._transaction():
            self._connection.execute(sql, values)
        return self.get_aggregate(values["poi_id"], include_deleted=True)  # type: ignore[return-value]

    def get_aggregate(
        self,
        poi_id: str,
        *,
        include_deleted: bool = False,
    ) -> dict[str, Any] | None:
        sql = "SELECT * FROM review_aggregates WHERE poi_id = ?"
        if not include_deleted:
            sql += " AND deleted = 0"
        row = self._fetchone(sql, (poi_id,))
        return _decode_row(
            row,
            json_columns=("tags_json", "insights_json", "evidence_ids_json"),
        )

    def get_aggregates(
        self,
        poi_ids: Iterable[str],
        *,
        include_deleted: bool = False,
    ) -> dict[str, dict[str, Any]]:
        identifiers = list(dict.fromkeys(poi_ids))
        if not identifiers:
            return {}
        sql = f"SELECT * FROM review_aggregates WHERE poi_id IN ({_placeholders(identifiers)})"
        if not include_deleted:
            sql += " AND deleted = 0"
        rows = self._fetchall(sql, identifiers)
        decoded = (
            _decode_row(
                row,
                json_columns=("tags_json", "insights_json", "evidence_ids_json"),
            )
            for row in rows
        )
        return {item["poi_id"]: item for item in decoded if item is not None}

    def upsert_collection_target(self, target: JsonObject | Any) -> dict[str, Any]:
        """Create or update a POI collection schedule.

        Scheduling progress is retained when a caller merely re-imports a POI's
        priority/tier configuration.  Progress fields are overwritten only when
        they are explicitly present in ``target``.
        """
        item = _as_mapping(target)
        now = _utc_now()
        next_value, has_next = _present_value(
            item, "next_collection_at", "nextCollectionAt"
        )
        last_value, has_last = _present_value(
            item, "last_collected_at", "lastCollectedAt"
        )
        status_value, has_status = _present_value(item, "status")
        error_value, has_error = _present_value(item, "last_error", "lastError", "error")
        active_value, has_active = _present_value(item, "active")
        priority_value, has_priority = _present_value(item, "priority")
        tier_value, has_tier = _present_value(item, "tier")
        interval, has_interval = _present_value(
            item,
            "refresh_interval_hours",
            "refreshIntervalHours",
            "refresh_interval",
            "refreshInterval",
        )
        values = {
            "poi_id": _required(item, "poi_id", "poiId", "sourcePoiId"),
            "priority": int(priority_value or 0),
            "tier": str(tier_value or "cold"),
            "refresh_interval_hours": int(interval if interval is not None else 168),
            "last_collected_at": _iso_or_none(last_value),
            "next_collection_at": _iso_or_none(next_value) if has_next else now,
            "status": str(status_value or "pending"),
            "last_error": error_value,
            "active": int(bool(active_value)) if has_active else 1,
            "has_last": int(has_last),
            "has_next": int(has_next),
            "has_status": int(has_status),
            "has_error": int(has_error),
            "has_priority": int(has_priority),
            "has_tier": int(has_tier),
            "has_interval": int(has_interval),
            "has_active": int(has_active),
            "created_at": now,
            "updated_at": now,
        }
        if values["refresh_interval_hours"] <= 0:
            raise ValueError("refresh_interval_hours must be positive")
        sql = """
            INSERT INTO collection_targets (
                poi_id, priority, tier, refresh_interval_hours,
                last_collected_at, next_collection_at, status, last_error,
                active, created_at, updated_at
            ) VALUES (
                :poi_id, :priority, :tier, :refresh_interval_hours,
                :last_collected_at, :next_collection_at, :status, :last_error,
                :active, :created_at, :updated_at
            )
            ON CONFLICT(poi_id) DO UPDATE SET
                priority = CASE WHEN :has_priority = 1
                    THEN excluded.priority ELSE collection_targets.priority END,
                tier = CASE WHEN :has_tier = 1
                    THEN excluded.tier ELSE collection_targets.tier END,
                refresh_interval_hours = CASE WHEN :has_interval = 1
                    THEN excluded.refresh_interval_hours
                    ELSE collection_targets.refresh_interval_hours END,
                last_collected_at = CASE WHEN :has_last = 1
                    THEN excluded.last_collected_at ELSE collection_targets.last_collected_at END,
                next_collection_at = CASE WHEN :has_next = 1
                    THEN excluded.next_collection_at ELSE collection_targets.next_collection_at END,
                status = CASE WHEN :has_status = 1
                    THEN excluded.status ELSE collection_targets.status END,
                last_error = CASE WHEN :has_error = 1
                    THEN excluded.last_error ELSE collection_targets.last_error END,
                active = CASE WHEN :has_active = 1
                    THEN excluded.active ELSE collection_targets.active END,
                updated_at = excluded.updated_at
        """
        with self._transaction():
            self._connection.execute(sql, values)
        return self.get_collection_target(values["poi_id"])  # type: ignore[return-value]

    def get_collection_target(self, poi_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM collection_targets WHERE poi_id = ?", (poi_id,)
        )
        return _decode_row(row)

    def list_collection_targets(
        self,
        *,
        active_only: bool = True,
        due_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        conditions: list[str] = []
        parameters: list[Any] = []
        if active_only:
            conditions.append("active = 1")
        if due_only:
            conditions.append("(next_collection_at IS NULL OR next_collection_at <= ?)")
            parameters.append(_utc_now())
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit)
        rows = self._fetchall(
            "SELECT * FROM collection_targets"
            f"{where} ORDER BY priority DESC, "
            "CASE WHEN next_collection_at IS NULL THEN 0 ELSE 1 END, "
            "next_collection_at, poi_id LIMIT ?",
            parameters,
        )
        return [_decode_row(row) for row in rows]  # type: ignore[misc]

    def update_collection_target(self, poi_id: str, **fields: Any) -> dict[str, Any] | None:
        aliases = {
            "priority": "priority",
            "tier": "tier",
            "refresh_interval_hours": "refresh_interval_hours",
            "refreshIntervalHours": "refresh_interval_hours",
            "refresh_interval": "refresh_interval_hours",
            "last_collected_at": "last_collected_at",
            "lastCollectedAt": "last_collected_at",
            "next_collection_at": "next_collection_at",
            "nextCollectionAt": "next_collection_at",
            "status": "status",
            "last_error": "last_error",
            "lastError": "last_error",
            "error": "last_error",
            "active": "active",
        }
        if not fields:
            return self.get_collection_target(poi_id)
        unknown = sorted(set(fields) - set(aliases))
        if unknown:
            raise ValueError(f"unsupported collection target fields: {', '.join(unknown)}")
        normalized: dict[str, Any] = {}
        for name, value in fields.items():
            column = aliases[name]
            if column in {"last_collected_at", "next_collection_at"}:
                value = _iso_or_none(value)
            elif column in {"priority", "refresh_interval_hours"}:
                value = int(value)
            elif column == "active":
                value = int(bool(value))
            normalized[column] = value
        if normalized.get("refresh_interval_hours", 1) <= 0:
            raise ValueError("refresh_interval_hours must be positive")
        normalized["updated_at"] = _utc_now()
        assignments = ", ".join(f"{column} = ?" for column in normalized)
        parameters = [*normalized.values(), poi_id]
        with self._transaction():
            cursor = self._connection.execute(
                f"UPDATE collection_targets SET {assignments} WHERE poi_id = ?",
                parameters,
            )
        return self.get_collection_target(poi_id) if cursor.rowcount else None

    def start_ingestion_run(self, run: JsonObject | Any) -> dict[str, Any]:
        item = _as_mapping(run)
        now = _utc_now()
        values = {
            "run_id": _required(item, "run_id", "runId", "id"),
            "provider": _required(item, "provider"),
            "status": _value(item, "status") or "running",
            "target_count": _non_negative_count(item, "target_count", "targetCount"),
            "fetched_count": _non_negative_count(item, "fetched_count", "fetchedCount"),
            "accepted_count": _non_negative_count(item, "accepted_count", "acceptedCount"),
            "saved_count": _non_negative_count(item, "saved_count", "savedCount"),
            "skipped_count": _non_negative_count(item, "skipped_count", "skippedCount"),
            "failed_count": _non_negative_count(item, "failed_count", "failedCount"),
            "started_at": _iso(_value(item, "started_at", "startedAt") or now),
            "finished_at": _iso_or_none(_value(item, "finished_at", "finishedAt")),
            "error": _value(item, "error"),
            "created_at": now,
            "updated_at": now,
        }
        sql = """
            INSERT INTO ingestion_runs (
                run_id, provider, status, target_count, fetched_count,
                accepted_count, saved_count, skipped_count, failed_count,
                started_at, finished_at, error, created_at, updated_at
            ) VALUES (
                :run_id, :provider, :status, :target_count, :fetched_count,
                :accepted_count, :saved_count, :skipped_count, :failed_count,
                :started_at, :finished_at, :error, :created_at, :updated_at
            )
        """
        with self._transaction():
            self._connection.execute(sql, values)
        return self.get_ingestion_run(values["run_id"])  # type: ignore[return-value]

    def finish_ingestion_run(self, run_id: str, **fields: Any) -> dict[str, Any] | None:
        aliases = {
            "provider": "provider",
            "status": "status",
            "target_count": "target_count",
            "targetCount": "target_count",
            "fetched_count": "fetched_count",
            "fetchedCount": "fetched_count",
            "accepted_count": "accepted_count",
            "acceptedCount": "accepted_count",
            "saved_count": "saved_count",
            "savedCount": "saved_count",
            "skipped_count": "skipped_count",
            "skippedCount": "skipped_count",
            "failed_count": "failed_count",
            "failedCount": "failed_count",
            "finished_at": "finished_at",
            "finishedAt": "finished_at",
            "error": "error",
        }
        unknown = sorted(set(fields) - set(aliases))
        if unknown:
            raise ValueError(f"unsupported ingestion run fields: {', '.join(unknown)}")
        normalized: dict[str, Any] = {
            "status": fields.get("status", "completed"),
            "finished_at": _iso_or_none(
                fields.get("finished_at", fields.get("finishedAt", _utc_now()))
            ),
        }
        for name, value in fields.items():
            column = aliases[name]
            if column.endswith("_count"):
                value = int(value)
                if value < 0:
                    raise ValueError(f"{column} must be non-negative")
            elif column == "finished_at":
                value = _iso_or_none(value)
            normalized[column] = value
        normalized["updated_at"] = _utc_now()
        assignments = ", ".join(f"{column} = ?" for column in normalized)
        with self._transaction():
            cursor = self._connection.execute(
                f"UPDATE ingestion_runs SET {assignments} WHERE run_id = ?",
                (*normalized.values(), run_id),
            )
        return self.get_ingestion_run(run_id) if cursor.rowcount else None

    def get_ingestion_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._fetchone("SELECT * FROM ingestion_runs WHERE run_id = ?", (run_id,))
        return _decode_row(row)

    def list_ingestion_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        rows = self._fetchall(
            "SELECT * FROM ingestion_runs ORDER BY started_at DESC, run_id DESC LIMIT ?",
            (limit,),
        )
        return [_decode_row(row) for row in rows]  # type: ignore[misc]

    def get_content_stats(self) -> dict[str, int]:
        """Return inexpensive operational counters for collection monitoring."""
        queries = {
            "place_count": "SELECT COUNT(*) FROM place_profiles",
            "active_evidence_count": "SELECT COUNT(*) FROM ugc_evidence WHERE deleted = 0",
            "aggregate_count": "SELECT COUNT(*) FROM review_aggregates WHERE deleted = 0",
            "active_target_count": "SELECT COUNT(*) FROM collection_targets WHERE active = 1",
            "due_target_count": (
                "SELECT COUNT(*) FROM collection_targets WHERE active = 1 "
                "AND (next_collection_at IS NULL OR next_collection_at <= ?)"
            ),
            "ingestion_run_count": "SELECT COUNT(*) FROM ingestion_runs",
            "running_ingestion_count": (
                "SELECT COUNT(*) FROM ingestion_runs WHERE status = 'running'"
            ),
            "official_source_count": (
                "SELECT COUNT(*) FROM official_source_directory WHERE active = 1"
            ),
            "official_notice_count": (
                "SELECT COUNT(*) FROM official_notices WHERE deleted = 0"
            ),
        }
        now = _utc_now()
        result: dict[str, int] = {}
        with self._lock:
            self._ensure_open()
            for name, sql in queries.items():
                parameters = (now,) if name == "due_target_count" else ()
                row = self._connection.execute(sql, parameters).fetchone()
                result[name] = int(row[0])
        return result

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def __enter__(self) -> ReviewStore:
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _fetchone(self, sql: str, parameters: Iterable[Any]) -> sqlite3.Row | None:
        self._ensure_open()
        with self._lock:
            return self._connection.execute(sql, tuple(parameters)).fetchone()

    def _fetchall(self, sql: str, parameters: Iterable[Any]) -> list[sqlite3.Row]:
        self._ensure_open()
        with self._lock:
            return self._connection.execute(sql, tuple(parameters)).fetchall()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("ReviewStore is closed")


def _as_mapping(value: JsonObject | Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    raise TypeError("value must be a mapping or a Pydantic model")


def _required(item: Mapping[str, Any], *names: str) -> Any:
    value = _value(item, *names)
    if value is None or value == "":
        raise ValueError(f"missing required field: {names[0]}")
    return value


def _value(item: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in item:
            return item[name]
    return None


def _present_value(item: Mapping[str, Any], *names: str) -> tuple[Any, bool]:
    for name in names:
        if name in item:
            return item[name], True
    return None, False


def _non_negative_count(item: Mapping[str, Any], *names: str) -> int:
    value = _value(item, *names)
    count = int(value) if value is not None else 0
    if count < 0:
        raise ValueError(f"{names[0]} must be non-negative")
    return count


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _iso(value: str | datetime) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _iso_or_none(value: str | datetime | None) -> str | None:
    return None if value is None or value == "" else _iso(value)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode_row(
    row: sqlite3.Row | None,
    *,
    json_columns: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for column in json_columns:
        decoded = json.loads(result[column])
        result[column] = decoded
        result[column.removesuffix("_json")] = decoded
    for column in ("deleted", "active"):
        if column in result:
            result[column] = bool(result[column])
    return result


def _placeholders(values: Iterable[Any]) -> str:
    return ",".join("?" for _ in values)
