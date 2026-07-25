import asyncio
import json
from datetime import datetime
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
from app.services.amap_weather_service import AmapWeatherForecastDay
from app.services.ai_plan_job_manager import AiPlanJobManager
from app.services.ai_plan_job_manager import planning_event_fingerprint


client = TestClient(app)


def test_legacy_preferred_mode_is_merged_into_ai_optimization() -> None:
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.25",
        dayCount=1,
        optimizationMode="PREFERRED",
    )

    assert request.optimizationMode == "REQUIRED"


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
    assert not any("AI" in warning for warning in result.warnings)
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

    required_result = asyncio.run(
        service.generate(
            AiPlanGenerationRequest(
                destination="北京",
                dateRange="07.16 - 07.17",
                dayCount=2,
                optimizationMode="REQUIRED",
            ),
        ),
    )
    assert required_result.days
    assert required_result.quality.usedFallback is True

    async def unexpected_ai_failure(*args, **kwargs) -> str:
        raise RuntimeError("unexpected model adapter failure")

    ark.chat = unexpected_ai_failure
    unexpected_result = asyncio.run(
        service.generate(
            AiPlanGenerationRequest(
                destination="北京",
                dateRange="07.16 - 07.17",
                dayCount=2,
                optimizationMode="REQUIRED",
            ),
        ),
    )
    assert unexpected_result.days
    assert unexpected_result.quality.usedFallback is True
    assert not any("AI" in warning for warning in unexpected_result.warnings)


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
    assert routed[0].places[1].suggestedStart == "11:00"
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


def test_meal_with_large_actual_route_detour_is_removed() -> None:
    class FakeRouteService:
        async def best_segment(self, **kwargs):
            origin = kwargs["origin"].id
            destination = kwargs["destination"].id
            minutes = {("a", "meal"): 18, ("meal", "b"): 20, ("a", "b"): 10}[(origin, destination)]
            distance = {("a", "meal"): 1800, ("meal", "b"): 1900, ("a", "b"): 900}[(origin, destination)]
            return RouteSegment(
                originId=origin,
                destinationId=destination,
                originName=origin,
                destinationName=destination,
                mode="driving",
                distanceMeters=distance,
                durationSeconds=minutes * 60,
            )

    service = TravelPlanGenerationService(object(), object(), FakeRouteService(), reveal_delay_seconds=0)
    places = [
        _ai_review_place("a", "scenic", "09:00", "10:00"),
        _ai_review_place("meal", "food", "12:00", "13:00").model_copy(update={"mealType": "LUNCH"}),
        _ai_review_place("b", "scenic", "14:00", "15:00"),
    ]

    retained, removed = asyncio.run(
        service._filter_meal_actual_detours(
            AiPlanGenerationRequest(destination="北京", dateRange="07.20", dayCount=1),
            places,
            "2026-07-20",
            True,
        ),
    )

    assert [place.id for place in retained] == ["a", "b"]
    assert removed == ["meal"]


def test_ai_review_rejects_new_unverified_route() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    first = _ai_review_place("a", "scenic", "09:00", "10:00")
    second = _ai_review_place("b", "scenic", "10:30", "11:30")
    verified_transfer = AiGeneratedTransfer(
        originPlaceId="a",
        destinationPlaceId="b",
        mode="walking",
        distanceMeters=800,
        durationMinutes=15,
        verified=True,
    )
    baseline = AiGeneratedDay(
        dayIndex=1,
        title="DAY 1",
        summary="草案",
        places=[first, second],
        transfers=[verified_transfer],
        estimatedDistanceKm=0.8,
    )
    candidate = baseline.model_copy(
        update={"transfers": [verified_transfer.model_copy(update={"verified": False})]},
        deep=True,
    )

    violations = service._ai_day_violations(
        AiPlanGenerationRequest(destination="北京", dateRange="07.20", dayCount=1),
        baseline,
        candidate,
    )

    assert "新增了无法由高德确认的交通路段" in violations


def test_model_ndjson_stream_emits_auditable_event_before_result() -> None:
    captured_options = {}

    class StreamingArk:
        async def chat_stream(self, messages, *, on_delta, **kwargs):
            captured_options.update(kwargs)
            chunks = [
                '{"kind":"event","type":"MODEL_REASON","message":"雨天优先室内馆",',
                '"dayIndex":1,"evidence":["天气：雨"],"decision":"保留博物馆"}\n',
                '{"kind":"result","proposal":{"changes":[]}}\n',
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
    assert payload["changes"] == []
    assert events[0].type == "MODEL_REASON"
    assert events[0].evidence == ["天气：雨"]
    assert events[0].decision == "保留博物馆"
    assert captured_options["thinking_enabled"] is False
    assert captured_options["max_tokens"] == 1400


def test_deep_mode_reviews_once_then_reuses_cached_assessment_for_patch_generation() -> None:
    class TwoStageModel:
        def __init__(self) -> None:
            self.review_calls = 0
            self.patch_prompts = []

        async def chat(self, messages, **kwargs):
            self.review_calls += 1
            assert kwargs["max_tokens"] == 16000
            assert kwargs["disable_read_timeout"] is True
            assert kwargs["thinking_enabled"] is True
            assert kwargs["reasoning_effort"] == "high"
            assert kwargs["json_mode"] is True
            return json.dumps(
                {
                    "strengths": ["经典地点已覆盖"],
                    "problems": [
                        {
                            "dayIndex": 1,
                            "type": "VARIETY",
                            "message": "连续同类展馆，体验较单调",
                            "evidence": ["上午和下午均为博物馆"],
                        },
                    ],
                },
                ensure_ascii=False,
            )

        async def chat_stream(self, messages, *, on_delta, **kwargs):
            self.patch_prompts.append(messages[-1]["content"])
            result = '{"kind":"result","proposal":{"changes":[]}}\n'
            on_delta(result)
            return result

    model = TwoStageModel()
    service = TravelPlanGenerationService(model, object(), reveal_delay_seconds=0)
    museum = _ai_review_place("museum", "scenic", "09:00", "11:00").model_copy(
        update={"name": "城市博物馆", "districtName": "中心区"},
    )
    day = AiGeneratedDay(dayIndex=1, title="DAY 1", summary="", places=[museum])
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.25",
        dayCount=1,
        optimizationMode="REQUIRED",
    )
    candidate = service._generated_to_summary(museum)

    first = asyncio.run(service._generate_with_ai(request, "北京市", [candidate], [day], None))
    second = asyncio.run(service._generate_with_ai(request, "北京市", [candidate], [day], None))

    assert first["changes"] == []
    assert second["changes"] == []
    assert model.review_calls == 1
    assert all("连续同类展馆" in prompt for prompt in model.patch_prompts)


