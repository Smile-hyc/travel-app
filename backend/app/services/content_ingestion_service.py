from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.review_store import ReviewStore
from app.schemas.content import OfficialSyncResponse
from app.schemas.explore import PlaceSummary
from app.services.place_detail_service import PlaceDetailService
from app.services.popular_poi_catalog import (
    PopularPoiCatalogService,
    PopularPoiSeed,
    seed_by_official_source,
)
from app.services.official_source_catalog import match_official_seed, official_seed


class OfficialContentProvider(Protocol):
    @property
    def supported_source_ids(self) -> set[str]: ...

    async def fetch_for_place(self, place: PlaceSummary, source_id: str) -> list[dict]: ...


class ContentIngestionService:
    def __init__(
        self,
        catalog: PopularPoiCatalogService,
        detail_service: PlaceDetailService,
        store: ReviewStore,
        *,
        review_client: Any,
        official_service: OfficialContentProvider | None = None,
    ) -> None:
        self._catalog = catalog
        self._detail_service = detail_service
        self._store = store
        self._review_client = review_client
        self._official_service = official_service
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def catalog(self) -> PopularPoiCatalogService:
        return self._catalog

    async def start_run(
        self,
        *,
        limit: int,
        force_refresh: bool,
        include_official: bool,
    ) -> dict:
        seeds = list(self._catalog.seeds[: max(1, min(limit, 30))])
        run_id = str(uuid.uuid4())
        run = self._store.start_ingestion_run(
            {
                "run_id": run_id,
                "provider": "authorized_ugc+official" if include_official else "authorized_ugc",
                "status": "running",
                "target_count": len(seeds),
            },
        )
        task = asyncio.create_task(
            self._execute_run(run_id, seeds, force_refresh, include_official),
            name=f"content-ingestion-{run_id}",
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        return run

    def get_run(self, run_id: str) -> dict | None:
        return self._store.get_ingestion_run(run_id)

    def list_runs(self, limit: int = 20) -> list[dict]:
        return self._store.list_ingestion_runs(limit=limit)

    def list_targets(self, *, due_only: bool = False, limit: int = 100) -> list[dict]:
        return self._store.list_collection_targets(due_only=due_only, limit=limit)

    def stats(self) -> dict[str, int]:
        return self._store.get_content_stats()

    def list_official_sources(self, *, city_name: str | None = None, limit: int = 200) -> list[dict]:
        return self._store.list_official_sources(city_name=city_name, limit=limit)

    async def bootstrap_city(self, *, city_name: str, limit: int) -> dict:
        places = await self._catalog.discover_city(city_name, limit=limit)
        items: list[dict[str, Any]] = []
        for index, place in enumerate(places):
            self._detail_service.ensure_place_profile(place)
            self._store.upsert_collection_target(
                {
                    "poi_id": place.sourcePoiId,
                    "priority": max(50, 100 - index * 2),
                    "tier": "HOT" if index < 10 else "WARM",
                    "refresh_interval_hours": 72 if index < 10 else 168,
                    "status": "queued",
                },
            )
            official = match_official_seed(place.name)
            if official is not None:
                self._store.upsert_official_source(
                    {
                        **official.__dict__,
                        "poi_id": place.sourcePoiId,
                        "verified_at": datetime.now(timezone.utc),
                    },
                )
            else:
                self._store.upsert_official_source(
                    {
                        "source_id": f"pending:{place.sourcePoiId}",
                        "poi_id": place.sourcePoiId,
                        "official_name": place.name,
                        "province_name": place.provinceName,
                        "city_name": place.cityName or city_name,
                        "adapter_kind": "PENDING_DISCOVERY",
                        "capabilities": [
                            "SCENIC_GRADE",
                            "OFFICIAL_NAME",
                            "TICKET",
                            "RESERVATION",
                            "CLOSURE",
                            "HOLIDAY_HOURS",
                            "CAPACITY",
                            "ANNOUNCEMENT",
                        ],
                        "discovery_status": "PENDING",
                    },
                )
            items.append(
                {
                    "sourcePoiId": place.sourcePoiId,
                    "name": place.name,
                    "rating": place.rating,
                    "districtName": place.districtName,
                    "crawlerKeyword": place.name,
                    "officialSourceId": official.source_id if official else None,
                },
            )
        return {"cityName": city_name, "count": len(items), "places": items}

    async def sync_official(self, source_id: str) -> OfficialSyncResponse:
        if self._official_service is None or source_id not in self._official_service.supported_source_ids:
            return OfficialSyncResponse(
                sourceId=source_id,
                sourcePoiId="",
                placeName="",
                savedCount=0,
                status="UNSUPPORTED",
                message="尚未配置该景区的官方数据适配器。",
            )
        seed = seed_by_official_source(source_id)
        directory_seed = official_seed(source_id)
        if seed is None and directory_seed is not None:
            seed = PopularPoiSeed(
                directory_seed.city_name,
                directory_seed.official_name,
                90,
                official_source_id=source_id,
            )
        if seed is None:
            return OfficialSyncResponse(
                sourceId=source_id,
                sourcePoiId="",
                placeName="",
                savedCount=0,
                status="UNSUPPORTED",
                message="官方来源尚未映射到高德 POI。",
            )
        resolved, _ = await self._catalog.resolve([seed])
        if not resolved:
            discovered = await self._catalog.discover_city(seed.city, limit=25)
            expected = "".join(character for character in seed.name if character.isalnum())
            best = next(
                (
                    place
                    for place in discovered
                    if expected in "".join(
                        character for character in place.name if character.isalnum()
                    )
                    or "".join(character for character in place.name if character.isalnum())
                    in expected
                ),
                None,
            )
            if best is not None:
                resolved = [(seed, best)]
        if not resolved:
            return OfficialSyncResponse(
                sourceId=source_id,
                sourcePoiId="",
                placeName=seed.name,
                savedCount=0,
                status="POI_NOT_FOUND",
            )
        _, place = resolved[0]
        self._detail_service.ensure_place_profile(place)
        if directory_seed is not None:
            self._store.upsert_official_source(
                {
                    **directory_seed.__dict__,
                    "poi_id": place.sourcePoiId,
                    "verified_at": datetime.now(timezone.utc),
                },
            )
        try:
            notices = await self._official_service.fetch_for_place(place, source_id)
        except Exception as exc:
            return OfficialSyncResponse(
                sourceId=source_id,
                sourcePoiId=place.sourcePoiId,
                placeName=place.name,
                savedCount=0,
                status="FETCH_FAILED",
                message=f"{type(exc).__name__}: {str(exc)[:140]}",
            )
        for notice in notices:
            self._store.upsert_official_notice(notice)
        directory = self._store.get_official_source(source_id)
        if directory is not None:
            capacities = [
                int(match.group(1))
                for notice in notices
                if notice.get("notice_type") == "CAPACITY"
                for match in [re.search(r"(\d{4,7})\s*人", str(notice.get("summary") or ""))]
                if match is not None
            ]
            directory["max_daily_capacity"] = max(capacities, default=directory.get("max_daily_capacity"))
            directory["verified_at"] = datetime.now(timezone.utc)
            self._store.upsert_official_source(directory)
        return OfficialSyncResponse(
            sourceId=source_id,
            sourcePoiId=place.sourcePoiId,
            placeName=place.name,
            savedCount=len(notices),
            status="COMPLETED",
        )

    async def _execute_run(
        self,
        run_id: str,
        seeds: list[PopularPoiSeed],
        force_refresh: bool,
        include_official: bool,
    ) -> None:
        fetched = accepted = saved = skipped = failed = 0
        errors: list[str] = []
        try:
            resolved, missing = await self._catalog.resolve(seeds)
            failed += len(missing)
            if missing:
                errors.append(f"AMAP_POI_NOT_FOUND:{len(missing)}")
            places = [place for _, place in resolved]
            for seed, place in resolved:
                self._store.upsert_collection_target(
                    {
                        "poi_id": place.sourcePoiId,
                        "priority": seed.priority,
                        "tier": seed.tier,
                        "refresh_interval_hours": 72 if seed.tier == "HOT" else 720,
                        "status": "queued",
                    },
                )
                if seed.official_source_id:
                    directory_seed = official_seed(seed.official_source_id)
                    if directory_seed is not None:
                        self._store.upsert_official_source(
                            {
                                **directory_seed.__dict__,
                                "poi_id": place.sourcePoiId,
                                "verified_at": datetime.now(timezone.utc),
                            },
                        )

            details_by_poi: dict[str, Any] = {}
            collection_metrics: dict[str, dict[str, int]] = {}
            if places and self._review_client.configured:
                batch = await self._detail_service.ensure_batch(places, force_refresh=force_refresh)
                for item in batch.items:
                    if item.detail is not None:
                        details_by_poi[item.sourcePoiId] = item.detail
                if batch.pendingCount:
                    async for event in self._detail_service.stream_batch(batch.batchId):
                        if event.detail is not None and event.sourcePoiId:
                            details_by_poi[event.sourcePoiId] = event.detail
                collection_metrics = self._detail_service.get_batch_metrics(batch.batchId)
                provider_error = getattr(self._review_client, "last_error", None)
                if provider_error is not None:
                    errors.append(provider_error.kind)
            elif places:
                errors.append("UGC_PROVIDER_DISABLED")

            now = datetime.now(timezone.utc)
            for seed, place in resolved:
                detail = details_by_poi.get(place.sourcePoiId)
                metrics = collection_metrics.get(place.sourcePoiId, {})
                fetched += metrics.get("fetched", 0)
                accepted += metrics.get("accepted", 0)
                saved += metrics.get("accepted", 0)
                target_error = None
                target_status = "completed"
                if self._review_client.configured and (
                    detail is None or detail.reviewStatus == "UNAVAILABLE"
                ):
                    target_status = "failed"
                    provider_error = getattr(self._review_client, "last_error", None)
                    target_error = (
                        provider_error.kind
                        if provider_error is not None
                        else (errors[-1] if errors else "UGC_UNAVAILABLE")
                    )
                    failed += 1
                elif not self._review_client.configured:
                    target_status = "official_only" if include_official else "provider_disabled"
                    skipped += 1

                if include_official and seed.official_source_id and self._official_service is not None:
                    try:
                        notices = await self._official_service.fetch_for_place(place, seed.official_source_id)
                        for notice in notices:
                            self._store.upsert_official_notice(notice)
                    except Exception:
                        failed += 1
                        errors.append(f"OFFICIAL_SYNC_FAILED:{seed.official_source_id}")

                interval = 72 if seed.tier == "HOT" else 720
                self._store.update_collection_target(
                    place.sourcePoiId,
                    last_collected_at=now,
                    next_collection_at=now + timedelta(hours=interval),
                    status=target_status,
                    last_error=target_error,
                )

            status = "completed" if not errors else "partial"
            self._store.finish_ingestion_run(
                run_id,
                status=status,
                target_count=len(seeds),
                fetched_count=fetched,
                accepted_count=accepted,
                saved_count=saved,
                skipped_count=skipped,
                failed_count=failed,
                error=";".join(dict.fromkeys(errors)) or None,
            )
        except Exception as exc:
            self._store.finish_ingestion_run(
                run_id,
                status="failed",
                target_count=len(seeds),
                fetched_count=fetched,
                accepted_count=accepted,
                saved_count=saved,
                skipped_count=skipped,
                failed_count=max(1, failed),
                error=f"{type(exc).__name__}: {str(exc)[:160]}",
            )


def map_ingestion_run(raw: dict) -> dict:
    return {
        "runId": raw["run_id"],
        "provider": raw["provider"],
        "status": raw["status"],
        "targetCount": raw.get("target_count", 0),
        "fetchedCount": raw.get("fetched_count", 0),
        "acceptedCount": raw.get("accepted_count", 0),
        "savedCount": raw.get("saved_count", 0),
        "skippedCount": raw.get("skipped_count", 0),
        "failedCount": raw.get("failed_count", 0),
        "startedAt": raw["started_at"],
        "finishedAt": raw.get("finished_at"),
        "error": raw.get("error"),
    }


def map_target(raw: dict) -> dict:
    return {
        "sourcePoiId": raw["poi_id"],
        "priority": raw["priority"],
        "tier": raw["tier"],
        "refreshIntervalHours": raw["refresh_interval_hours"],
        "lastCollectedAt": raw.get("last_collected_at"),
        "nextCollectionAt": raw.get("next_collection_at"),
        "status": raw["status"],
        "lastError": raw.get("last_error"),
        "active": bool(raw.get("active", 1)),
    }


def map_stats(raw: dict[str, int]) -> dict[str, int]:
    return {
        "placeCount": raw.get("place_count", 0),
        "activeEvidenceCount": raw.get("active_evidence_count", 0),
        "aggregateCount": raw.get("aggregate_count", 0),
        "activeTargetCount": raw.get("active_target_count", 0),
        "dueTargetCount": raw.get("due_target_count", 0),
        "ingestionRunCount": raw.get("ingestion_run_count", 0),
        "runningIngestionCount": raw.get("running_ingestion_count", 0),
        "officialSourceCount": raw.get("official_source_count", 0),
        "officialNoticeCount": raw.get("official_notice_count", 0),
        "rankedCityCount": raw.get("ranked_city_count", 0),
        "rankedPoiCount": raw.get("ranked_poi_count", 0),
        "cityCollectionRunCount": raw.get("city_collection_run_count", 0),
        "runningCityCollectionCount": raw.get("running_city_collection_count", 0),
    }
