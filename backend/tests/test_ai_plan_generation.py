import asyncio

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import ai as ai_api
from app.main import app
from app.schemas.ai import (
    AiGeneratedDay,
    AiGeneratedPlace,
    AiPlanGenerationRequest,
    AiPlanGenerationResponse,
)
from app.schemas.explore import CitySearchResult, PaginatedPlaces, PlaceSummary
from app.services.travel_plan_generation_service import TravelPlanGenerationService
from app.services.ai_plan_job_manager import AiPlanJobManager


client = TestClient(app)


def test_generate_plan_returns_structured_itinerary() -> None:
    class FakePlanGenerationService:
        async def generate(self, request: AiPlanGenerationRequest) -> AiPlanGenerationResponse:
            assert request.destination == "北京"
            assert request.dayCount == 2
            assert request.preferences == ["经典必玩", "历史古建"]
            place = AiGeneratedPlace(
                id="AMAP:B000A83V0P",
                sourcePoiId="B000A83V0P",
                name="故宫博物院",
                category="scenic",
                categoryCode="scenic",
                latitude=39.916345,
                longitude=116.397155,
                suggestedStart="09:00",
                suggestedEnd="11:30",
                note="建议提前确认预约要求。",
            )
            return AiPlanGenerationResponse(
                requestId="request-test",
                title="北京 2 日智能行程",
                destination="北京市",
                dateRange=request.dateRange,
                dayCount=request.dayCount,
                preferences=request.preferences,
                days=[
                    AiGeneratedDay(
                        dayIndex=1,
                        title="DAY 1 · 东城区",
                        summary="经典中轴线",
                        places=[place],
                    ),
                    AiGeneratedDay(
                        dayIndex=2,
                        title="DAY 2 · 海淀区",
                        summary="园林与人文",
                        places=[],
                    ),
                ],
                generatedAt="2026-07-16T00:00:00+00:00",
                model="test-model",
            )

    app.dependency_overrides[ai_api.get_travel_plan_generation_service] = (
        lambda: FakePlanGenerationService()
    )
    try:
        response = client.post(
            "/api/ai/plans/generate",
            json={
                "destination": "北京",
                "dateRange": "07.16 - 07.17",
                "dayCount": 2,
                "preferences": ["经典必玩", "历史古建"],
                "freeText": "步行不要太多",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["requestId"] == "request-test"
    assert payload["dayCount"] == 2
    assert [day["dayIndex"] for day in payload["days"]] == [1, 2]
    assert payload["days"][0]["places"][0]["sourcePoiId"] == "B000A83V0P"


def test_generate_plan_validates_day_count() -> None:
    response = client.post(
        "/api/ai/plans/generate",
        json={
            "destination": "北京",
            "dateRange": "07.16 - 07.30",
            "dayCount": 11,
            "preferences": [],
        },
    )

    assert response.status_code == 422


def test_generate_plan_falls_back_to_real_pois_when_ai_fails() -> None:
    class FakeArkClient:
        model_name = "test-model"

        async def chat(self, *args, **kwargs) -> str:
            raise HTTPException(status_code=502, detail="模型暂时不可用")

    class FakePoiService:
        async def search_cities(self, *, keyword: str, limit: int):
            assert keyword == "北京"
            return [
                CitySearchResult(
                    id="110000",
                    name="北京市",
                    adCode="110000",
                    latitude=39.9042,
                    longitude=116.4074,
                ),
            ]

        async def search_pois(self, *, category: str, **kwargs):
            offset = 0 if category == "scenic" else 100
            items = [
                PlaceSummary(
                    id=f"AMAP:{offset + index}",
                    sourcePoiId=str(offset + index),
                    name=f"{category}-{index}",
                    category=category,
                    categoryCode=category,
                    districtName="东城区",
                    latitude=39.90 + index * 0.002,
                    longitude=116.40 + index * 0.002,
                )
                for index in range(6)
            ]
            return PaginatedPlaces(
                items=items,
                page=1,
                pageSize=6,
                total=6,
                hasMore=False,
            )

    service = TravelPlanGenerationService(
        FakeArkClient(),
        FakePoiService(),
        reveal_delay_seconds=0,
    )
    result = asyncio.run(
        service.generate(
            AiPlanGenerationRequest(
                destination="北京",
                dateRange="07.16 - 07.17",
                dayCount=2,
                preferences=["经典必玩", "美食打卡"],
            ),
        ),
    )

    assert len(result.days) == 2
    assert all(day.places for day in result.days)
    assert result.model is None
    assert result.warnings and "已使用地点偏好与距离规则生成" in result.warnings[0]


def test_plan_job_reports_real_progress_and_is_idempotent() -> None:
    class FakeGenerationService:
        async def generate(self, request, progress=None):
            if progress:
                progress(20, "正在检索真实地点", 0)
            await asyncio.sleep(0)
            if progress:
                progress(90, "正在完成质量检查", request.dayCount)
            return AiPlanGenerationResponse(
                requestId="generated-request",
                title="北京 2 日智能行程",
                destination="北京市",
                dateRange=request.dateRange,
                dayCount=request.dayCount,
                days=[],
                generatedAt="2026-07-16T00:00:00+00:00",
            )

    async def scenario():
        manager = AiPlanJobManager(FakeGenerationService())
        request = AiPlanGenerationRequest(
            destination="北京",
            dateRange="07.16 - 07.17",
            dayCount=2,
            clientRequestId="client-request-001",
        )
        first = await manager.create(request)
        duplicate = await manager.create(request)
        assert duplicate.jobId == first.jobId
        for _ in range(5):
            await asyncio.sleep(0)
            current = await manager.get(first.jobId)
            if current.status == "COMPLETED":
                break
        return current

    result = asyncio.run(scenario())
    assert result.status == "COMPLETED"
    assert result.progress == 100
    assert result.completedDays == 2
    assert result.result is not None


def test_plan_job_can_cancel_in_flight_generation() -> None:
    class SlowGenerationService:
        async def generate(self, request, progress=None):
            if progress:
                progress(30, "正在等待模型编排", 0)
            await asyncio.sleep(60)
            raise AssertionError("cancelled job must not finish")

    async def scenario():
        manager = AiPlanJobManager(SlowGenerationService())
        created = await manager.create(
            AiPlanGenerationRequest(
                destination="北京",
                dateRange="07.16 - 07.17",
                dayCount=2,
            ),
        )
        await asyncio.sleep(0)
        return await manager.cancel(created.jobId)

    result = asyncio.run(scenario())
    assert result.status == "CANCELLED"
    assert result.stage == "已取消智能规划"


def test_plan_job_exposes_partial_days_and_planning_events() -> None:
    place = AiGeneratedPlace(
        id="AMAP:B000A83V0P",
        sourcePoiId="B000A83V0P",
        name="故宫博物院",
        category="scenic",
        categoryCode="scenic",
        latitude=39.916345,
        longitude=116.397155,
        suggestedStart="09:00",
        suggestedEnd="11:30",
        note="建议提前预约。",
    )
    day = AiGeneratedDay(
        dayIndex=1,
        title="DAY 1 · 东城区",
        summary="中轴线",
        places=[place],
    )

    class ProgressiveGenerationService:
        async def generate(self, request, progress=None):
            if progress:
                from app.schemas.ai import AiPlanProgressEvent

                progress(
                    55,
                    "已加入故宫博物院，正在延伸第 1 天路线",
                    0,
                    [day],
                    AiPlanProgressEvent(
                        sequence=1,
                        type="PLACE_ADDED",
                        message="把故宫博物院作为第 1 天起点。",
                        dayIndex=1,
                        placeId=place.id,
                        createdAt="2026-07-16T00:00:00+00:00",
                    ),
                    1,
                )
            await asyncio.sleep(0.02)
            return AiPlanGenerationResponse(
                requestId="generated-request",
                title="北京 1 日智能行程",
                destination="北京市",
                dateRange=request.dateRange,
                dayCount=1,
                days=[day],
                generatedAt="2026-07-16T00:00:00+00:00",
            )

    async def scenario():
        manager = AiPlanJobManager(ProgressiveGenerationService())
        created = await manager.create(
            AiPlanGenerationRequest(
                destination="北京",
                dateRange="07.16",
                dayCount=1,
            ),
        )
        await asyncio.sleep(0)
        return await manager.get(created.jobId)

    snapshot = asyncio.run(scenario())
    assert snapshot.status == "RUNNING"
    assert snapshot.activeDayIndex == 1
    assert snapshot.partialDays[0].places[0].name == "故宫博物院"
    assert snapshot.events[0].sequence == 1
    assert snapshot.events[0].type == "PLACE_ADDED"


def test_constraint_planner_uses_station_hotel_meal_and_open_hours() -> None:
    class FailingArkClient:
        model_name = "test-model"

        async def chat(self, *args, **kwargs) -> str:
            raise HTTPException(status_code=502, detail="模型暂时不可用")

    class ConstraintPoiService:
        async def search_cities(self, *, keyword: str, limit: int):
            return [
                CitySearchResult(
                    id="110000",
                    name="北京市",
                    adCode="110000",
                    latitude=39.9042,
                    longitude=116.4074,
                ),
            ]

        async def search_pois(self, *, category: str, keyword=None, **kwargs):
            if category == "transport":
                items = [
                    PlaceSummary(
                        id="station",
                        sourcePoiId="station",
                        name="北京南站",
                        category="transport",
                        categoryCode="transport",
                        typeName="火车站",
                        rating="4.8",
                        latitude=39.865,
                        longitude=116.379,
                    ),
                ]
            elif category == "lodging":
                items = [
                    PlaceSummary(
                        id="hotel",
                        sourcePoiId="hotel",
                        name="北京王府井酒店",
                        category="lodging",
                        categoryCode="lodging",
                        rating="4.7",
                        latitude=39.914,
                        longitude=116.412,
                    ),
                ]
            else:
                opening = "09:00-17:00" if category == "scenic" else "11:00-22:00"
                items = [
                    PlaceSummary(
                        id=f"{category}-{index}",
                        sourcePoiId=f"{category}-{index}",
                        name=f"{category}-{index}",
                        category=category,
                        categoryCode=category,
                        rating=str(4.9 - index * 0.1),
                        openingHoursToday=opening,
                        openingHoursWeek=f"周一至周日 {opening}",
                        districtName="东城区",
                        latitude=39.90 + index * 0.004,
                        longitude=116.40 + index * 0.004,
                    )
                    for index in range(8)
                ]
            return PaginatedPlaces(
                items=items,
                page=1,
                pageSize=len(items),
                total=len(items),
                hasMore=False,
            )

    service = TravelPlanGenerationService(
        FailingArkClient(),
        ConstraintPoiService(),
        reveal_delay_seconds=0,
    )
    result = asyncio.run(
        service.generate(
            AiPlanGenerationRequest(
                destination="北京",
                dateRange="07.17 - 07.18",
                dayCount=2,
                arrivalStation="北京南站",
                hotelName="北京王府井酒店",
            ),
        ),
    )

    first_categories = [place.category for place in result.days[0].places]
    assert first_categories[:2] == ["transport", "lodging"]
    assert any(place.category == "food" for day in result.days for place in day.places)
    for place in (place for day in result.days for place in day.places if place.category == "scenic"):
        assert "09:00" <= place.suggestedStart < place.suggestedEnd <= "17:00"
        assert place.scheduleVerified is True


def test_ai_optimization_timeout_falls_back_without_long_stall() -> None:
    class SlowArkClient:
        model_name = "slow-model"

        async def chat(self, *args, **kwargs) -> str:
            await asyncio.sleep(60)
            return "{}"

    class MinimalPoiService:
        async def search_cities(self, *, keyword: str, limit: int):
            return [CitySearchResult(id="1", name="北京市", adCode="110000", latitude=39.9, longitude=116.4)]

        async def search_pois(self, *, category: str, **kwargs):
            offset = {"scenic": 0, "food": 100, "transport": 200, "lodging": 300}.get(category, 400)
            items = [
                PlaceSummary(
                    id=f"{category}-{index}",
                    sourcePoiId=f"{offset + index}",
                    name=f"{category}-{index}",
                    category=category,
                    categoryCode=category,
                    typeName="火车站" if category == "transport" else None,
                    latitude=39.9 + index * 0.003,
                    longitude=116.4 + index * 0.003,
                )
                for index in range(8)
            ]
            return PaginatedPlaces(items=items, page=1, pageSize=8, total=8, hasMore=False)

    service = TravelPlanGenerationService(
        SlowArkClient(),
        MinimalPoiService(),
        reveal_delay_seconds=0,
        ai_optimization_timeout_seconds=0.05,
    )
    result = asyncio.run(
        service.generate(
            AiPlanGenerationRequest(destination="北京", dateRange="07.17", dayCount=1),
        ),
    )
    assert result.quality.usedFallback is True
    assert any("自动采用" in warning for warning in result.warnings)


def test_weekly_closure_is_respected_for_trip_date() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    museum = PlaceSummary(
        id="museum",
        sourcePoiId="museum",
        name="示例博物馆",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
        openingHoursWeek="周二至周日 09:00-17:00；周一闭馆",
    )
    monday_request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="07.20 - 07.20",
        dayCount=1,
    )
    assert service._is_open_on_trip_day(museum, monday_request, 1) is False
