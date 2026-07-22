import asyncio
import pytest

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import ai as ai_api
from app.main import app
from app.schemas.ai import (
    AiGeneratedDay,
    AiGeneratedPlace,
    AiGeneratedTransfer,
    AiMapPointInput,
    AiPlanGenerationRequest,
    AiPlanGenerationResponse,
    AiPlanProgressEvent,
)
from app.schemas.explore import CitySearchResult, PaginatedPlaces, PlaceSummary
from app.schemas.routes import RouteCoordinate, RouteSegment, RouteStep
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
        calls = 0

        async def chat(self, *args, **kwargs) -> str:
            self.calls += 1
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

    ark = FakeArkClient()
    service = TravelPlanGenerationService(
        ark,
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
    assert not any(place.category in {"transport", "lodging"} for day in result.days for place in day.places)
    assert result.model is None
    assert result.warnings and "已使用地点偏好与距离规则生成" in result.warnings[0]
    preferred_calls = ark.calls

    fast_result = asyncio.run(
        service.generate(
            AiPlanGenerationRequest(
                destination="北京",
                dateRange="07.16 - 07.17",
                dayCount=2,
                optimizationMode="FAST",
            ),
        ),
    )
    assert ark.calls == preferred_calls
    assert fast_result.model is None
    assert fast_result.quality.dataSources == ["AMAP"]

    with pytest.raises(HTTPException, match="必须 AI 深度优化"):
        asyncio.run(
            service.generate(
                AiPlanGenerationRequest(
                    destination="北京",
                    dateRange="07.16 - 07.17",
                    dayCount=2,
                    optimizationMode="REQUIRED",
                ),
            ),
        )


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


def test_ai_optimization_waits_for_model_and_rejects_incomplete_result() -> None:
    class SlowArkClient:
        model_name = "slow-model"

        async def chat(self, *args, **kwargs) -> str:
            await asyncio.sleep(0.08)
            return '{"title":"慢速模型结果","days":[]}'

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
    )
    result = asyncio.run(
        asyncio.wait_for(
            service.generate(
                AiPlanGenerationRequest(destination="北京", dateRange="07.17", dayCount=1),
            ),
            timeout=1.0,
        )
    )
    assert result.quality.usedFallback is True
    assert result.model is None


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


def test_actual_route_duration_retimes_next_place_and_records_mode() -> None:
    class FakeRouteService:
        async def best_segment(self, **kwargs):
            return RouteSegment(
                originId=kwargs["origin"].id,
                destinationId=kwargs["destination"].id,
                originName=kwargs["origin"].name,
                destinationName=kwargs["destination"].name,
                mode="transit",
                distanceMeters=8200,
                durationSeconds=2700,
                steps=[
                    RouteStep(instruction="乘坐地铁2号线"),
                    RouteStep(instruction="换乘快速公交1线"),
                ],
            )

    service = TravelPlanGenerationService(object(), object(), FakeRouteService(), reveal_delay_seconds=0)
    first = AiGeneratedPlace(
        id="a",
        sourcePoiId="a",
        name="景点A",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
        suggestedStart="09:00",
        suggestedEnd="10:00",
        note="",
    )
    second = AiGeneratedPlace(
        id="b",
        sourcePoiId="b",
        name="景点B",
        category="scenic",
        categoryCode="scenic",
        latitude=39.95,
        longitude=116.5,
        suggestedStart="10:10",
        suggestedEnd="11:10",
        note="",
    )
    days = [AiGeneratedDay(dayIndex=1, title="DAY 1", summary="", places=[first, second])]
    routed = asyncio.run(
        service._apply_actual_routes(
            AiPlanGenerationRequest(destination="北京", dateRange="07.20", dayCount=1),
            days,
            [],
            None,
        ),
    )
    assert routed[0].places[1].suggestedStart == "10:45"
    assert routed[0].transfers[0].mode == "transit"
    assert routed[0].transfers[0].modeLabel == "地铁 + 公交"
    assert routed[0].transfers[0].durationMinutes == 45
    assert routed[0].estimatedDistanceKm == 8.2