def test_reasoning_review_failure_retries_with_compact_non_thinking_review() -> None:
    class ReviewFallbackModel:
        fallback_model_name = "deepseek-chat"
        reasoning_max_output_tokens = 16000
        reasoning_effort = "high"

        def __init__(self) -> None:
            self.review_options = []

        async def chat(self, messages, **kwargs):
            self.review_options.append(kwargs)
            if kwargs["thinking_enabled"] is True:
                raise HTTPException(status_code=502, detail="reasoning-only")
            return json.dumps({"strengths": ["路线紧凑"], "problems": []}, ensure_ascii=False)

        async def chat_stream(self, messages, *, on_delta, **kwargs):
            result = '{"kind":"result","proposal":{"changes":[]}}\n'
            on_delta(result)
            return result

    model = ReviewFallbackModel()
    service = TravelPlanGenerationService(model, object(), reveal_delay_seconds=0)
    place = _ai_review_place("museum", "scenic", "09:00", "11:00")
    day = AiGeneratedDay(dayIndex=1, title="DAY 1", summary="", places=[place])

    result = asyncio.run(
        service._generate_with_ai(
            AiPlanGenerationRequest(
                destination="北京",
                dateRange="2026.07.25",
                dayCount=1,
                optimizationMode="REQUIRED",
            ),
            "北京市",
            [service._generated_to_summary(place)],
            [day],
            None,
        ),
    )

    assert result["changes"] == []
    assert len(model.review_options) == 2
    assert model.review_options[0]["thinking_enabled"] is True
    assert model.review_options[0]["reasoning_effort"] == "high"
    assert model.review_options[1]["thinking_enabled"] is False
    assert model.review_options[1]["model"] == "deepseek-chat"
    assert model.review_options[1]["max_tokens"] == 1800


def test_ai_candidate_context_excludes_unrelated_far_place() -> None:
    class CapturingModel:
        def __init__(self) -> None:
            self.user_payload = None

        async def chat_stream(self, messages, *, on_delta, **kwargs):
            self.user_payload = json.loads(messages[-1]["content"])
            result = '{"kind":"result","proposal":{"changes":[]}}\n'
            on_delta(result)
            return result

    model = CapturingModel()
    service = TravelPlanGenerationService(model, object(), reveal_delay_seconds=0)
    planned = _ai_review_place("planned", "scenic", "09:00", "11:00").model_copy(
        update={"districtName": "东城区", "latitude": 39.90, "longitude": 116.40},
    )
    nearby = PlaceSummary(
        id="nearby", sourcePoiId="nearby", name="附近景点", category="scenic", categoryCode="scenic",
        latitude=39.91, longitude=116.41, districtName="东城区",
    )
    far = PlaceSummary(
        id="far", sourcePoiId="far", name="远处景点", category="scenic", categoryCode="scenic",
        latitude=40.30, longitude=117.10, districtName="远郊区",
    )
    day = AiGeneratedDay(dayIndex=1, title="DAY 1", summary="", places=[planned])

    asyncio.run(
        service._generate_with_ai(
            AiPlanGenerationRequest(
                destination="北京", dateRange="2026.07.25", dayCount=1, optimizationMode="REQUIRED",
            ),
            "北京市",
            [service._generated_to_summary(planned), nearby, far],
            [day],
            None,
        ),
    )

    ids = {item["sourcePoiId"] for item in model.user_payload["candidatePlaces"]}
    assert ids == {"planned", "nearby"}


def test_model_patch_replaces_only_movable_candidate() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(destination="北京", dateRange="07.20", dayCount=1)
    old = _ai_review_place("old", "scenic", "09:30", "11:00")
    baseline = AiGeneratedDay(dayIndex=1, title="DAY 1", summary="草案", places=[old])
    replacement = PlaceSummary(
        id="new",
        sourcePoiId="new",
        name="新景点",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
        openingHoursWeek="周一至周日 09:00-18:00",
    )

    result = service._apply_ai_proposal(
        request,
        {"changes": [{"type": "REPLACE_PLACE", "dayIndex": 1, "oldPoiId": "old", "newPoiId": "new"}]},
        [replacement],
        [baseline],
    )

    assert result[0].places[0].sourcePoiId == "new"


def test_model_patch_cannot_replace_user_mandatory_place() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(destination="北京", dateRange="07.20", dayCount=1, freeText="故宫必须去")
    old = _ai_review_place("old", "scenic", "09:30", "11:00").model_copy(update={"name": "故宫"})
    baseline = AiGeneratedDay(dayIndex=1, title="DAY 1", summary="草案", places=[old])
    replacement = PlaceSummary(
        id="new",
        sourcePoiId="new",
        name="新景点",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
    )

    result = service._apply_ai_proposal(
        request,
        {"changes": [{"type": "REPLACE_PLACE", "dayIndex": 1, "oldPoiId": "old", "newPoiId": "new"}]},
        [replacement],
        [baseline],
    )

    assert result[0].places[0].sourcePoiId == "old"


def test_planning_event_fingerprint_deduplicates_non_adjacent_equivalent_events() -> None:
    first = AiPlanProgressEvent(
        sequence=1,
        type="ANALYSIS",
        message="正在完善行程安排",
        dayIndex=1,
        createdAt="2026-07-22T00:00:00Z",
    )
    repeated = first.model_copy(update={"sequence": 3, "createdAt": "2026-07-22T00:00:02Z"})

    assert planning_event_fingerprint(first) == planning_event_fingerprint(repeated)


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


def test_breakfast_endpoint_does_not_double_count_first_scenic_distance() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    first_scenic = PlaceSummary(
        id="scenic",
        sourcePoiId="scenic",
        name="首个景点",
        category="scenic",
        categoryCode="scenic",
        latitude=39.900,
        longitude=116.400,
    )
    breakfast = PlaceSummary(
        id="breakfast",
        sourcePoiId="breakfast",
        name="老字号豆浆烧饼早餐",
        category="food",
        categoryCode="food",
        latitude=39.905,
        longitude=116.405,
    )

    selected = service._pick_meal(
        [breakfast],
        set(),
        first_scenic,
        first_scenic,
        "BREAKFAST",
        "北京市",
        "MIXED",
    )

    assert selected is not None
    assert selected.sourcePoiId == "breakfast"


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


