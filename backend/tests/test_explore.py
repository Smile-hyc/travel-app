from fastapi.testclient import TestClient

from app.api import explore as explore_api
from app.main import app
from app.schemas.explore import ExploreWeather

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
