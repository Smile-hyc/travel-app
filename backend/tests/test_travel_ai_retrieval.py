import asyncio

from app.schemas.ai import AiChatRequest, AiDayContext, AiHistoryMessage, AiPlaceContext, AiPlanContext
from app.schemas.explore import CitySearchResult, PaginatedPlaces, PlaceSummary
from app.services.travel_ai_service import TravelAiService


class FakeModelClient:
    model_name = "deepseek-test"

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages, **kwargs):
        self.calls.append(messages)
        if "旅行检索规划器" in messages[0]["content"]:
            question = messages[-1]["content"]
            if "夏天旅行" in question:
                return '{"search":false}'
            if "两日游" in question:
                return (
                    '{"search":true,"city":"天津","queries":['
                    '{"category":"scenic","keyword":"天津经典景点"},'
                    '{"category":"food","keyword":"天津特色美食"}]}'
                )
            return '{"search":true,"city":"天津","category":"food","keywords":["天津特色小吃"]}'
        if "两日游" in messages[-1]["content"]:
            return "交给智能规划前，可以优先考虑 **耳朵眼会馆**。"
        return "天津小吃很有地方特色，可以去耳朵眼会馆品尝传统风味。"


class FakePoiService:
    def __init__(self) -> None:
        self.search_count = 0

    async def search_cities(self, *, keyword: str, limit: int):
        assert keyword == "天津"
        return [
            CitySearchResult(
                id="amap-city:120000:天津市",
                name="天津市",
                adCode="120000",
                latitude=39.12,
                longitude=117.20,
            ),
        ]

    async def search_pois(self, **kwargs):
        self.search_count += 1
        return PaginatedPlaces(
            items=[
                PlaceSummary(
                    id="amap:B001",
                    sourcePoiId="B001",
                    name="耳朵眼会馆",
                    category="food",
                    categoryCode="food",
                    typeName="中餐厅",
                    address="鼓楼商业街",
                    cityName="天津市",
                    districtName="南开区",
                    latitude=39.14,
                    longitude=117.18,
                    rating="4.7",
                    costAverage="88",
                    coverImageUrl="https://example.com/place.jpg",
                ),
            ],
            page=1,
            pageSize=6,
            total=1,
            hasMore=False,
        )


def test_chat_enriches_place_question_with_amap_links_and_cards() -> None:
    model = FakeModelClient()
    poi_service = FakePoiService()
    service = TravelAiService(model, poi_service)

    response = asyncio.run(service.chat(AiChatRequest(message="天津有什么小吃推荐？")))

    assert "[耳朵眼会馆](aitravel://place/amap:B001)" in response.message
    assert response.retrievalCity == "天津市"
    assert response.offerPlan is True
    assert response.dataSources == ["DEEPSEEK", "AMAP"]
    assert len(response.recommendedPlaces) == 1
    assert response.recommendedPlaces[0].id == "amap:B001"
    assert response.recommendedPlaces[0].rating == "4.7"
    assert poi_service.search_count == 1


def test_chat_keeps_non_place_question_as_plain_travel_conversation() -> None:
    model = FakeModelClient()
    poi_service = FakePoiService()
    service = TravelAiService(model, poi_service)

    response = asyncio.run(service.chat(AiChatRequest(message="夏天旅行需要带什么？")))

    assert response.recommendedPlaces == []
    assert response.offerPlan is False
    assert response.dataSources == ["DEEPSEEK"]
    assert poi_service.search_count == 0
    assert len(model.calls) == 2


def test_multiday_plan_request_retrieves_places_and_converts_bold_name_to_link() -> None:
    model = FakeModelClient()
    poi_service = FakePoiService()
    service = TravelAiService(model, poi_service)

    response = asyncio.run(service.chat(AiChatRequest(message="我想安排一个天津两日游")))

    assert "[耳朵眼会馆](aitravel://place/amap:B001)" in response.message
    assert "**[耳朵眼会馆]" not in response.message
    assert response.retrievalCity == "天津市"
    assert len(response.recommendedPlaces) == 1
    assert poi_service.search_count == 2