def test_ai_review_does_not_treat_draft_meals_as_hard_constraints() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    breakfast = _ai_review_place("早餐", "food", "08:00", "09:00", "BREAKFAST")
    scenic = _ai_review_place("景点", "scenic", "09:30", "11:30")
    lunch = _ai_review_place("午餐", "food", "12:00", "13:00", "LUNCH")
    baseline = AiGeneratedDay(dayIndex=1, title="DAY 1", summary="规则草案", places=[breakfast, scenic, lunch])
    candidate = baseline.model_copy(update={"summary": "AI建议", "places": [breakfast, scenic]}, deep=True)

    violations = service._ai_day_violations(
        AiPlanGenerationRequest(destination="北京", dateRange="07.22", dayCount=1, dailyStart="08:00"),
        baseline,
        candidate,
    )

    assert not any("必要餐期" in violation for violation in violations)


def test_preference_recall_includes_popular_and_matching_attraction_queries() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)

    keywords = service._preference_recall_keywords(
        "北京市",
        ["经典必玩", "历史古建", "拍照出片"],
        "晚上想看夜景",
    )

    assert "北京历史古迹" in keywords
    assert "北京摄影夜景" in keywords


def test_classic_preference_boosts_recognized_popular_attractions() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.10.01",
        dayCount=1,
        preferences=["经典必玩"],
    )
    landmark = PlaceSummary(
        id="landmark",
        sourcePoiId="landmark",
        name="国家博物馆",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
        rating="4.8",
        officialScenicGrade="5A",
        experienceEvidenceCount=20,
    )
    generic = landmark.model_copy(
        update={
            "id": "generic",
            "sourcePoiId": "generic",
            "name": "普通游览点",
            "rating": "4.1",
            "officialScenicGrade": None,
            "experienceEvidenceCount": 0,
        },
    )

    assert service._preference_place_score(request, landmark) > service._preference_place_score(request, generic)


def test_future_today_hours_can_be_used_only_as_unverified_hint() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(destination="北京", dateRange="2026.10.01", dayCount=1)
    place = PlaceSummary(
        id="hint",
        sourcePoiId="hint",
        name="开放时间待确认景点",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
        openingHoursToday="10:00-20:00",
    )

    assert service._opening_windows_for_day(place, request, 1) == []
    assert [(item.start, item.end) for item in service._opening_hint_windows_for_day(place, request, 1)] == [
        (10 * 60, 20 * 60),
    ]
    generated = service._schedule_places(request, [place], 1)
    assert generated[0].scheduleVerified is False
    assert "尚未按出行日期确认" in generated[0].note


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


def test_official_closure_date_is_a_hard_constraint() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(destination="北京", dateRange="07.23", dayCount=1)
    place = PlaceSummary(
        id="closed",
        sourcePoiId="closed",
        name="临时闭园景区",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
        officialClosedDates=[f"{datetime.now().year}-07-23"],
    )

    assert service._is_open_on_trip_day(place, request, 1) is False


def test_user_reservation_time_becomes_a_visit_window() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="07.23",
        dayCount=2,
        freeText="第2天故宫博物院预约10:00，必须保留",
    )
    place = PlaceSummary(
        id="palace",
        sourcePoiId="palace",
        name="故宫博物院",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
    )

    assert service._requested_day_for_place(request, place) == 2
    window = service._user_visit_window(request, place, 2, 120)
    assert window is not None
    assert window.start == 10 * 60
    assert window.end == 12 * 60 + 30


def test_trip_date_supports_full_year_and_cross_year_ranges() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="哈尔滨",
        dateRange="2026.12.31 - 2027.01.02",
        dayCount=3,
    )

    assert service._trip_date(request, 1).date().isoformat() == "2026-12-31"
    assert service._trip_date(request, 3).date().isoformat() == "2027-01-02"


def test_weather_alternatives_are_unused_open_places_in_same_area() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(destination="北京", dateRange="07.23", dayCount=1)
    scheduled = _ai_review_place("scheduled", "scenic", "09:30", "11:00").model_copy(
        update={"districtName": "东城区"},
    )
    alternative = PlaceSummary(
        id="museum",
        sourcePoiId="museum",
        name="城市博物馆",
        category="scenic",
        categoryCode="scenic",
        districtName="东城区",
        latitude=39.901,
        longitude=116.401,
        openingHoursWeek="周一至周日 09:00-17:00",
    )
    weather = AmapWeatherForecastDay("2026-07-23", "中雨", "小雨", "28", "22")

    result = service._attach_day_alternatives(
        request,
        [AiGeneratedDay(dayIndex=1, title="DAY 1", summary="草案", places=[scheduled])],
        [alternative],
        [weather],
    )

    assert [item.sourcePoiId for item in result[0].alternatives] == ["museum"]
    assert "同片区备选" in result[0].summary


def test_local_official_and_ugc_signals_are_attached_without_network_collection() -> None:
    class FakeDetailService:
        def get_planning_signals(self, place, trip_dates):
            assert trip_dates[0].date().isoformat() == f"{datetime.now().year}-07-23"
            return {
                "officialScenicGrade": "5A",
                "experienceEvidenceCount": 12,
                "officialReservationRequired": True,
            }

    service = TravelPlanGenerationService(
        object(),
        object(),
        reveal_delay_seconds=0,
        place_detail_service=FakeDetailService(),
    )
    place = PlaceSummary(
        id="poi",
        sourcePoiId="poi",
        name="重点景区",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
    )

    enriched = service._attach_planning_signals(
        AiPlanGenerationRequest(destination="北京", dateRange="07.23", dayCount=1),
        [place],
    )[0]

    assert enriched.officialScenicGrade == "5A"
    assert enriched.experienceEvidenceCount == 12
    assert enriched.officialReservationRequired is True


