from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.review_store import ReviewStore, hash_author_identifier


def _place(poi_id: str = "B001") -> dict[str, object]:
    return {
        "sourcePoiId": poi_id,
        "source": "AMAP",
        "name": "故宫博物院",
        "category": "scenic",
        "categoryCode": "110200",
        "address": "景山前街4号",
        "cityName": "北京市",
        "latitude": 39.9163,
        "longitude": 116.3972,
        "openingHoursToday": "08:30-17:00",
        "rating": "4.8",
        "phone": "4009501925",
        "route": {"walking_minutes": 12},
        "images": ["must-not-be-persisted.jpg"],
    }


def test_place_profiles_are_upserted_and_batch_read(tmp_path) -> None:
    path = tmp_path / "reviews.sqlite3"
    with ReviewStore(path) as store:
        saved = store.upsert_place_profile(_place())
        store.upsert_place_profile({**_place(), "rating": "4.9"})
        store.upsert_place_profile(_place("B002"))

        assert saved["poi_id"] == "B001"
        assert saved["route_json"] == {"walking_minutes": 12}
        assert store.get_place_profile("B001")["rating"] == "4.9"
        assert set(store.get_place_profiles(["B002", "B001", "missing"])) == {
            "B001",
            "B002",
        }

    with ReviewStore(path) as reopened:
        assert reopened.get_place_profile("B001")["name"] == "故宫博物院"


def test_official_notices_filter_deleted_and_effective_window(tmp_path) -> None:
    now = datetime.now(tz=timezone.utc)
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        store.upsert_place_profile(_place())
        store.upsert_official_notice(
            {
                "noticeId": "notice-current",
                "poiId": "B001",
                "noticeType": "holiday_hours",
                "title": "暑期延长开放",
                "summary": "周末延长开放一小时",
                "sourceUrl": "https://example.org/notices/current",
                "effectiveFrom": now - timedelta(days=1),
                "effectiveTo": now + timedelta(days=1),
            }
        )
        store.upsert_official_notice(
            {
                "noticeId": "notice-old",
                "poiId": "B001",
                "noticeType": "closure",
                "title": "历史闭园通知",
                "sourceUrl": "https://example.org/notices/old",
                "effectiveTo": now - timedelta(days=2),
            }
        )

        active = store.list_official_notices("B001", at=now)
        assert [item["notice_id"] for item in active] == ["notice-current"]
        assert len(store.list_official_notices("B001", active_only=False)) == 2


def test_evidence_is_structured_anonymized_and_soft_deletable(tmp_path) -> None:
    author_hash = hash_author_identifier("upstream-user-123", salt="test-salt")
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        store.upsert_place_profile(_place())
        saved = store.save_evidence(
            {
                "evidenceId": "evidence-1",
                "poiId": "B001",
                "sourceNoteId": "note-1",
                "sourceUrl": "https://example.org/note-1",
                "publishedAt": "2026-07-20T10:00:00+08:00",
                "authorHash": author_hash,
                "relevanceScore": 0.93,
                "tags": ["拍照", "排队"],
                "shortSummary": "午后拍照光线较好，周末排队明显。",
                "mentionCount": 2,
                "summaryVersion": "ugc-summary-v1",
                "raw_text": "must not be persisted",
                "image_url": "must-not-be-persisted.jpg",
            }
        )

        assert saved["author_hash"] == author_hash
        assert saved["provider"] == "xiaohongshu"
        assert saved["tags_json"] == ["拍照", "排队"]
        assert saved["source_url"].endswith("note-1")
        assert len(store.list_active_evidence("B001")) == 1
        assert store.mark_evidence_deleted("evidence-1") is True
        assert store.list_active_evidence("B001") == []

    connection = sqlite3.connect(tmp_path / "reviews.sqlite3")
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(ugc_evidence)").fetchall()
        }
    finally:
        connection.close()
    assert "raw_text" not in columns
    assert "image_url" not in columns
    assert "author" not in columns
    assert "author_hash" in columns


def test_review_aggregates_support_batch_cache_lookup(tmp_path) -> None:
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        store.upsert_place_profile(_place())
        aggregate = store.save_aggregate(
            {
                "poiId": "B001",
                "tags": {"拍照": 4, "排队": 3},
                "insights": {
                    "photo": "午后光线较好",
                    "queue": "周末排队明显",
                },
                "evidenceIds": ["e1", "e2", "e3"],
                "independentSourceCount": 3,
                "confidence": 0.82,
                "summaryVersion": "aggregate-v2",
                "expiresAt": "2026-07-29T00:00:00+00:00",
            }
        )

        assert aggregate["status"] == "ready"
        assert aggregate["evidence_count"] == 3
        assert aggregate["evidence_ids_json"] == ["e1", "e2", "e3"]
        assert aggregate["insights_json"]["queue"] == "周末排队明显"
        assert store.get_aggregates(["B001", "missing"])["B001"]["confidence"] == 0.82


def test_closed_store_rejects_queries() -> None:
    store = ReviewStore(":memory:")
    store.close()
    store.close()

    try:
        store.get_place_profile("B001")
    except RuntimeError as exc:
        assert str(exc) == "ReviewStore is closed"
    else:
        raise AssertionError("closed store should reject queries")


