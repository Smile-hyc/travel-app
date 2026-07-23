import asyncio
from datetime import datetime, timezone

from app.review_store import ReviewStore
from app.schemas.explore import PlaceSummary, ReviewSource
from app.services.place_detail_service import PlaceDetailService


def _place() -> PlaceSummary:
    return PlaceSummary(
        id="amap:B001",
        sourcePoiId="B001",
        name="故宫博物院",
        category="scenic",
        categoryCode="scenic",
        cityName="北京市",
        address="景山前街4号",
        latitude=39.9163,
        longitude=116.3972,
        rating="4.8",
        openingHoursWeek="周二至周日 08:30-17:00",
    )


def _sources() -> list[ReviewSource]:
    return [
        ReviewSource(
            id=f"xiaohongshu:note-{index}",
            platform="小红书",
            title=f"故宫拍照机位分享 {index}",
            excerpt="午后拍照很出片，推荐提前到。",
            url=f"https://www.xiaohongshu.com/explore/note-{index}",
            author=f"author-{index}",
            coverImageUrl="https://example.com/must-not-persist.jpg",
        )
        for index in range(3)
    ]


class FakeAuthorizedProvider:
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    async def search_places(self, places):
        self.calls += 1
        await asyncio.sleep(0.01)
        return {place.sourcePoiId: _sources() for place in places}

    async def search_place(self, place):
        self.calls += 1
        return _sources()


def test_detail_returns_pending_then_streams_three_source_aggregate() -> None:
    async def scenario():
        provider = FakeAuthorizedProvider()
        store = ReviewStore(":memory:")
        service = PlaceDetailService(provider, store=store, author_hash_salt="test")
        initial = await service.ensure_batch([_place()])
        assert initial.pendingCount == 1
        assert initial.items[0].status == "PENDING"
        assert initial.items[0].detail.factLayer.sourcePoiId == "B001"

        events = [event async for event in service.stream_batch(initial.batchId)]
        final = service.get_batch(initial.batchId)
        return provider, store, events, final

    provider, store, events, final = asyncio.run(scenario())
    assert provider.calls == 1
    assert events[-1].type == "COMPLETE"
    assert final is not None
    assert final.items[0].status == "READY"
    detail = final.items[0].detail
    assert detail is not None
    assert detail.experienceLayer.minimumEvidenceCount == 1
    assert detail.experienceLayer.insights[0].mentionCount == 3
    assert "午后拍照很出片" in detail.experienceLayer.insights[0].summary
    assert "多条独立用户内容提到" not in detail.experienceLayer.insights[0].summary
    assert all(source.author is None for source in detail.reviewSources)
    assert all(source.coverImageUrl is None for source in detail.reviewSources)
    assert all(source.anonymousAuthorId for source in detail.reviewSources)
    assert all("must-not-persist" not in str(value) for value in store.list_active_evidence("B001"))
    store.close()


def test_single_attributable_note_is_shown_as_low_sample_reference() -> None:
    store = ReviewStore(":memory:")
    service = PlaceDetailService(FakeAuthorizedProvider(), store=store, author_hash_salt="test")

    result = service.import_review_sources(_place(), _sources()[:1])
    detail = result["detail"]

    assert result["status"] == "READY"
    assert detail.experienceLayer.insights[0].mentionCount == 1
    assert detail.experienceLayer.insights[0].confidence < 0.6
    assert "午后拍照很出片" in detail.experienceLayer.insights[0].summary
    store.close()


def test_concurrent_batches_deduplicate_same_poi_upstream_search() -> None:
    async def scenario():
        provider = FakeAuthorizedProvider()
        service = PlaceDetailService(provider, store=ReviewStore(":memory:"), author_hash_salt="test")
        first = await service.ensure_batch([_place()])
        second = await service.ensure_batch([_place()])
        await asyncio.gather(
            service._batches[first.batchId].task,
            service._batches[second.batchId].task,
        )
        return provider.calls, service.get_batch(first.batchId), service.get_batch(second.batchId)

    calls, first, second = asyncio.run(scenario())
    assert calls == 1
    assert first.items[0].status == "READY"
    assert second.items[0].status == "READY"


def test_unconfigured_provider_returns_facts_without_queue() -> None:
    class DisabledProvider:
        configured = False

        async def search_place(self, place):
            raise AssertionError("disabled provider must not be called")

    async def scenario():
        service = PlaceDetailService(DisabledProvider(), store=ReviewStore(":memory:"))
        return await service.ensure_batch([_place()])

    batch = asyncio.run(scenario())
    assert batch.pendingCount == 0
    assert batch.items[0].status == "UNAVAILABLE"
    assert batch.items[0].detail.factLayer.openingHours


