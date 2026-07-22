import asyncio

import pytest
from fastapi import HTTPException

from app.api.content import require_content_admin
from app.core.config import Settings
from app.review_store import ReviewStore
from app.schemas.explore import PlaceSummary, ReviewSource
from app.services.content_ingestion_service import ContentIngestionService
from app.services.place_detail_service import PlaceDetailService
from app.services.popular_poi_catalog import PopularPoiSeed
from app.services.tikhub_review_client import ReviewProviderError


def _place() -> PlaceSummary:
    return PlaceSummary(
        id="amap:B001",
        sourcePoiId="B001",
        name="故宫博物院",
        category="scenic",
        categoryCode="110000",
        cityName="北京市",
        districtName="东城区",
    )


class FakeCatalog:
    seeds = (PopularPoiSeed("北京市", "故宫博物院", 100, official_source_id="dpm"),)

    async def resolve(self, seeds):
        return [(seeds[0], _place())], []


class FakeReviewClient:
    configured = True
    last_error = None

    async def search_places(self, places):
        sources = [
            ReviewSource(
                id=f"xiaohongshu:n{index}",
                platform="小红书",
                title=f"故宫拍照体验 {index}",
                excerpt="拍照很出片，建议提前到达。",
                url=f"https://www.xiaohongshu.com/explore/n{index}",
                author=f"author-{index}",
            )
            for index in range(3)
        ]
        return {places[0].sourcePoiId: sources}


class FailingReviewClient:
    configured = True

    def __init__(self):
        self.last_error = None

    async def search_places(self, places):
        self.last_error = ReviewProviderError(
            "QUOTA_EXHAUSTED",
            "quota exhausted",
            status_code=402,
        )
        raise self.last_error


class FakeOfficialService:
    supported_source_ids = frozenset({"dpm"})

    async def fetch_for_place(self, place, source_id):
        return [
            {
                "notice_id": "dpm:test",
                "poi_id": place.sourcePoiId,
                "notice_type": "RESERVATION",
                "title": "预约规则",
                "summary": "需实名预约",
                "source_url": "https://www.dpm.org.cn/subject_booking/index.html",
            },
        ]


def test_ingestion_run_saves_clean_evidence_and_official_notice() -> None:
    async def scenario():
        store = ReviewStore(":memory:")
        review = FakeReviewClient()
        service = ContentIngestionService(
            FakeCatalog(),
            PlaceDetailService(review, store=store, author_hash_salt="test"),
            store,
            review_client=review,
            official_service=FakeOfficialService(),
        )
        started = await service.start_run(limit=1, force_refresh=True, include_official=True)
        await service._tasks[started["run_id"]]
        return store, service.get_run(started["run_id"])

    store, run = asyncio.run(scenario())
    assert run["status"] == "completed"
    assert run["accepted_count"] == 3
    assert len(store.list_active_evidence("B001")) == 3
    assert len(store.list_official_notices("B001")) == 1
    assert store.get_collection_target("B001")["status"] == "completed"
    store.close()


def test_provider_quota_failure_is_not_recorded_as_empty_success() -> None:
    async def scenario():
        store = ReviewStore(":memory:")
        review = FailingReviewClient()
        service = ContentIngestionService(
            FakeCatalog(),
            PlaceDetailService(review, store=store),
            store,
            review_client=review,
        )
        started = await service.start_run(limit=1, force_refresh=True, include_official=False)
        await service._tasks[started["run_id"]]
        return store, service.get_run(started["run_id"])

    store, run = asyncio.run(scenario())
    assert run["status"] == "partial"
    assert run["failed_count"] == 1
    assert run["error"] == "QUOTA_EXHAUSTED"
    assert store.get_collection_target("B001")["last_error"] == "QUOTA_EXHAUSTED"
    store.close()


def test_content_admin_token_is_required_and_constant_time_checked() -> None:
    with pytest.raises(HTTPException) as missing:
        require_content_admin(None, Settings(content_admin_token=""))
    assert missing.value.status_code == 503

    settings = Settings(content_admin_token="content-admin-token")
    with pytest.raises(HTTPException) as wrong:
        require_content_admin("wrong", settings)
    assert wrong.value.status_code == 401
    assert require_content_admin("content-admin-token", settings) is None
