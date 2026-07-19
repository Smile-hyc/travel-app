from fastapi.testclient import TestClient

from app.api import explore as explore_api
from app.main import app
from app.core.config import Settings
from app.schemas.explore import ExploreWeather, PlaceDetail, PlaceSummary, ReviewSource
from app.services.place_detail_service import PlaceDetailService
from app.services.rnote_review_client import RnoteReviewClient, _parse_search_results
from app.services.tikhub_review_client import TikhubReviewClient, _find_note_candidates, _parse_note

client = TestClient(app)


def test_amap_health_does_not_expose_key() -> None:
    response = client.get("/api/health/amap")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"configured", "webServiceKeyConfigured"}
    assert isinstance(payload["configured"], bool)
    assert isinstance(payload["webServiceKeyConfigured"], bool)


def test_input_tips_short_keyword_returns_empty_list() -> None:
    response = client.get("/api/explore/input-tips", params={"keyword": "广", "adcode": "440100"})

    assert response.status_code == 200
    assert response.json() == []


def test_weather_endpoint_returns_simplified_shape(monkeypatch) -> None:
    class FakeWeatherService:
        async def get_city_weather(self, *, adcode: str) -> ExploreWeather:
            assert adcode == "120100"
            return ExploreWeather(
                city="天津市",
                adCode="120000",
                weather="晴",
                dayTemp="33",
                nightTemp="24",
                text="晴 24°-33°",
                reportTime="2026-07-15 11:00:00",
            )

    monkeypatch.setattr(explore_api, "get_amap_weather_service", lambda: FakeWeatherService())

    response = client.get("/api/explore/weather", params={"adcode": "120100"})

    assert response.status_code == 200
    assert response.json() == {
        "city": "天津市",
        "adCode": "120000",
        "weather": "晴",
        "dayTemp": "33",
        "nightTemp": "24",
        "text": "晴 24°-33°",
        "reportTime": "2026-07-15 11:00:00",
    }


def _sample_place() -> PlaceSummary:
    return PlaceSummary(
        id="amap:B001",
        sourcePoiId="B001",
        name="杨柳青民俗文化馆",
        category="scenic",
        categoryCode="110000",
        typeName="文化场馆",
        address="杨柳青镇估衣街47号",
        cityName="天津市",
        districtName="西青区",
        latitude=39.14,
        longitude=117.01,
        rating="4.7",
    )


def test_place_detail_without_review_key_uses_honest_fallback() -> None:
    import asyncio

    service = PlaceDetailService(TikhubReviewClient(Settings(tikhub_api_key="")))
    detail = asyncio.run(service.get_detail(_sample_place()))

    assert detail.reviewTitle == "地点亮点"
    assert detail.hasRealReviews is False
    assert detail.reviewSources == []
    assert detail.sourceLabels == []
    assert detail.positiveHighlights[0].title == "公开评分"
    assert detail.openingHours is None


def test_tikhub_parser_handles_nested_app_v2_cards() -> None:
    payload = {
        "data": {
            "items": [
                {
                    "id": "note-1",
                    "note_card": {
                        "note_id": "note-1",
                        "display_title": "天津杨柳青民俗文化馆参观攻略",
                        "desc": "建筑很有特色，适合拍照。",
                        "user": {"nickname": "旅行者"},
                    },
                }
            ]
        }
    }

    candidates = _find_note_candidates(payload)
    assert len(candidates) == 1
    source = _parse_note(candidates[0])
    assert source is not None
    assert source.id == "xiaohongshu:note-1"
    assert source.author == "旅行者"
    assert source.url == "https://www.xiaohongshu.com/explore/note-1"


def test_rnote_parser_handles_wrapped_search_response_and_rich_fields() -> None:
    payload = {
        "success": True,
        "billed": True,
        "data": {
            "data": {
                "items": [
                    {
                        "id": "note-r1",
                        "xsec_token": "token value",
                        "note_card": {
                            "note_id": "note-r1",
                            "display_title": "天津杨柳青民俗文化馆游览记录",
                            "desc": "建筑古朴，很适合了解杨柳青年画文化。",
                            "user": {"nickname": "天津旅行日记"},
                            "cover": {"url_default": "https://example.com/cover.jpg"},
                            "interact_info": {"liked_count": "128"},
                        },
                    }
                ]
            }
        },
    }

    sources = _parse_search_results(payload, place=_sample_place(), limit=3)

    assert len(sources) == 1
    source = sources[0]
    assert source.provider == "Rnote API"
    assert source.coverImageUrl == "https://example.com/cover.jpg"
    assert source.likeCount == "128"
    assert source.author == "天津旅行日记"
    assert "xsec_token=token+value" in source.url


def test_rnote_configuration_takes_priority_over_tikhub() -> None:
    settings = Settings(rnote_api_key="rnote-key", tikhub_api_key="tikhub-key")

    assert RnoteReviewClient(settings).configured is True
    assert settings.active_review_provider == "rnote"


def test_place_detail_endpoint_preserves_traceable_sources(monkeypatch) -> None:
    class FakeDetailService:
        async def get_detail(self, place: PlaceSummary) -> PlaceDetail:
            return PlaceDetail(
                summary=place,
                description="地点介绍",
                reviewTitle="真实评价",
                hasRealReviews=True,
                sourceLabels=["小红书"],
                reviewSources=[
                    ReviewSource(
                        id="xiaohongshu:note-1",
                        platform="小红书",
                        title="真实用户笔记",
                        url="https://www.xiaohongshu.com/explore/note-1",
                    )
                ],
            )

    monkeypatch.setattr(explore_api, "get_place_detail_service", lambda: FakeDetailService())
    response = client.post("/api/explore/pois/detail", json=_sample_place().model_dump())

    assert response.status_code == 200
    payload = response.json()
    assert payload["hasRealReviews"] is True
    assert payload["reviewSources"][0]["platform"] == "小红书"
    assert payload["reviewSources"][0]["url"].endswith("note-1")