def test_actual_route_conflict_replaces_optional_scenic_with_same_area_candidate() -> None:
    class FakeRouteService:
        async def best_segment(self, **kwargs):
            destination = kwargs["destination"]
            minutes = 120 if destination.id == "closed" else 10
            return RouteSegment(
                originId=kwargs["origin"].id,
                destinationId=destination.id,
                originName=kwargs["origin"].name,
                destinationName=destination.name,
                mode="driving",
                distanceMeters=1000,
                durationSeconds=minutes * 60,
            )

    service = TravelPlanGenerationService(object(), object(), FakeRouteService(), reveal_delay_seconds=0)
    hotel = _ai_review_place("hotel", "lodging", "08:00", "09:00")
    closed = _ai_review_place("closed", "scenic", "09:10", "10:00").model_copy(
        update={"name": "早闭馆景点", "districtName": "东城区", "openingHoursWeek": "周一至周日 09:00-10:00"},
    )
    replacement = PlaceSummary(
        id="replacement",
        sourcePoiId="replacement",
        name="同区博物馆",
        category="scenic",
        categoryCode="scenic",
        districtName="东城区",
        latitude=39.901,
        longitude=116.401,
        openingHoursWeek="周一至周日 09:00-18:00",
    )

    routed = asyncio.run(
        service._apply_actual_routes(
            AiPlanGenerationRequest(destination="北京", dateRange="2026.07.23", dayCount=1),
            [AiGeneratedDay(dayIndex=1, title="DAY 1", summary="", places=[hotel, closed])],
            [],
            None,
            repair_candidates=[replacement],
        ),
    )

    assert [place.sourcePoiId for place in routed[0].places] == ["hotel", "replacement"]
    assert routed[0].transfers[0].verified is True


def test_actual_route_conflict_never_silently_drops_mandatory_place() -> None:
    class FakeRouteService:
        async def best_segment(self, **kwargs):
            return RouteSegment(
                originId=kwargs["origin"].id,
                destinationId=kwargs["destination"].id,
                originName=kwargs["origin"].name,
                destinationName=kwargs["destination"].name,
                mode="driving",
                distanceMeters=12000,
                durationSeconds=120 * 60,
            )

    service = TravelPlanGenerationService(object(), object(), FakeRouteService(), reveal_delay_seconds=0)
    hotel = _ai_review_place("hotel", "lodging", "08:00", "09:00")
    mandatory = _ai_review_place("must", "scenic", "09:10", "10:00").model_copy(
        update={"name": "必去景点", "openingHoursWeek": "周一至周日 09:00-10:00"},
    )
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.23",
        dayCount=1,
        freeText="必去景点必须去",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service._apply_actual_routes(
                request,
                [AiGeneratedDay(dayIndex=1, title="DAY 1", summary="", places=[hotel, mandatory])],
                [],
                None,
            ),
        )

    assert exc.value.status_code == 422
    assert "无法同时满足硬约束" in str(exc.value.detail)


def test_actual_route_conflict_does_not_fail_whole_plan_for_default_popular_place() -> None:
    class FakeRouteService:
        async def best_segment(self, **kwargs):
            return RouteSegment(
                originId=kwargs["origin"].id,
                destinationId=kwargs["destination"].id,
                originName=kwargs["origin"].name,
                destinationName=kwargs["destination"].name,
                mode="walking",
                distanceMeters=700,
                durationSeconds=10 * 60,
            )

    service = TravelPlanGenerationService(object(), object(), FakeRouteService(), reveal_delay_seconds=0)
    daytime = _ai_review_place("museum", "scenic", "14:00", "16:00").model_copy(
        update={"name": "北京历史博物馆", "openingHoursWeek": "周一至周日 09:00-18:00"},
    )
    dinner = _ai_review_place("dinner", "food", "17:30", "18:45", "DINNER").model_copy(
        update={"name": "北京烤鸭晚餐馆", "openingHoursWeek": "周一至周日 17:00-22:00"},
    )
    square = _ai_review_place("square", "scenic", "18:50", "20:20").model_copy(
        update={"name": "天安门广场", "openingHoursWeek": "周一至周日 05:00-19:00"},
    )

    routed = asyncio.run(
        service._apply_actual_routes(
            AiPlanGenerationRequest(
                destination="北京", dateRange="2026.07.25", dayCount=1, dailyEnd="22:00",
            ),
            [AiGeneratedDay(
                dayIndex=1,
                title="DAY 1",
                summary="",
                places=[daytime, dinner, square],
            )],
            [],
            None,
        ),
    )

    assert "museum" in {place.sourcePoiId for place in routed[0].places}
    assert "square" not in {place.sourcePoiId for place in routed[0].places}


def test_removed_meal_is_reinserted_from_actual_route_corridor() -> None:
    class FakeRouteService:
        async def best_segment(self, **kwargs):
            return RouteSegment(
                originId=kwargs["origin"].id,
                destinationId=kwargs["destination"].id,
                originName=kwargs["origin"].name,
                destinationName=kwargs["destination"].name,
                mode="walking",
                distanceMeters=600,
                durationSeconds=8 * 60,
            )

    service = TravelPlanGenerationService(object(), object(), FakeRouteService(), reveal_delay_seconds=0)
    scenic_a = _ai_review_place("a", "scenic", "10:30", "11:30")
    scenic_b = _ai_review_place("b", "scenic", "13:00", "14:00")
    meal = PlaceSummary(
        id="meal",
        sourcePoiId="meal",
        name="本地特色午餐",
        category="food",
        categoryCode="food",
        latitude=39.9005,
        longitude=116.4005,
        openingHoursWeek="周一至周日 11:00-14:00",
    )
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.23",
        dayCount=1,
        dailyStart="10:30",
        dailyEnd="16:00",
    )

    repaired, inserted = asyncio.run(
        service._reinsert_missing_meals(
            request,
            1,
            [scenic_a, scenic_b],
            [meal],
            {"a", "b"},
            "2026-07-23",
            True,
        ),
    )

    assert inserted == ["本地特色午餐"]
    assert [place.mealType for place in repaired if place.mealType] == ["LUNCH"]


def test_official_holiday_hours_override_regular_weekly_hours() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(destination="北京", dateRange="2026.10.01", dayCount=1)
    place = PlaceSummary(
        id="holiday",
        sourcePoiId="holiday",
        name="节假日景区",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
        openingHoursWeek="周一至周日 09:00-17:00",
        officialOpeningHoursByDate={"2026-10-01": "国庆开放调整 08:00-20:00"},
    )

    assert service._opening_ranges_for_day(place, request, 1) == [(8 * 60, 20 * 60)]


def test_named_hard_constraints_match_poi_aliases_and_exclusions() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.10.01",
        dayCount=2,
        freeText="第2天故宫预约10:00，天坛必去，不要去王府井",
    )
    palace = PlaceSummary(
        id="palace",
        sourcePoiId="palace",
        name="故宫博物院",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
    )
    forbidden = palace.model_copy(
        update={"id": "forbidden", "sourcePoiId": "forbidden", "name": "王府井步行街"},
    )

    assert service._named_constraint_queries(request, required=True) == ["故宫", "天坛"]
    assert service._requested_day_for_place(request, palace) == 2
    assert service._is_user_mandatory(request, palace) is True
    assert service._is_explicitly_excluded(request, forbidden) is True


