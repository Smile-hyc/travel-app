import asyncio
import json
from pathlib import Path

from app.review_store import ReviewStore
from app.schemas.explore import CitySearchResult, PlaceSummary
from app.services.city_content_pipeline import CityContentPipelineService
from app.services.mediacrawler_import_service import MediaCrawlerImportService
from app.services.mediacrawler_runner import (
    MediaCrawlerRunError,
    MediaCrawlerRunResult,
    _is_captcha_interruption,
    _is_login_interruption,
    _is_network_interruption,
)
from app.services.place_detail_service import PlaceDetailService


class DisabledReviewClient:
    configured = False


class FakeCatalog:
    def __init__(self, places):
        self.places = places

    async def resolve_city(self, city_name):
        return CitySearchResult(
            id="amap-city:120000",
            name="天津市",
            provinceName="天津市",
            adCode="120000",
            latitude=39.1,
            longitude=117.2,
        )

    async def discover_city(self, city_name, limit=12):
        return self.places[:limit]


class FakeRunner:
    def __init__(self, run_root: Path):
        self.run_root = run_root
        self.calls = 0

    async def run(self, *, run_id, city_name, items, candidate_limit, headless):
        self.calls += 1
        export = self.run_root / run_id / "xhs" / "jsonl" / "search_contents_test.jsonl"
        export.parent.mkdir(parents=True)
        rows = []
        for item in items:
            for index in range(25):
                rows.append(
                    {
                        "note_id": f"{item['poi_id']}-{index}",
                        "title": f"天津 {item['place_name']} 拍照攻略 {index}",
                        "desc": f"天津 {item['place_name']} 很出片，建议步行游览。",
                        "source_keyword": item["query_keyword"],
                        "time": 1_752_000_000_000 + index,
                    },
                )
        rows.append(
            {
                "note_id": "unmatched",
                "title": "不属于清单的内容",
                "desc": "不应进入任何地点数据库",
                "source_keyword": "天津 不存在的地点 攻略",
            },
        )
        export.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in rows),
            encoding="utf-8",
        )
        log = export.parents[3] / "crawler.log"
        log.write_text("ok", encoding="utf-8")
        return MediaCrawlerRunResult(export, log, 0)


class LoginRequiredRunner:
    async def run(self, **kwargs):
        raise MediaCrawlerRunError("LOGIN_REQUIRED: scan QR code")


class PartialRunner(FakeRunner):
    async def run(self, *, run_id, city_name, items, candidate_limit, headless):
        result = await super().run(
            run_id=run_id,
            city_name=city_name,
            items=items[:1],
            candidate_limit=candidate_limit,
            headless=headless,
        )
        return MediaCrawlerRunResult(result.export_path, result.log_path, 1)


class PartialLoginRunner(FakeRunner):
    async def run(self, *, run_id, city_name, items, candidate_limit, headless):
        result = await super().run(
            run_id=run_id,
            city_name=city_name,
            items=items[:1],
            candidate_limit=candidate_limit,
            headless=headless,
        )
        return MediaCrawlerRunResult(result.export_path, result.log_path, 460)


class InsufficientRunner(FakeRunner):
    async def run(self, *, run_id, city_name, items, candidate_limit, headless):
        self.calls += 1
        export = self.run_root / run_id / "xhs" / "jsonl" / "search_contents_test.jsonl"
        export.parent.mkdir(parents=True)
        rows = [
            {
                "note_id": f"irrelevant-{item['poi_id']}-{index}",
                "title": "与景点无关的测试内容",
                "desc": "没有地点体验信息",
                "source_keyword": item["query_keyword"],
            }
            for item in items
            for index in range(25)
        ]
        export.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in rows),
            encoding="utf-8",
        )
        log = export.parents[3] / "crawler.log"
        log.write_text("ok", encoding="utf-8")
        return MediaCrawlerRunResult(export, log, 0)


class NetworkUnavailableRunner:
    async def run(self, **kwargs):
        raise MediaCrawlerRunError("NETWORK_UNAVAILABLE: temporary outage")


def _place(poi_id: str, name: str, rating: str) -> PlaceSummary:
    return PlaceSummary(
        id=f"amap:{poi_id}",
        sourcePoiId=poi_id,
        name=name,
        category="scenic",
        categoryCode="110000",
        provinceName="天津市",
        cityName="天津市",
        districtName="和平区",
        adCode="120101",
        rating=rating,
    )


