from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.review_store import ReviewStore
from app.schemas.explore import PlaceSummary
from app.services.mediacrawler_import_service import MediaCrawlerImportService
from app.services.mediacrawler_runner import MediaCrawlerRunner, MediaCrawlerRunResult
from app.services.place_detail_service import PlaceDetailService
from app.services.popular_poi_catalog import PopularPoiCatalogService


DEFAULT_TOP_POIS = 12
DEFAULT_CANDIDATES_PER_POI = 30
DEFAULT_RETAINED_PER_POI = 20
DEFAULT_DISPLAYED_PER_POI = 8


class CityContentPipelineService:
    def __init__(
        self,
        catalog: PopularPoiCatalogService,
        detail_service: PlaceDetailService,
        importer: MediaCrawlerImportService,
        runner: MediaCrawlerRunner,
        store: ReviewStore,
    ) -> None:
        self._catalog = catalog
        self._detail_service = detail_service
        self._importer = importer
        self._runner = runner
        self._store = store
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def list_cities(self):
        return await self._catalog.list_cities()

    async def plan_city(self, city_name: str, *, top: int = DEFAULT_TOP_POIS) -> dict[str, Any]:
        top = max(1, min(top, 25))
        city = await self._catalog.resolve_city(city_name)
        if city is None:
            raise ValueError(f"未找到城市：{city_name}")
        places = await self._catalog.discover_city(city.name, limit=top)
        if not places:
            raise ValueError(f"{city.name}没有可用的景点候选")
        for place in places:
            self._detail_service.ensure_place_profile(place)
        ranking_version = _ranking_version(city.adCode, places)
        ranking = self._store.save_city_ranking(
            city_adcode=city.adCode,
            city_name=city.name,
            province_name=city.provinceName,
            ranking_version=ranking_version,
            places=[
                {
                    "sourcePoiId": place.sourcePoiId,
                    "crawlerKeyword": _crawler_keyword(city.name, place.name),
                }
                for place in places
            ],
        )
        return {
            "cityAdcode": city.adCode,
            "cityName": city.name,
            "provinceName": city.provinceName,
            "rankingVersion": ranking_version,
            "count": len(ranking),
            "places": [_map_ranking(item) for item in ranking],
        }

    async def start_city(
        self,
        city_name: str,
        *,
        top: int = DEFAULT_TOP_POIS,
        candidate_limit: int = DEFAULT_CANDIDATES_PER_POI,
        headless: bool = False,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        plan = await self.plan_city(city_name, top=top)
        run_id = str(uuid.uuid4())
        items = []
        now = datetime.now(timezone.utc).isoformat()
        for item in plan["places"]:
            poi_id = item["sourcePoiId"]
            target = self._store.get_collection_target(poi_id)
            has_evidence = bool(self._store.list_active_evidence(poi_id, limit=1))
            due = (
                force_refresh
                or not has_evidence
                or target is None
                or target.get("next_collection_at") is None
                or str(target["next_collection_at"]) <= now
            )
            if due:
                items.append(
                    {
                        "poi_id": poi_id,
                        "rank": item["rank"],
                        "query_keyword": item["crawlerKeyword"],
                    },
                )
        run = self._store.start_city_collection_run(
            {
                "run_id": run_id,
                "city_adcode": plan["cityAdcode"],
                "city_name": plan["cityName"],
                "ranking_version": plan["rankingVersion"],
                "candidate_limit": max(1, min(candidate_limit, 60)),
                "retain_limit": DEFAULT_RETAINED_PER_POI,
                "display_limit": DEFAULT_DISPLAYED_PER_POI,
            },
            items,
        )
        if not items:
            return self._store.update_city_collection_run(
                run_id,
                status="ready",
                finished_at=datetime.now(timezone.utc),
            )  # type: ignore[return-value]
        task = asyncio.create_task(
            self._execute(run_id, headless=headless),
            name=f"city-content-{run_id}",
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        return run

    async def run_city_and_wait(self, city_name: str, **kwargs: Any) -> dict[str, Any]:
        started = await self.start_city(city_name, **kwargs)
        task = self._tasks.get(started["run_id"])
        if task is not None:
            await task
        return self.get_run(started["run_id"])  # type: ignore[return-value]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._store.get_city_collection_run(run_id)

    def list_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self._store.list_city_collection_runs(limit=limit)

    def recover_partial_run(self, run_id: str) -> dict[str, Any]:
        run = self._store.get_city_collection_run(run_id)
        if run is None:
            raise ValueError(f"未找到采集任务：{run_id}")
        run_dir = (self._runner.run_root / run_id).resolve()
        if not run_dir.is_relative_to(self._runner.run_root):
            raise ValueError("非法采集任务目录")
        exports = sorted(
            (run_dir / "xhs" / "jsonl").glob("search_contents_*.jsonl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not exports or exports[0].stat().st_size == 0:
            raise ValueError("采集任务没有可恢复的 JSONL 数据")
        self._import_result(
            run_id,
            run,
            MediaCrawlerRunResult(exports[0], run_dir / "crawler.log", 1),
        )
        return self.get_run(run_id)  # type: ignore[return-value]

    async def _execute(self, run_id: str, *, headless: bool) -> None:
        run = self._store.get_city_collection_run(run_id)
        if run is None:
            return
        try:
            items = run["items"]
            for item in items:
                self._store.update_city_collection_item(
                    run_id, item["poi_id"], status="crawling", error=None,
                )
            self._store.update_city_collection_run(run_id, status="crawling", error=None)
            result = await self._runner.run(
                run_id=run_id,
                city_name=run["city_name"],
                items=items,
                candidate_limit=run["candidate_limit"],
                headless=headless,
            )
            self._import_result(run_id, run, result)
        except Exception as exc:
            message = str(exc)
            if message.startswith("LOGIN_REQUIRED:"):
                failure_status, error_kind = "login_required", "LOGIN_REQUIRED"
            elif message.startswith("CAPTCHA_REQUIRED:"):
                failure_status, error_kind = "captcha_required", "CAPTCHA_REQUIRED"
            elif message.startswith("NETWORK_UNAVAILABLE:"):
                failure_status, error_kind = "network_unavailable", "NETWORK_UNAVAILABLE"
            else:
                failure_status, error_kind = "failed", type(exc).__name__
            self._store.update_city_collection_run(
                run_id,
                status=failure_status,
                failed_count=max(1, int(run.get("target_count") or 1)),
                error=f"{type(exc).__name__}: {str(exc)[:600]}",
                finished_at=datetime.now(timezone.utc),
            )
            for item in self._store.list_city_collection_items(run_id):
                if item["status"] in {"queued", "crawling"}:
                    self._store.update_city_collection_item(
                        run_id,
                        item["poi_id"],
                        status=failure_status,
                        error=error_kind,
                    )

    def _import_result(
        self,
        run_id: str,
        run: dict[str, Any],
        result: MediaCrawlerRunResult,
    ) -> None:
        items = run["items"]
        self._store.update_city_collection_run(
            run_id,
            status="cleaning",
            output_path=str(result.export_path),
            error=None,
        )
        places_by_keyword = {
            item["query_keyword"]: _profile_to_place(
                self._store.get_place_profile(item["poi_id"]),
            )
            for item in items
        }
        imported = self._importer.import_manifest_export(
            export_path=result.export_path,
            places_by_keyword=places_by_keyword,
            candidate_limit=run["candidate_limit"],
        )
        by_poi = {item["sourcePoiId"]: item for item in imported["imported"]}
        failed = 0
        crawler_interrupted = result.return_code != 0
        interruption_error = (
            "CAPTCHA_REQUIRED" if result.return_code == 461 else "CRAWLER_INTERRUPTED"
        )
        now = datetime.now(timezone.utc)
        for item in items:
            metrics = by_poi.get(item["poi_id"])
            if metrics is None:
                status = "partial" if crawler_interrupted else "insufficient"
                fetched = accepted = 0
                error = interruption_error if crawler_interrupted else None
                if crawler_interrupted:
                    failed += 1
            else:
                fetched = int(metrics["fetchedCount"])
                accepted = int(metrics["acceptedCount"])
                status = "ready" if accepted else "insufficient"
                error = None
            self._store.update_city_collection_item(
                run_id,
                item["poi_id"],
                status=status,
                fetched_count=fetched,
                accepted_count=accepted,
                error=error,
            )
            if metrics is not None:
                self._store.upsert_collection_target(
                    {
                        "poi_id": item["poi_id"],
                        "priority": max(50, 102 - int(item["rank"]) * 2),
                        "tier": "HOT" if int(item["rank"]) <= 5 else "WARM",
                        "refresh_interval_hours": (
                            168 if int(item["rank"]) <= 5 else 720
                        ),
                        "last_collected_at": now,
                        "next_collection_at": now + timedelta(
                            days=7 if int(item["rank"]) <= 5 else 30,
                        ),
                        "status": status,
                    },
                )
        self._store.update_city_collection_run(
            run_id,
            status="ready" if not failed else "partial",
            fetched_count=imported["fetchedCount"],
            accepted_count=imported["acceptedCount"],
            failed_count=failed,
            finished_at=now,
            error=interruption_error if crawler_interrupted else None,
        )


def _ranking_version(city_adcode: str, places: list[PlaceSummary]) -> str:
    payload = ":".join([city_adcode, *(place.sourcePoiId for place in places)])
    return f"{datetime.now(timezone.utc):%Y%m%d}-{hashlib.sha256(payload.encode()).hexdigest()[:10]}"


def _crawler_keyword(city_name: str, place_name: str) -> str:
    city = city_name.removesuffix("市")
    return f"{city} {place_name} 攻略".replace(",", " ")


def _map_ranking(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": item["rank"],
        "sourcePoiId": item["poi_id"],
        "name": item["place_name"],
        "rating": item.get("rating"),
        "districtName": item.get("district_name"),
        "crawlerKeyword": item["crawler_keyword"],
    }


def _profile_to_place(profile: dict[str, Any] | None) -> PlaceSummary:
    if profile is None:
        raise ValueError("POI profile is missing")
    return PlaceSummary(
        id=f"amap:{profile['poi_id']}",
        sourcePoiId=profile["poi_id"],
        name=profile["name"],
        category=profile.get("category") or "scenic",
        categoryCode=profile.get("category_code") or "110000",
        address=profile.get("address"),
        provinceName=profile.get("province_name"),
        cityName=profile.get("city_name"),
        districtName=profile.get("district_name"),
        adCode=profile.get("ad_code"),
        latitude=profile.get("latitude"),
        longitude=profile.get("longitude"),
        phone=profile.get("phone"),
        rating=profile.get("rating"),
        openingHoursToday=profile.get("opening_hours_today"),
        openingHoursWeek=profile.get("opening_hours_week"),
    )