def test_meal_that_causes_large_detour_is_removed() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)

    def generated(place_id: str, name: str, category: str, latitude: float, longitude: float):
        return AiGeneratedPlace(
            id=place_id,
            sourcePoiId=place_id,
            name=name,
            category=category,
            categoryCode=category,
            latitude=latitude,
            longitude=longitude,
            suggestedStart="10:00",
            suggestedEnd="11:00",
            note="",
            mealType="LUNCH" if category == "food" else None,
        )

    scenic_a = generated("a", "景点A", "scenic", 39.90, 116.40)
    far_meal = generated("meal", "绕路餐馆", "food", 40.10, 116.70)
    scenic_b = generated("b", "景点B", "scenic", 39.91, 116.41)
    retained, removed = service._filter_meal_detours(
        AiPlanGenerationRequest(
            destination="北京",
            dateRange="07.20",
            dayCount=1,
            transportPreference="MIXED",
        ),
        [scenic_a, far_meal, scenic_b],
    )
    assert [place.id for place in retained] == ["a", "b"]
    assert removed == ["绕路餐馆"]


def test_model_ndjson_stream_emits_auditable_event_before_result() -> None:
    captured_options = {}

    class StreamingArk:
        async def chat_stream(self, messages, *, on_delta, **kwargs):
            captured_options.update(kwargs)
            chunks = [
                '{"kind":"event","type":"MODEL_REASON","message":"雨天优先室内馆",',
                '"dayIndex":1,"evidence":["天气：雨"],"decision":"保留博物馆"}\n',
                '{"kind":"result","plan":{"title":"测试","days":[]}}\n',
            ]
            for chunk in chunks:
                on_delta(chunk)
            return "".join(chunks)

    service = TravelPlanGenerationService(StreamingArk(), object(), reveal_delay_seconds=0)
    candidate = PlaceSummary(
        id="museum",
        sourcePoiId="museum",
        name="博物馆",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
    )
    events = []

    def progress(*args):
        if args[4] is not None:
            events.append(args[4])

    payload = asyncio.run(
        service._generate_with_ai(
            AiPlanGenerationRequest(destination="北京", dateRange="07.20", dayCount=1),
            "北京市",
            [candidate],
            [],
            progress,
        ),
    )
    assert payload["title"] == "测试"
    assert events[0].type == "MODEL_REASON"
    assert events[0].evidence == ["天气：雨"]
    assert events[0].decision == "保留博物馆"
    assert "thinking_type" not in captured_options
    assert captured_options["max_tokens"] == 2200