def test_city_pipeline_binds_queries_and_caps_retained_evidence(tmp_path) -> None:
    store = ReviewStore(":memory:")
    detail = PlaceDetailService(DisabledReviewClient(), store=store, author_hash_salt="test")
    places = [_place("TJ001", "民园广场", "4.8"), _place("TJ002", "五大道", "4.7")]
    run_root = tmp_path / "runs"
    importer = MediaCrawlerImportService(
        FakeCatalog(places),
        detail,
        data_root=tmp_path / "exports",
        run_root=run_root,
    )
    runner = FakeRunner(run_root)
    pipeline = CityContentPipelineService(
        FakeCatalog(places),
        detail,
        importer,
        runner,
        store,
    )

    result = asyncio.run(
        pipeline.run_city_and_wait("天津市", top=2, candidate_limit=30, headless=True),
    )

    assert result["status"] == "ready"
    assert result["target_count"] == 2
    assert result["fetched_count"] == 50
    assert result["accepted_count"] == 40
    assert [item["status"] for item in result["items"]] == ["ready", "ready"]
    for place in places:
        assert len(store.list_active_evidence(place.sourcePoiId)) == 20
        detail_result = asyncio.run(detail.get_detail(place))
        assert len(detail_result.reviewSources) == 8
        assert all("unmatched" not in source.id for source in detail_result.reviewSources)
    ranking = store.get_city_ranking("120000")
    assert [item["poi_id"] for item in ranking] == ["TJ001", "TJ002"]
    assert ranking[0]["crawler_keyword"] == "天津 民园广场 攻略"
    cached = asyncio.run(
        pipeline.run_city_and_wait("天津市", top=2, candidate_limit=30, headless=True),
    )
    assert cached["status"] == "ready"
    assert cached["target_count"] == 0
    assert runner.calls == 1
    store.close()


def test_city_pipeline_limits_each_collection_batch_without_marking_others_done(tmp_path) -> None:
    store = ReviewStore(":memory:")
    detail = PlaceDetailService(DisabledReviewClient(), store=store, author_hash_salt="test")
    places = [_place("TJ001", "民园广场", "4.8"), _place("TJ002", "五大道", "4.7")]
    run_root = tmp_path / "runs"
    runner = FakeRunner(run_root)
    pipeline = CityContentPipelineService(
        FakeCatalog(places),
        detail,
        MediaCrawlerImportService(
            FakeCatalog(places), detail, data_root=tmp_path / "exports", run_root=run_root,
        ),
        runner,
        store,
    )

    first = asyncio.run(
        pipeline.run_city_and_wait("天津市", top=2, max_targets=1, candidate_limit=30),
    )
    second = asyncio.run(
        pipeline.run_city_and_wait("天津市", top=2, max_targets=1, candidate_limit=30),
    )

    assert first["target_count"] == 1
    assert second["target_count"] == 1
    assert first["items"][0]["poi_id"] == "TJ001"
    assert second["items"][0]["poi_id"] == "TJ002"
    assert runner.calls == 2
    store.close()


def test_insufficient_poi_enters_cooldown_and_next_batch_advances(tmp_path) -> None:
    store = ReviewStore(":memory:")
    detail = PlaceDetailService(DisabledReviewClient(), store=store, author_hash_salt="test")
    places = [_place("TJ001", "民园广场", "4.8"), _place("TJ002", "五大道", "4.7")]
    run_root = tmp_path / "runs"
    runner = InsufficientRunner(run_root)
    pipeline = CityContentPipelineService(
        FakeCatalog(places),
        detail,
        MediaCrawlerImportService(
            FakeCatalog(places), detail, data_root=tmp_path / "exports", run_root=run_root,
        ),
        runner,
        store,
    )

    first = asyncio.run(pipeline.run_city_and_wait("天津市", top=2, max_targets=1))
    second = asyncio.run(pipeline.run_city_and_wait("天津市", top=2, max_targets=1))

    assert first["items"][0]["poi_id"] == "TJ001"
    assert first["items"][0]["status"] == "insufficient"
    assert store.get_collection_target("TJ001")["status"] == "insufficient"
    assert second["items"][0]["poi_id"] == "TJ002"
    assert runner.calls == 2
    store.close()


