import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.schemas.explore import PlaceSummary
from app.services.tikhub_review_client import ReviewProviderError, TikhubReviewClient


def _place() -> PlaceSummary:
    return PlaceSummary(
        id="amap:B001",
        sourcePoiId="B001",
        name="故宫博物院",
        category="scenic",
        categoryCode="110000",
        cityName="北京市",
    )


def _client(handler) -> TikhubReviewClient:
    settings = Settings(
        tikhub_api_key="test",
        ugc_provider_authorized=True,
        tikhub_base_url="https://provider.example",
    )
    client = TikhubReviewClient(settings)
    client._client = httpx.AsyncClient(
        base_url="https://provider.example",
        transport=httpx.MockTransport(handler),
    )
    return client


def test_contract_sends_popularity_search_and_parses_notes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search_notes")
        assert request.url.params["sort_type"] == "popularity_descending"
        assert request.headers["Authorization"] == "Bearer test"
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "note_card": {
                                "note_id": "n1",
                                "display_title": "北京故宫博物院参观攻略",
                                "desc": "故宫拍照机位很多，很值得。",
                                "user": {"nickname": "旅行者"},
                            },
                        },
                    ],
                },
            },
        )

    client = _client(handler)
    try:
        notes = asyncio.run(client.search_place(_place()))
        assert len(notes) == 1
        assert notes[0].relevanceScore is not None
        assert notes[0].relevanceScore >= 0.7
    finally:
        asyncio.run(client.aclose())


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "AUTH_ERROR"), (402, "QUOTA_EXHAUSTED"), (429, "RATE_LIMITED"), (503, "UPSTREAM_ERROR")],
)
def test_contract_keeps_provider_errors_distinct_from_empty_results(status: int, kind: str) -> None:
    client = _client(lambda request: httpx.Response(status, request=request))
    try:
        with pytest.raises(ReviewProviderError) as captured:
            asyncio.run(client.search_place(_place()))
        assert captured.value.kind == kind
        assert captured.value.status_code == status
    finally:
        asyncio.run(client.aclose())