def test_missing_required_alias_is_reported_after_route_validation() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.10.01",
        dayCount=1,
        freeText="故宫必去",
    )
    other = _ai_review_place("other", "scenic", "09:00", "11:00").model_copy(
        update={"name": "天坛公园"},
    )

    assert service._missing_required_place_queries(
        request,
        [AiGeneratedDay(dayIndex=1, title="DAY 1", summary="", places=[other])],
    ) == ["故宫"]


def test_multi_day_builder_never_stops_after_first_empty_candidate_day() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.10.01 - 2026.10.03",
        dayCount=3,
    )
    only_place = PlaceSummary(
        id="one",
        sourcePoiId="one",
        name="唯一可行景点",
        category="scenic",
        categoryCode="scenic",
        latitude=39.9,
        longitude=116.4,
        openingHoursWeek="周一至周日 09:00-18:00",
    )

    days = service._build_heuristic_days(request, [only_place])

    assert [day.dayIndex for day in days] == [1, 2, 3]
    assert service._draft_completeness_violations(request, days) == [
        "第2天没有可执行地点或用户锚点",
        "第3天没有可执行地点或用户锚点",
    ]


def test_short_arrival_day_can_be_anchor_only_but_middle_day_cannot() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.10.01 - 2026.10.02",
        dayCount=2,
        arrivalStation="北京南站",
        arrivalTime="19:00",
        dailyEnd="21:00",
    )
    station = _ai_review_place("station", "transport", "19:00", "19:30")
    scenic = _ai_review_place("scenic", "scenic", "09:30", "11:30")
    days = [
        AiGeneratedDay(dayIndex=1, title="DAY 1", summary="抵达", places=[station]),
        AiGeneratedDay(dayIndex=2, title="DAY 2", summary="游览", places=[scenic]),
    ]

    assert service._draft_completeness_violations(request, days) == []


def test_opening_parser_distinguishes_last_admission_from_closing() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)

    windows = service._parse_opening_windows("开放入馆08:30；停止入馆16:00；闭馆17:00")

    assert len(windows) == 1
    assert windows[0].start == 8 * 60 + 30
    assert windows[0].latest_start == 16 * 60
    assert windows[0].end == 17 * 60
    assert service._find_open_slot(windows, 15 * 60 + 30, 90) == (15 * 60 + 30, 17 * 60)
    assert service._find_open_slot(windows, 16 * 60 + 1, 30) is None


def test_road_matrix_reorders_scenic_places_to_keep_both_time_windows() -> None:
    class FakeMatrixRouteService:
        async def road_time_matrix(self, places):
            return {
                ("late", "morning"): (10, 1000),
                ("morning", "late"): (10, 1000),
            }

    service = TravelPlanGenerationService(
        object(),
        object(),
        FakeMatrixRouteService(),
        reveal_delay_seconds=0,
    )
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.23",
        dayCount=1,
        dailyStart="08:30",
        dailyEnd="18:00",
    )
    late = _ai_review_place("late", "scenic", "14:00", "15:30").model_copy(
        update={"name": "下午展馆", "openingHoursWeek": "周一至周日 14:00-17:30"},
    )
    morning = _ai_review_place("morning", "scenic", "09:00", "10:30").model_copy(
        update={"name": "上午展馆", "openingHoursWeek": "周一至周日 09:00-12:00"},
    )

    reordered = asyncio.run(
        service._reorder_day_with_road_matrix(request, 1, [late, morning], None),
    )

    assert [place.sourcePoiId for place in reordered] == ["morning", "late"]
    assert reordered[0].suggestedStart == "09:00"
    assert reordered[1].suggestedStart == "14:00"


def test_famous_public_night_landmark_is_scheduled_in_evening() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="上海",
        dateRange="2026.07.23",
        dayCount=1,
        dailyStart="09:00",
        dailyEnd="21:30",
    )
    landmark = PlaceSummary(
        id="bund",
        sourcePoiId="bund",
        name="上海外滩夜景",
        category="scenic",
        categoryCode="scenic",
        typeName="城市夜景",
        latitude=31.24,
        longitude=121.49,
        rating="4.8",
    )

    selected = service._select_time_window_scenic(request, [landmark], 1, 1, None, None, None)
    scheduled = service._schedule_places(request, selected, 1)

    assert [place.sourcePoiId for place in selected] == ["bund"]
    assert scheduled[0].suggestedStart == "17:30"
    assert scheduled[0].suggestedEnd == "19:00"


def test_night_preference_reserves_evening_landmark_after_daytime_solver() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.23",
        dayCount=1,
        preferences=["经典必玩", "晚上看夜景"],
        dailyStart="09:00",
        dailyEnd="22:00",
    )
    daytime = [
        PlaceSummary(
            id=f"day-{index}",
            sourcePoiId=f"day-{index}",
            name=f"热门博物馆{index}",
            category="scenic",
            categoryCode="scenic",
            typeName="博物馆",
            latitude=39.90 + index * 0.001,
            longitude=116.40 + index * 0.001,
            rating="5.0",
            openingHoursWeek="周一至周日 09:00-18:00",
        )
        for index in range(4)
    ]
    night = PlaceSummary(
        id="night-landmark",
        sourcePoiId="night-landmark",
        name="南锣鼓巷",
        category="scenic",
        categoryCode="scenic",
        typeName="风景名胜",
        latitude=39.905,
        longitude=116.405,
        rating="4.2",
    )
    far_night = PlaceSummary(
        id="far-night",
        sourcePoiId="far-night",
        name="远郊高分夜景广场",
        category="scenic",
        categoryCode="scenic",
        typeName="城市夜景",
        latitude=40.08,
        longitude=116.62,
        rating="5.0",
    )

    selected = service._select_time_window_scenic(
        request,
        [*daytime, far_night, night],
        day_index=1,
        target=3,
        weather=None,
        start_anchor=None,
        end_anchor=None,
    )

    assert len(selected) == 3
    assert "night-landmark" in {place.sourcePoiId for place in selected}
    assert "far-night" not in {place.sourcePoiId for place in selected}


def test_opening_parser_supports_all_day_and_cross_midnight_hours() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)

    all_day = service._parse_opening_windows("24小时营业")
    overnight = service._parse_opening_windows("周一至周日 11:00-02:00")

    assert [(window.start, window.end) for window in all_day] == [(0, 24 * 60)]
    assert [(window.start, window.end) for window in overnight] == [(11 * 60, 24 * 60)]


