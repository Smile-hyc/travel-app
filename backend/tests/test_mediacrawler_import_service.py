import asyncio
import json

import pytest

from app.review_store import ReviewStore
from app.schemas.explore import PlaceSummary
from app.services.mediacrawler_import_service import (
    MediaCrawlerImportError,
    MediaCrawlerImportService,
)
from app.services.place_detail_service import PlaceDetailService


class FakeCatalog:
    async def discover_city(self, city_name, limit=25):
        return []

    async def resolve(self, seeds):
        place = PlaceSummary(
            id="amap:TJ001",
            sourcePoiId="TJ001",
            name="天津五大道文化旅游区",
            category="scenic",
            categoryCode="110000",
            cityName="天津市",
        )
        return [(seeds[0], place)], []


class DisabledReviewClient:
    configured = False


def test_mediacrawler_jsonl_is_cleaned_and_imported(tmp_path) -> None:
    export = tmp_path / "search_contents_2026-07-22.jsonl"
    rows = [
        {
            "note_id": f"n{index}",
            "title": f"天津五大道拍照攻略 {index}",
            "desc": "五大道很出片，周末排队，建议步行游览。",
            "note_url": f"https://www.xiaohongshu.com/explore/n{index}",
            "creator_hash": f"creator-{index}",
            "source_keyword": "天津五大道文化旅游区",
            "time": 1_752_000_000_000,
        }
        for index in range(3)
    ]
    export.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows), encoding="utf-8")
    store = ReviewStore(":memory:")
    service = MediaCrawlerImportService(
        FakeCatalog(),
        PlaceDetailService(DisabledReviewClient(), store=store, author_hash_salt="test"),
        data_root=tmp_path,
    )

    result = asyncio.run(service.import_export(file_name=export.name, city_name="天津市"))

    assert result["rowCount"] == 3
    assert result["acceptedCount"] == 3
    assert store.get_aggregate("TJ001")["status"] == "READY"
    assert len(store.list_active_evidence("TJ001")) == 3
    store.close()


def test_mediacrawler_import_rejects_path_traversal(tmp_path) -> None:
    service = MediaCrawlerImportService(
        FakeCatalog(),
        PlaceDetailService(DisabledReviewClient()),
        data_root=tmp_path,
    )
    with pytest.raises(MediaCrawlerImportError):
        asyncio.run(service.import_export(file_name="../secret.jsonl", city_name="天津市"))