def test_sse_endpoint_streams_progress_and_completion() -> None:
    class FakeStreamingService:
        async def generate(self, request, progress=None):
            progress(35, "正在核验天气", 0)
            await asyncio.sleep(0)
            progress(70, "正在核验路线", 1)
            return AiPlanGenerationResponse(
                requestId="stream-result",
                title="北京 1 日行程",
                destination="北京市",
                dateRange=request.dateRange,
                dayCount=1,
                days=[],
                generatedAt="2026-07-19T00:00:00+00:00",
            )

    app.dependency_overrides[ai_api.get_travel_plan_generation_service] = lambda: FakeStreamingService()
    try:
        response = client.post(
            "/api/ai/plans/stream",
            json={"destination": "北京", "dateRange": "07.20", "dayCount": 1},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    assert "event: complete" in response.text
    assert '"requestId":"stream-result"' in response.text


def test_heuristic_plan_can_place_distinctive_breakfast_lunch_and_dinner() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    scenic = [
        PlaceSummary(
            id=f"scenic-{index}",
            sourcePoiId=f"scenic-{index}",
            name=f"景点{index}",
            category="scenic",
            categoryCode="scenic",
            latitude=39.90 + index * 0.002,
            longitude=116.40 + index * 0.002,
            openingHoursWeek="周一至周日 08:00-22:00",
        )
        for index in range(4)
    ]
    food_names = ["老字号豆浆烧饼早餐", "北京特色炸酱面", "老北京铜锅涮肉"]
    food = [
        PlaceSummary(
            id=f"food-{index}",
            sourcePoiId=f"food-{index}",
            name=name,
            category="food",
            categoryCode="food",
            latitude=39.901 + index * 0.002,
            longitude=116.401 + index * 0.002,
            openingHoursWeek="周一至周日 07:00-23:00",
        )
        for index, name in enumerate(food_names)
    ]
    days = service._build_heuristic_days(
        AiPlanGenerationRequest(
            destination="北京",
            dateRange="07.20",
            dayCount=1,
            dailyStart="08:00",
            dailyEnd="21:00",
        ),
        scenic + food,
        city_name="北京市",
    )
    meal_types = {place.mealType for place in days[0].places if place.mealType}
    assert {"BREAKFAST", "LUNCH", "DINNER"}.issubset(meal_types)


def test_evening_place_is_scheduled_only_after_dinner_when_suitable() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    scenic = [
        PlaceSummary(
            id="morning",
            sourcePoiId="morning",
            name="城市博物馆",
            category="scenic",
            categoryCode="scenic",
            latitude=39.900,
            longitude=116.400,
            openingHoursWeek="周一至周日 08:00-18:00",
        ),
        PlaceSummary(
            id="afternoon",
            sourcePoiId="afternoon",
            name="历史街区展馆",
            category="scenic",
            categoryCode="scenic",
            latitude=39.902,
            longitude=116.402,
            openingHoursWeek="周一至周日 09:00-18:00",
        ),
        PlaceSummary(
            id="night",
            sourcePoiId="night",
            name="城市夜景广场",
            category="scenic",
            categoryCode="scenic",
            latitude=39.904,
            longitude=116.404,
        ),
    ]
    foods = [
        PlaceSummary(
            id=f"meal-{index}",
            sourcePoiId=f"meal-{index}",
            name=name,
            category="food",
            categoryCode="food",
            latitude=39.901 + index * 0.001,
            longitude=116.401 + index * 0.001,
            openingHoursWeek="周一至周日 07:00-23:00",
        )
        for index, name in enumerate(("特色早餐铺", "地方午餐馆", "老字号晚餐馆"))
    ]

    day = service._build_heuristic_days(
        AiPlanGenerationRequest(
            destination="北京",
            dateRange="07.22",
            dayCount=1,
            dailyStart="08:00",
            dailyEnd="21:00",
        ),
        scenic + foods,
        city_name="北京市",
    )[0]

    dinner_index = next(index for index, place in enumerate(day.places) if place.mealType == "DINNER")
    night_index = next(index for index, place in enumerate(day.places) if place.sourcePoiId == "night")
    assert night_index > dinner_index
    assert day.places[night_index].suggestedStart >= day.places[dinner_index].suggestedEnd


def _ai_review_place(
    place_id: str,
    category: str,
    start: str,
    end: str,
    meal_type: str | None = None,
) -> AiGeneratedPlace:
    return AiGeneratedPlace(
        id=place_id,
        sourcePoiId=place_id,
        name=place_id,
        category=category,
        categoryCode=category,
        latitude=39.9,
        longitude=116.4,
        suggestedStart=start,
        suggestedEnd=end,
        note="",
        mealType=meal_type,
        rating="4.6",
    )


def test_ai_review_rejects_plan_that_drops_required_meal_period() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    breakfast = _ai_review_place("早餐", "food", "08:00", "09:00", "BREAKFAST")
    scenic = _ai_review_place("景点", "scenic", "09:30", "11:30")
    lunch = _ai_review_place("午餐", "food", "12:00", "13:00", "LUNCH")
    baseline = AiGeneratedDay(dayIndex=1, title="DAY 1", summary="规则草案", places=[breakfast, scenic, lunch])
    candidate = baseline.model_copy(update={"summary": "AI建议", "places": [breakfast, scenic]}, deep=True)

    selected, accepted, notes = service._select_ai_optimized_days(
        AiPlanGenerationRequest(destination="北京", dateRange="07.22", dayCount=1, dailyStart="08:00"),
        [baseline],
        [candidate],
    )

    assert accepted == 0
    assert selected[0].summary == "规则草案"
    assert "必要餐期" in notes[0]


def test_ai_review_accepts_safe_copywriting_improvement_without_reordering() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    scenic = _ai_review_place("景点", "scenic", "09:30", "11:30")
    baseline = AiGeneratedDay(dayIndex=1, title="DAY 1", summary="规则草案", places=[scenic])
    candidate = baseline.model_copy(update={"summary": "AI优化后的主题说明"}, deep=True)

    selected, accepted, notes = service._select_ai_optimized_days(
        AiPlanGenerationRequest(destination="北京", dateRange="07.22", dayCount=1),
        [baseline],
        [candidate],
    )

    assert accepted == 1
    assert selected[0].summary == "AI优化后的主题说明"
    assert "顺序不变" in notes[0]


def test_ai_review_event_is_part_of_the_public_progress_contract() -> None:
    event = AiPlanProgressEvent(
        sequence=1,
        type="AI_REVIEW",
        message="AI 建议复核完成",
        createdAt="2026-07-22T00:00:00Z",
    )

    assert event.type == "AI_REVIEW"


def test_meal_roles_follow_station_times_and_free_text_instead_of_fixed_template() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    late_arrival = AiPlanGenerationRequest(
        destination="成都",
        dateRange="07.22",
        dayCount=1,
        arrivalDay=1,
        arrivalTime="11:30",
        departureDay=1,
        departureTime="17:00",
        dailyStart="08:00",
        dailyEnd="21:00",
    )
    sleep_in = late_arrival.model_copy(
        update={"arrivalTime": "08:00", "departureTime": "21:00", "freeText": "睡到自然醒，不安排早餐"},
    )

    assert service._requested_meal_roles(late_arrival, 1, full_day=False) == ["LUNCH"]
    assert service._requested_meal_roles(sleep_in, 1, full_day=False) == ["LUNCH", "DINNER"]


def test_preferences_affect_scenic_ranking_and_requested_density() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="南京",
        dateRange="07.22",
        dayCount=1,
        preferences=["文艺展览"],
        freeText="不要太累，慢慢逛",
    )
    museum = PlaceSummary(
        id="museum",
        sourcePoiId="museum",
        name="城市美术馆",
        category="scenic",
        categoryCode="scenic",
        latitude=32.0,
        longitude=118.8,
    )
    park = museum.model_copy(update={"id": "park", "sourcePoiId": "park", "name": "城市公园"})

    assert service._preference_place_score(request, museum) > service._preference_place_score(request, park)
    assert service._scenic_target_for_request(request) == 2