def test_high_temperature_disables_cycling_and_moves_outdoor_visit_out_of_midday() -> None:
    class CapturingRouteService:
        def __init__(self) -> None:
            self.allow_cycling_values: list[bool] = []

        async def best_segment(self, **kwargs):
            self.allow_cycling_values.append(kwargs["allow_cycling"])
            return RouteSegment(
                originId=kwargs["origin"].id,
                destinationId=kwargs["destination"].id,
                originName=kwargs["origin"].name,
                destinationName=kwargs["destination"].name,
                mode="driving",
                distanceMeters=1200,
                durationSeconds=10 * 60,
            )

    route_service = CapturingRouteService()
    service = TravelPlanGenerationService(object(), object(), route_service, reveal_delay_seconds=0)
    museum = _ai_review_place("museum", "scenic", "09:00", "10:30").model_copy(
        update={
            "name": "城市博物馆",
            "typeName": "博物馆",
            "openingHoursWeek": "周一至周日 09:00-18:00",
        },
    )
    park = _ai_review_place("park", "scenic", "12:00", "13:30").model_copy(
        update={
            "name": "滨江公园",
            "typeName": "公园",
            "openingHoursWeek": "周一至周日 08:00-22:00",
        },
    )

    result = asyncio.run(
        service._apply_actual_routes(
            AiPlanGenerationRequest(
                destination="上海",
                dateRange="2026.07.23",
                dayCount=1,
                dailyStart="09:00",
                dailyEnd="21:30",
            ),
            [AiGeneratedDay(dayIndex=1, title="DAY 1", summary="", places=[museum, park])],
            [AmapWeatherForecastDay("2026-07-23", "晴", "晴", "36", "29")],
            None,
        ),
    )

    assert route_service.allow_cycling_values == [False]
    assert result[0].places[1].suggestedStart >= "16:30"


def test_dessert_or_drink_only_place_cannot_fill_any_meal_role() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    gelato = PlaceSummary(
        id="gelato",
        sourcePoiId="gelato",
        name="野人先生Gelato冰淇淋",
        category="food",
        categoryCode="food",
        latitude=31.23,
        longitude=121.47,
    )
    ice_cream_chain = gelato.model_copy(
        update={"id": "haagen", "sourcePoiId": "haagen", "name": "哈根达斯(滨江店)"},
    )

    for role in ("BREAKFAST", "LUNCH", "DINNER"):
        assert service._meal_role_compatible(gelato, role) is False
        assert service._meal_role_compatible(ice_cream_chain, role) is False


def test_commercial_installation_is_not_selected_as_scenic() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    commercial = PlaceSummary(
        id="commercial",
        sourcePoiId="commercial",
        name="LV巨轮旗舰店",
        category="scenic",
        categoryCode="scenic",
        typeName="商业装置",
        latitude=31.23,
        longitude=121.47,
        rating="4.9",
        openingHoursWeek="周一至周日 10:00-22:00",
    )
    museum = PlaceSummary(
        id="museum",
        sourcePoiId="museum",
        name="上海历史博物馆",
        category="scenic",
        categoryCode="scenic",
        typeName="博物馆",
        latitude=31.231,
        longitude=121.471,
        rating="4.6",
        openingHoursWeek="周一至周日 09:00-18:00",
    )

    days = service._build_heuristic_days(
        AiPlanGenerationRequest(
            destination="上海",
            dateRange="2026.07.23",
            dayCount=1,
            dailyStart="09:00",
            dailyEnd="18:00",
        ),
        [commercial, museum],
    )

    selected_ids = {place.sourcePoiId for place in days[0].places}
    assert "museum" in selected_ids
    assert "commercial" not in selected_ids


def test_late_day_start_places_lunch_before_first_scenic() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    scenic = PlaceSummary(
        id="scenic",
        sourcePoiId="scenic",
        name="城市博物馆",
        category="scenic",
        categoryCode="scenic",
        typeName="博物馆",
        latitude=39.900,
        longitude=116.400,
        openingHoursWeek="周一至周日 09:00-18:00",
    )
    lunch = PlaceSummary(
        id="lunch",
        sourcePoiId="lunch",
        name="北京特色炸酱面",
        category="food",
        categoryCode="food",
        latitude=39.901,
        longitude=116.401,
        openingHoursWeek="周一至周日 11:00-21:00",
    )

    day = service._build_heuristic_days(
        AiPlanGenerationRequest(
            destination="北京",
            dateRange="2026.07.23",
            dayCount=1,
            dailyStart="12:30",
            dailyEnd="18:00",
        ),
        [scenic, lunch],
    )[0]

    lunch_index = next(index for index, place in enumerate(day.places) if place.mealType == "LUNCH")
    scenic_index = next(index for index, place in enumerate(day.places) if place.sourcePoiId == "scenic")
    assert lunch_index < scenic_index

def test_road_matrix_preserves_night_visit_window() -> None:
    class FakeMatrixRouteService:
        async def road_time_matrix(self, places):
            return {
                (origin.id, destination.id): (10, 1000)
                for origin in places
                for destination in places
                if origin.id != destination.id
            }

    service = TravelPlanGenerationService(
        object(),
        object(),
        FakeMatrixRouteService(),
        reveal_delay_seconds=0,
    )
    museum = _ai_review_place("museum", "scenic", "10:00", "11:30").model_copy(
        update={
            "name": "上海历史博物馆",
            "typeName": "博物馆",
            "openingHoursWeek": "周一至周日 09:00-17:00",
        },
    )
    bund = _ai_review_place("bund", "scenic", "17:30", "19:00").model_copy(
        update={
            "name": "上海外滩",
            "typeName": "城市夜景",
            "openingHoursWeek": "24小时营业",
        },
    )

    reordered = asyncio.run(
        service._reorder_day_with_road_matrix(
            AiPlanGenerationRequest(
                destination="上海",
                dateRange="2026.07.23",
                dayCount=1,
                dailyStart="09:00",
                dailyEnd="21:30",
            ),
            1,
            [bund, museum],
            None,
        ),
    )

    assert [place.sourcePoiId for place in reordered] == ["museum", "bund"]
    assert reordered[-1].suggestedStart >= "17:30"