def test_followup_uses_previous_city_when_current_question_only_names_business_area() -> None:
    model = FakeModelClient()
    poi_service = FakePoiService()
    service = TravelAiService(model, poi_service)

    response = asyncio.run(
        service.chat(
            AiChatRequest(
                message="推荐西北角附近的美食店铺",
                history=[
                    AiHistoryMessage(role="user", content="我准备去天津玩"),
                    AiHistoryMessage(role="assistant", content="天津有很多值得探索的地方。"),
                ],
            ),
        ),
    )

    planner_input = model.calls[0][-1]["content"]
    assert "我准备去天津玩" in planner_input
    assert "current_user: 推荐西北角附近的美食店铺" in planner_input
    assert "[耳朵眼会馆](aitravel://place/amap:B001)" in response.message
    assert response.recommendedPlaces[0].coverImageUrl == "https://example.com/place.jpg"


def test_linkify_keeps_one_link_when_bold_line_or_plain_name_duplicates_it() -> None:
    service = TravelAiService(FakeModelClient(), FakePoiService())
    target = PlaceSummary(
        id="amap:B001",
        sourcePoiId="B001",
        name="耳朵眼会馆",
        category="food",
        categoryCode="food",
        latitude=39.14,
        longitude=117.18,
    )
    markdown = "[耳朵眼会馆](aitravel://place/amap:B001)"

    result = service._linkify_places(
        f"**1. {markdown}**\n**耳朵眼会馆** (aitravel://place/amap:B001) {markdown}\n{markdown} {markdown}",
        [target],
    )

    assert result == f"1. {markdown}\n{markdown}\n{markdown}"


def test_every_chat_request_includes_all_plan_page_contexts() -> None:
    service = TravelAiService(FakeModelClient(), None)
    plans = [
        AiPlanContext(
            id="shanghai-plan",
            title="上海一日游",
            destination="上海",
            dateRange="07.23 - 07.23",
            currentDate="2026-07-23",
            todayDayIndex=1,
            days=[
                AiDayContext(
                    dayIndex=1,
                    title="上海城市漫步",
                    places=[AiPlaceContext(itemId="p1", name="外滩", visitOrder=1)],
                )
            ],
        ),
        AiPlanContext(
            id="tianjin-plan",
            title="天津周末游",
            destination="天津",
            dateRange="07.26 - 07.27",
            currentDate="2026-07-23",
            days=[AiDayContext(dayIndex=1, title="天津古文化街")],
        ),
    ]

    messages = service._build_messages(
        AiChatRequest(
            message="我的计划里有哪些行程？",
            planId="shanghai-plan",
            context=plans[0],
            planContexts=plans,
        )
    )
    all_plans_prompt = messages[1]["content"]

    assert "计划页面中的全部旅行计划" in all_plans_prompt
    assert "上海一日游" in all_plans_prompt
    assert "外滩" in all_plans_prompt
    assert "天津周末游" in all_plans_prompt
    assert "天津古文化街" in all_plans_prompt


def test_plan_places_become_valid_links_and_unknown_links_are_not_clickable() -> None:
    service = TravelAiService(FakeModelClient(), None)
    context = AiPlanContext(
        id="shanghai-plan",
        title="上海一日游",
        days=[
            AiDayContext(
                dayIndex=1,
                places=[AiPlaceContext(itemId="amap:PLAN001", name="外滩")],
            )
        ],
    )

    result = service._linkify_places(
        "外滩和[不存在地点](aitravel://place/amap:UNKNOWN)",
        [],
        [context],
    )

    assert result == "[外滩](aitravel://place/amap:PLAN001)和不存在地点"


def test_recommendation_rank_prioritizes_famous_city_landmark() -> None:
    service = TravelAiService(FakeModelClient(), FakePoiService())
    famous = PlaceSummary(
        id="famous", sourcePoiId="famous", name="五大道文化旅游区",
        category="scenic", categoryCode="scenic", cityName="天津市",
        latitude=39.12, longitude=117.20, rating="4.6",
    )
    generic = PlaceSummary(
        id="generic", sourcePoiId="generic", name="城市景观体验馆",
        category="scenic", categoryCode="scenic", cityName="天津市",
        latitude=39.13, longitude=117.21, rating="5.0", coverImageUrl="https://example.com/generic.jpg",
    )

    assert service._recommendation_rank(famous, "天津市", 1) > service._recommendation_rank(
        generic, "天津市", 0,
    )