def test_planning_signals_distinguish_access_restriction_from_whole_place_closure() -> None:
    class DisabledProvider:
        configured = False

        async def search_place(self, place):
            raise AssertionError("disabled provider must not be called")

    store = ReviewStore(":memory:")
    store.upsert_place_profile(_place())
    store.upsert_official_source(
        {
            "sourceId": "palace",
            "poiId": "B001",
            "officialName": "故宫博物院",
            "cityName": "北京市",
            "scenicGrade": "5A",
            "maxDailyCapacity": 80000,
        },
    )
    store.upsert_official_notice(
        {
            "noticeId": "sold-out",
            "poiId": "B001",
            "noticeType": "CAPACITY",
            "title": "预约已满",
            "summary": "10月1日门票预约已满，停止售票。",
            "sourceUrl": "https://example.org/sold-out",
            "effectiveFrom": "2026-10-01T00:00:00+00:00",
            "effectiveTo": "2026-10-01T23:59:59+00:00",
        },
    )
    store.upsert_official_notice(
        {
            "noticeId": "ticket",
            "poiId": "B001",
            "noticeType": "TICKET",
            "title": "官方票价",
            "summary": "成人票60元。",
            "sourceUrl": "https://example.org/ticket",
        },
    )
    store.upsert_official_notice(
        {
            "noticeId": "access",
            "poiId": "B001",
            "noticeType": "CLOSURE",
            "title": "接驳调整",
            "summary": "景区东门接驳车临时停运，请从南门进入。",
            "sourceUrl": "https://example.org/access",
            "effectiveFrom": "2026-10-01T00:00:00+00:00",
            "effectiveTo": "2026-10-01T23:59:59+00:00",
        },
    )
    store.upsert_official_notice(
        {
            "noticeId": "holiday",
            "poiId": "B001",
            "noticeType": "HOLIDAY_HOURS",
            "title": "国庆开放调整",
            "summary": "国庆开放时间调整为 08:00-20:00。",
            "sourceUrl": "https://example.org/hours",
            "effectiveFrom": "2026-10-01T00:00:00+00:00",
            "effectiveTo": "2026-10-01T23:59:59+00:00",
        },
    )
    store.upsert_official_notice(
        {
            "noticeId": "closed",
            "poiId": "B001",
            "noticeType": "CLOSURE",
            "title": "临时闭园",
            "summary": "景区闭园一天。",
            "sourceUrl": "https://example.org/closed",
            "effectiveFrom": "2026-10-02T00:00:00+00:00",
            "effectiveTo": "2026-10-02T23:59:59+00:00",
        },
    )
    service = PlaceDetailService(DisabledProvider(), store=store)

    signals = service.get_planning_signals(
        _place(),
        [
            datetime(2026, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 10, 2, tzinfo=timezone.utc),
        ],
    )

    assert signals["officialScenicGrade"] == "5A"
    assert signals["officialMaxDailyCapacity"] == 80000
    assert signals["officialTicketNote"] == "成人票60元。"
    assert "预约已满" in signals["officialCapacityNote"]
    assert signals["officialOpeningHoursByDate"]["2026-10-01"] == "国庆开放时间调整为 08:00-20:00。"
    assert "接驳车临时停运" in signals["officialAccessNote"]
    assert signals["officialClosedDates"] == ["2026-10-01", "2026-10-02"]
    store.close()


def test_expired_cache_is_returned_immediately_and_queued_for_refresh() -> None:
    async def scenario():
        provider = FakeAuthorizedProvider()
        store = ReviewStore(":memory:")
        store.upsert_place_profile(_place())
        store.save_aggregate(
            {
                "poi_id": "B001",
                "summary": "旧缓存样本不足。",
                "status": "INSUFFICIENT",
                "insights": [],
                "evidence_ids": [],
                "summary_version": "experience-rules-v1",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "data_updated_at": "2026-01-01T00:00:00+00:00",
                "expires_at": "2026-01-02T00:00:00+00:00",
            },
        )
        service = PlaceDetailService(provider, store=store, author_hash_salt="test")
        initial = await service.ensure_batch([_place()])
        assert initial.items[0].status == "INSUFFICIENT"
        assert initial.pendingCount == 1
        await service._batches[initial.batchId].task
        return provider.calls, service.get_batch(initial.batchId)

    calls, final = asyncio.run(scenario())
    assert calls == 1
    assert final.items[0].status == "READY"