def test_default_beijing_landmark_stays_before_dinner() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    scenic = [
        PlaceSummary(
            id="museum", sourcePoiId="museum", name="北京历史博物馆", category="scenic",
            categoryCode="scenic", latitude=39.91, longitude=116.40,
            openingHoursWeek="周一至周日 09:00-17:00",
        ),
        PlaceSummary(
            id="square", sourcePoiId="square", name="天安门广场", category="scenic",
            categoryCode="scenic", latitude=39.903, longitude=116.397,
            openingHoursWeek="周一至周日 05:00-22:00",
        ),
    ]
    foods = [
        PlaceSummary(
            id=f"meal-{index}", sourcePoiId=f"meal-{index}", name=name,
            category="food", categoryCode="food",
            latitude=39.904 + index * 0.001, longitude=116.398 + index * 0.001,
            openingHoursWeek="周一至周日 07:00-23:00",
        )
        for index, name in enumerate(("北京特色早餐铺", "北京地方午餐馆", "北京烤鸭晚餐馆"))
    ]

    day = service._build_heuristic_days(
        AiPlanGenerationRequest(
            destination="北京", dateRange="2026.07.25", dayCount=1,
            dailyStart="08:00", dailyEnd="21:00",
        ),
        scenic + foods,
        city_name="北京市",
    )[0]

    square_index = next(index for index, place in enumerate(day.places) if place.sourcePoiId == "square")
    dinner_index = next(index for index, place in enumerate(day.places) if place.mealType == "DINNER")
    assert square_index < dinner_index


def test_generic_square_requires_night_request_and_sufficient_window() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    square = PlaceSummary(
        id="square", sourcePoiId="square", name="天安门广场", category="scenic",
        categoryCode="scenic", latitude=39.903, longitude=116.397,
        openingHoursWeek="周一至周日 05:00-22:00",
    )
    default_request = AiPlanGenerationRequest(
        destination="北京", dateRange="2026.07.25", dayCount=1, dailyEnd="22:00",
    )
    night_request = default_request.model_copy(update={"freeText": "晚上想看天安门夜景"})

    assert service._is_night_experience_candidate(square, default_request, 1) is False
    assert service._is_night_experience_candidate(square, night_request, 1) is True

    short_window = square.model_copy(
        update={"name": "城市中心广场", "openingHoursWeek": "周一至周日 17:45-19:00"},
    )
    assert service._supports_evening_visit(short_window, night_request, 1) is False


def test_indoor_place_with_square_in_branch_name_is_not_assumed_open_at_night() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    museum = PlaceSummary(
        id="museum", sourcePoiId="museum", name="上海博物馆(人民广场馆)",
        category="scenic", categoryCode="scenic", typeName="博物馆",
        latitude=31.23, longitude=121.47,
    )
    request = AiPlanGenerationRequest(
        destination="上海", dateRange="2026.07.25", dayCount=1,
        freeText="晚上也可以安排活动", dailyEnd="22:00",
    )

    assert service._supports_evening_visit(museum, request, 1) is False
    assert service._is_night_experience_candidate(museum, request, 1) is False


def test_actual_route_replay_preserves_confirmed_night_visit_window() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.23",
        dayCount=1,
        dailyStart="09:00",
        dailyEnd="22:00",
    )
    night_place = _ai_review_place("tiantan", "scenic", "17:30", "19:00").model_copy(
        update={
            "name": "天坛公园",
            "typeName": "公园广场",
            "openingHoursWeek": "周一至周日 06:00-22:00 最晚进入21:00",
        },
    )

    fitted = service._fit_place_after_route(
        request,
        night_place,
        day_index=1,
        earliest=15 * 60,
    )

    assert fitted is not None
    assert fitted.suggestedStart == "17:30"
    assert fitted.suggestedEnd == "19:00"


def test_adverse_or_hot_weather_requests_indoor_candidate_recall() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)

    assert service._weather_needs_indoor_recall(
        AmapWeatherForecastDay("2026-07-23", "晴", "晴", "36", "29"),
    )
    assert service._weather_needs_indoor_recall(
        AmapWeatherForecastDay("2026-07-23", "中雨", "小雨", "28", "24"),
    )
    assert not service._weather_needs_indoor_recall(
        AmapWeatherForecastDay("2026-07-23", "多云", "晴", "29", "22"),
    )

def test_seasonal_weekly_hours_use_only_the_trip_date_segment() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    place = PlaceSummary(
        id="museum",
        sourcePoiId="museum",
        name="上海博物馆(人民广场馆)",
        category="scenic",
        categoryCode="scenic",
        typeName="博物馆",
        latitude=31.23,
        longitude=121.47,
        openingHoursWeek=(
            "9月至12月 周二至周五 09:00-17:00 最晚进入15:00；"
            "07-09至08-31 周二至周五 09:00-21:00 最晚进入19:00；"
            "01-01至07-08 周二至周五 09:00-17:00 最晚进入15:00；"
            "周一 全天关闭"
        ),
    )
    request = AiPlanGenerationRequest(
        destination="上海",
        dateRange="2026.07.24",
        dayCount=1,
        dailyEnd="21:30",
    )

    windows = service._opening_windows_for_day(place, request, 1)

    assert [(window.start, window.end, window.latest_start) for window in windows] == [
        (9 * 60, 21 * 60, 19 * 60),
    ]
    assert service._find_open_slot(windows, 19 * 60 + 5, 90) is None


def test_indoor_museum_branch_name_does_not_become_night_landmark_from_square_word() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    museum = PlaceSummary(
        id="museum",
        sourcePoiId="museum",
        name="上海博物馆(人民广场馆)",
        category="scenic",
        categoryCode="scenic",
        typeName="博物馆",
        latitude=31.23,
        longitude=121.47,
        rating="4.8",
    )

    assert service._night_experience_score(museum) < 24.0


def test_plan_quality_reports_real_route_comfort_risks() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.23",
        dayCount=1,
        pace="BALANCED",
        freeText="必去故宫",
    )
    first = _ai_review_place("forbidden", "scenic", "09:00", "11:00").model_copy(
        update={"name": "故宫", "districtName": "东城区"},
    )
    second = _ai_review_place("summer", "scenic", "13:30", "15:30").model_copy(
        update={"name": "颐和园", "districtName": "海淀区"},
    )
    day = AiGeneratedDay(
        dayIndex=1,
        title="DAY 1",
        summary="",
        places=[first, second],
        transfers=[
            AiGeneratedTransfer(
                originPlaceId=first.id,
                destinationPlaceId=second.id,
                mode="transit",
                distanceMeters=18000,
                durationMinutes=70,
            ),
        ],
    )

    quality = service._evaluate_plan_quality(request, [day], False, ["AMAP"])

    assert quality.totalCommuteMinutes == 70
    assert quality.longestLegMinutes == 70
    assert quality.crossRegionTransferCount == 1
    assert quality.longIdleGapCount == 1
    assert quality.requiredPlaceCoverage == 1.0
    assert quality.comfortScore < 100