def test_city_pipeline_records_login_required_separately(tmp_path) -> None:
    store = ReviewStore(":memory:")
    detail = PlaceDetailService(DisabledReviewClient(), store=store, author_hash_salt="test")
    places = [_place("TJ001", "民园广场", "4.8")]
    importer = MediaCrawlerImportService(
        FakeCatalog(places),
        detail,
        data_root=tmp_path / "exports",
        run_root=tmp_path / "runs",
    )
    pipeline = CityContentPipelineService(
        FakeCatalog(places),
        detail,
        importer,
        LoginRequiredRunner(),
        store,
    )

    result = asyncio.run(pipeline.run_city_and_wait("天津市", top=1, headless=True))

    assert result["status"] == "login_required"
    assert result["items"][0]["status"] == "login_required"
    assert result["items"][0]["error"] == "LOGIN_REQUIRED"
    store.close()


def test_city_pipeline_imports_partial_export_and_leaves_missing_poi_due(tmp_path) -> None:
    store = ReviewStore(":memory:")
    detail = PlaceDetailService(DisabledReviewClient(), store=store, author_hash_salt="test")
    places = [_place("TJ001", "民园广场", "4.8"), _place("TJ002", "五大道", "4.7")]
    run_root = tmp_path / "runs"
    pipeline = CityContentPipelineService(
        FakeCatalog(places),
        detail,
        MediaCrawlerImportService(
            FakeCatalog(places),
            detail,
            data_root=tmp_path / "exports",
            run_root=run_root,
        ),
        PartialRunner(run_root),
        store,
    )

    result = asyncio.run(pipeline.run_city_and_wait("天津市", top=2, headless=False))

    assert result["status"] == "partial"
    assert result["items"][0]["status"] == "ready"
    assert result["items"][1]["status"] == "partial"
    assert result["items"][1]["error"] == "CRAWLER_INTERRUPTED"
    assert store.get_collection_target("TJ001") is not None
    assert store.get_collection_target("TJ002") is None
    store.close()


def test_captcha_interruption_is_detected_for_partial_import() -> None:
    assert _is_captcha_interruption("CAPTCHA appeared, status code 461")
    assert _is_captcha_interruption("Verifytype: 216")
    assert not _is_captcha_interruption("network connection reset")


def test_login_interruption_matches_current_mediacrawler_messages() -> None:
    assert _is_login_interruption("media_platform.xhs.exception.DataFetchError: 登录已过期")
    assert _is_login_interruption("Login xiaohongshu failed by qrcode login method")
    assert not _is_login_interruption("Login state result: True")


def test_partial_login_imports_existing_rows_and_pauses_run(tmp_path) -> None:
    store = ReviewStore(":memory:")
    detail = PlaceDetailService(DisabledReviewClient(), store=store, author_hash_salt="test")
    places = [_place("TJ001", "民园广场", "4.8"), _place("TJ002", "五大道", "4.7")]
    run_root = tmp_path / "runs"
    pipeline = CityContentPipelineService(
        FakeCatalog(places),
        detail,
        MediaCrawlerImportService(
            FakeCatalog(places), detail, data_root=tmp_path / "exports", run_root=run_root,
        ),
        PartialLoginRunner(run_root),
        store,
    )

    result = asyncio.run(pipeline.run_city_and_wait("天津市", top=2, headless=False))

    assert result["status"] == "login_required"
    assert result["items"][0]["status"] == "ready"
    assert result["items"][1]["status"] == "login_required"
    assert result["items"][1]["error"] == "LOGIN_REQUIRED"
    assert len(store.list_active_evidence("TJ001")) == 20
    store.close()


def test_network_interruption_is_classified_for_retry() -> None:
    assert _is_network_interruption("httpx.ConnectError: All connection attempts failed")
    assert _is_network_interruption("ReadTimeout")
    assert not _is_network_interruption("CAPTCHA appeared")


def test_city_pipeline_records_network_outage_separately(tmp_path) -> None:
    store = ReviewStore(":memory:")
    detail = PlaceDetailService(DisabledReviewClient(), store=store, author_hash_salt="test")
    places = [_place("TJ001", "民园广场", "4.8")]
    pipeline = CityContentPipelineService(
        FakeCatalog(places),
        detail,
        MediaCrawlerImportService(
            FakeCatalog(places),
            detail,
            data_root=tmp_path / "exports",
            run_root=tmp_path / "runs",
        ),
        NetworkUnavailableRunner(),
        store,
    )

    result = asyncio.run(pipeline.run_city_and_wait("天津市", top=1))

    assert result["status"] == "network_unavailable"
    assert result["items"][0]["error"] == "NETWORK_UNAVAILABLE"
    store.close()