def test_map_selected_anchor_keeps_exact_coordinates() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    point = AiMapPointInput(
        name="自驾停车位置",
        address="北京市东城区测试路1号",
        latitude=39.901234,
        longitude=116.401234,
    )

    place = service._map_point_summary(point, "transport", "北京市", "110100")

    assert place is not None
    assert place.source == "MAP_SELECTED"
    assert place.latitude == point.latitude
    assert place.longitude == point.longitude
    assert place.name == point.name


def test_map_selected_anchor_must_belong_to_destination_city() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="成都",
        dateRange="07.22",
        dayCount=1,
        hotelName="地图住宿",
        hotelPoint=AiMapPointInput(
            name="南京酒店",
            latitude=32.0,
            longitude=118.8,
            adCode="320102",
            cityName="南京市",
        ),
    )

    with pytest.raises(HTTPException) as exc:
        service._validate_map_point_cities(request, "510100", "成都市")

    assert exc.value.status_code == 422
    assert "不在目的城市" in str(exc.value.detail)


def test_ai_merge_preserves_repeated_hotel_anchor_occurrences() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="成都",
        dateRange="07.22",
        dayCount=1,
        dailyStart="08:00",
        dailyEnd="23:00",
    )
    hotel = _ai_review_place("hotel", "lodging", "08:00", "08:45")
    scenic = _ai_review_place("scenic", "scenic", "09:30", "11:30")
    baseline = AiGeneratedDay(
        dayIndex=1,
        title="DAY 1",
        summary="草案",
        places=[hotel, scenic, hotel.model_copy(update={"suggestedStart": "21:00", "suggestedEnd": "21:45"})],
    )
    scenic_candidate = PlaceSummary(
        id="scenic",
        sourcePoiId="scenic",
        name="scenic",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
    )

    merged = service._merge_ai_result(
        request,
        {"days": [{"dayIndex": 1, "places": [{"sourcePoiId": "scenic"}]}]},
        [scenic_candidate],
        [baseline],
    )

    assert [place.sourcePoiId for place in merged[0].places].count("hotel") == 2
    assert merged[0].places[0].sourcePoiId == "hotel"
    assert merged[0].places[-1].sourcePoiId == "hotel"


def test_generated_transfer_serializes_actual_route_polyline() -> None:
    transfer = AiGeneratedTransfer(
        originPlaceId="a",
        destinationPlaceId="b",
        mode="driving",
        distanceMeters=1200,
        durationMinutes=8,
        polyline=[
            RouteCoordinate(latitude=39.9, longitude=116.4),
            RouteCoordinate(latitude=39.91, longitude=116.41),
        ],
    )

    assert len(transfer.model_dump()["polyline"]) == 2