def test_beijing_first_visit_landmarks_outrank_generic_high_rated_scenic() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    request = AiPlanGenerationRequest(
        destination="北京",
        dateRange="2026.07.26",
        dayCount=1,
        pace="BALANCED",
    )
    palace = PlaceSummary(
        id="palace", sourcePoiId="palace", name="故宫博物院", category="scenic", categoryCode="scenic",
        latitude=39.916, longitude=116.397, rating="4.7", openingHoursWeek="周二至周日 08:30-17:00",
    )
    square = PlaceSummary(
        id="square", sourcePoiId="square", name="天安门广场", category="scenic", categoryCode="scenic",
        latitude=39.904, longitude=116.397, rating="4.6", openingHoursWeek="周一至周日 05:00-22:00",
    )
    generic = PlaceSummary(
        id="generic", sourcePoiId="generic", name="城市文化体验园", category="scenic", categoryCode="scenic",
        latitude=39.908, longitude=116.402, rating="5.0", openingHoursWeek="周一至周日 09:00-20:00",
    )

    selected = service._select_time_window_scenic(
        request,
        [generic, square, palace],
        day_index=1,
        target=2,
        weather=None,
        start_anchor=None,
        end_anchor=None,
    )

    assert {place.sourcePoiId for place in selected} == {"palace", "square"}
    assert service._is_first_visit_core_landmark(palace) is True
    assert service._is_first_visit_core_landmark(square) is True
    assert service._should_protect_core_landmark(request, palace) is True
    assert service._should_protect_core_landmark(request, square) is True

    monday_request = request.model_copy(update={"dateRange": "2026.07.27"})
    monday_selected = service._select_time_window_scenic(
        monday_request,
        [generic, square, palace],
        day_index=1,
        target=2,
        weather=None,
        start_anchor=None,
        end_anchor=None,
    )
    assert "palace" not in {place.sourcePoiId for place in monday_selected}
    assert "square" in {place.sourcePoiId for place in monday_selected}


def test_low_crowd_preference_overrides_default_landmark_protection() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    square = PlaceSummary(
        id="square", sourcePoiId="square", name="天安门广场", category="scenic", categoryCode="scenic",
        latitude=39.904, longitude=116.397, rating="4.8", crowdRisk=0.9,
        openingHoursWeek="周一至周日 05:00-22:00",
    )
    palace = PlaceSummary(
        id="palace", sourcePoiId="palace", name="故宫博物院", category="scenic", categoryCode="scenic",
        latitude=39.916, longitude=116.397, rating="4.8", crowdRisk=0.9,
        openingHoursWeek="周二至周日 08:30-17:00",
    )
    quiet_place = PlaceSummary(
        id="quiet", sourcePoiId="quiet", name="史家胡同社区旧址", category="scenic", categoryCode="scenic",
        latitude=39.914, longitude=116.416, rating="4.4", crowdRisk=0.1,
        openingHoursWeek="周一至周日 09:00-18:00",
    )
    niche_request = AiPlanGenerationRequest(
        destination="北京", dateRange="2026.07.28", dayCount=1, preferences=["小众探索"],
    )

    assert service._should_protect_core_landmark(niche_request, square) is False
    assert (
        service._candidate_score(niche_request, quiet_place, None, None).total
        > service._candidate_score(niche_request, square, None, None).total
    )

    mixed_request = niche_request.model_copy(update={"preferences": ["经典必玩", "小众探索"]})
    assert service._should_protect_core_landmark(mixed_request, palace) is True
    assert service._should_protect_core_landmark(mixed_request, square) is False

    explicit_request = niche_request.model_copy(
        update={"freeText": "天安门必去，其他地点希望偏冷门人少"},
    )
    assert service._should_protect_core_landmark(explicit_request, square) is True


def test_tiananmen_complex_is_deduped_and_keeps_canonical_square() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    tower = PlaceSummary(
        id="tower", sourcePoiId="tower", name="天安门城楼", category="scenic", categoryCode="scenic",
        latitude=39.9087, longitude=116.3975, rating="4.8",
    )
    square = PlaceSummary(
        id="square", sourcePoiId="square", name="天安门广场", category="scenic", categoryCode="scenic",
        latitude=39.9033, longitude=116.3976, rating="4.7",
        imageUrls=["https://img.example/square.jpg"],
    )

    deduped = service._dedupe_candidates([tower, square])

    assert [place.name for place in deduped] == ["天安门广场"]


def test_nearby_meal_recall_prefers_local_keyword_then_falls_back() -> None:
    class FakePoiService:
        def __init__(self) -> None:
            self.keywords: list[str | None] = []

        async def search_nearby_pois(self, **kwargs):
            self.keywords.append(kwargs["keyword"])
            if kwargs["keyword"] is not None:
                return []
            return [
                PlaceSummary(
                    id="meal",
                    sourcePoiId="meal",
                    name="顺路本帮菜",
                    category="food",
                    categoryCode="food",
                    latitude=31.23,
                    longitude=121.47,
                ),
            ]

    poi_service = FakePoiService()
    service = TravelPlanGenerationService(object(), poi_service, reveal_delay_seconds=0)
    previous = _ai_review_place("a", "scenic", "10:00", "11:30").model_copy(
        update={"adCode": "310101"},
    )
    following = _ai_review_place("b", "scenic", "13:00", "14:30").model_copy(
        update={"adCode": "310101"},
    )

    result = asyncio.run(
        service._nearby_meal_candidates(previous, following, "LUNCH", "上海"),
    )

    assert poi_service.keywords == ["本帮菜", None]
    assert [place.name for place in result] == ["顺路本帮菜"]

def test_local_food_score_recognizes_city_name_and_cuisine_terms() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    local = PlaceSummary(
        id="local",
        sourcePoiId="local",
        name="老上海本帮菜",
        category="food",
        categoryCode="food",
        latitude=31.23,
        longitude=121.47,
    )
    nonlocal_food = local.model_copy(
        update={"id": "other", "sourcePoiId": "other", "name": "印度餐厅"},
    )

    assert service._local_food_score("上海市", local) > service._local_food_score(
        "上海市",
        nonlocal_food,
    )