def test_collection_targets_are_due_ordered_updated_and_reopenable(tmp_path) -> None:
    path = tmp_path / "reviews.sqlite3"
    now = datetime.now(tz=timezone.utc)
    with ReviewStore(path) as store:
        store.upsert_collection_target(
            {
                "poiId": "future",
                "priority": 100,
                "tier": "hot",
                "refreshIntervalHours": 24,
                "nextCollectionAt": now + timedelta(hours=1),
            }
        )
        store.upsert_collection_target(
            {
                "poiId": "due-low",
                "priority": 10,
                "tier": "warm",
                "refreshIntervalHours": 72,
                "nextCollectionAt": now - timedelta(hours=2),
            }
        )
        store.upsert_collection_target(
            {
                "poiId": "due-high",
                "priority": 20,
                "tier": "hot",
                "refreshIntervalHours": 24,
                "nextCollectionAt": now - timedelta(hours=1),
            }
        )
        store.upsert_collection_target(
            {"poiId": "disabled", "priority": 999, "active": False}
        )

        assert [item["poi_id"] for item in store.list_collection_targets(due_only=True)] == [
            "due-high",
            "due-low",
        ]
        updated = store.update_collection_target(
            "due-high",
            status="ready",
            lastCollectedAt=now,
            nextCollectionAt=now + timedelta(days=1),
            lastError=None,
        )
        assert updated["status"] == "ready"
        assert updated["last_error"] is None
        assert updated["active"] is True

        # Re-importing popularity metadata must not reset collection progress.
        reimported = store.upsert_collection_target(
            {"poiId": "due-high", "priority": 30}
        )
        assert reimported["last_collected_at"] == updated["last_collected_at"]
        assert reimported["next_collection_at"] == updated["next_collection_at"]
        assert reimported["priority"] == 30
        still_disabled = store.upsert_collection_target({"poiId": "disabled"})
        assert still_disabled["active"] is False
        assert still_disabled["priority"] == 999

    with ReviewStore(path) as reopened:
        assert reopened.get_collection_target("due-high")["status"] == "ready"
        assert len(reopened.list_collection_targets(active_only=False)) == 4


def test_ingestion_runs_record_counts_failure_and_stats(tmp_path) -> None:
    path = tmp_path / "reviews.sqlite3"
    with ReviewStore(path) as store:
        started = store.start_ingestion_run(
            {"runId": "run-1", "provider": "authorized-ugc", "targetCount": 12}
        )
        assert started["status"] == "running"
        assert started["target_count"] == 12
        assert store.get_content_stats()["running_ingestion_count"] == 1

        finished = store.finish_ingestion_run(
            "run-1",
            status="partial",
            fetchedCount=80,
            acceptedCount=25,
            savedCount=22,
            skippedCount=55,
            failedCount=3,
            error="three targets failed",
        )
        assert finished["finished_at"] is not None
        assert finished["saved_count"] == 22
        assert finished["error"] == "three targets failed"
        assert store.list_ingestion_runs()[0]["run_id"] == "run-1"
        assert store.get_content_stats()["running_ingestion_count"] == 0

    with ReviewStore(path) as reopened:
        assert reopened.get_ingestion_run("run-1")["status"] == "partial"


def test_collection_target_updates_are_thread_safe(tmp_path) -> None:
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        for index in range(12):
            store.upsert_collection_target({"poiId": f"poi-{index}", "priority": index})

        def mark_ready(index: int) -> str:
            result = store.update_collection_target(
                f"poi-{index}", status="ready", lastError=None
            )
            return result["status"]

        with ThreadPoolExecutor(max_workers=6) as pool:
            assert list(pool.map(mark_ready, range(12))) == ["ready"] * 12

        assert all(
            item["status"] == "ready"
            for item in store.list_collection_targets(active_only=False)
        )


def test_collection_target_and_run_validation(tmp_path) -> None:
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        try:
            store.upsert_collection_target(
                {"poiId": "bad", "refreshIntervalHours": 0}
            )
        except ValueError as exc:
            assert str(exc) == "refresh_interval_hours must be positive"
        else:
            raise AssertionError("zero refresh interval should be rejected")

        store.start_ingestion_run({"runId": "run", "provider": "test"})
        try:
            store.finish_ingestion_run("run", failedCount=-1)
        except ValueError as exc:
            assert str(exc) == "failed_count must be non-negative"
        else:
            raise AssertionError("negative run counts should be rejected")


def test_official_source_directory_keeps_channels_grade_and_capacity(tmp_path) -> None:
    with ReviewStore(tmp_path / "reviews.sqlite3") as store:
        saved = store.upsert_official_source(
            {
                "sourceId": "jiuzhai",
                "officialName": "九寨沟风景名胜区",
                "provinceName": "四川省",
                "cityName": "阿坝藏族羌族自治州",
                "scenicGrade": "5A",
                "websiteUrl": "https://www.jiuzhai.com/",
                "wechatName": "九寨沟",
                "miniProgramName": "阿坝旅游网",
                "capabilities": ["TICKET", "CLOSURE", "CAPACITY"],
                "maxDailyCapacity": 41000,
            }
        )
        assert saved["scenic_grade"] == "5A"
        assert saved["capabilities"] == ["TICKET", "CLOSURE", "CAPACITY"]
        assert saved["max_daily_capacity"] == 41000
        assert store.list_official_sources(city_name="阿坝藏族羌族自治州")[0]["source_id"] == "jiuzhai"
        assert store.get_content_stats()["official_source_count"] == 1
