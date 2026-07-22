from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.schemas.explore import PlaceSummary
from app.review_store import ReviewStore
from app.services.official_content_service import (
    OfficialContentService,
    OfficialResponseTooLargeError,
    OfficialSourceSecurityError,
)


ANNOUNCEMENTS_HTML = """
<html><body>
  <ul>
    <li><a href="/announce_detail/100.html">关于坤宁宫暂停开放的公告</a><span>2026 / 05 / 29</span></li>
    <li><a href="https://www.dpm.org.cn/announce_detail/101.html?from=home">故宫博物院关于春节开放时间的公告</a><time>2026-02-10</time></li>
    <li><a href="/announce_detail/100.html">重复链接</a></li>
    <li><a href="/news/other.html">普通新闻</a></li>
  </ul>
</body></html>
"""

BOOKING_HTML = """
<html><body>
  <p>故宫博物院实行实名制预约、检票，所有观众均须实名预约参观。</p>
  <p>故宫博物院不售当日票，门票于参观7日前20:00开始预约。</p>
  <section>每年4月1日至10月31日为旺季，门票60元/人；
    每年11月1日至次年3月31日为淡季，门票40元/人；
    珍宝馆，参观门票：10元/人；钟表馆，参观门票：10元/人；</section>
  <p>除法定节假日，故宫博物院全年实行周一闭馆</p>
  <div>08:30 <span>开放入馆时间</span> 16:00 <span>停止入馆时间</span>
    17:00 <span>闭馆时间</span></div>
</body></html>
"""


def _place() -> PlaceSummary:
    return PlaceSummary(
        id="amap-B000A",
        sourcePoiId="B000A",
        name="故宫博物院",
        category="风景名胜",
        categoryCode="110000",
    )


def _service(handler, **kwargs) -> OfficialContentService:
    return OfficialContentService(
        transport=httpx.MockTransport(handler),
        now=lambda: datetime(2026, 7, 22, tzinfo=timezone.utc),
        **kwargs,
    )


def test_dpm_adapter_emits_store_ready_attributable_records(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/announce.html":
            return httpx.Response(200, text=ANNOUNCEMENTS_HTML, request=request)
        if request.url.path == "/subject_booking/index.html":
            return httpx.Response(200, text=BOOKING_HTML, request=request)
        raise AssertionError(f"unexpected URL: {request.url}")

    records = asyncio.run(_service(handler).fetch_for_place(_place(), "dpm"))

    assert OfficialContentService.supported_source_ids >= {"dpm", "jiuzhai", "huangshan", "bmy", "panda"}
    assert len(records) == 5
    assert {item["notice_type"] for item in records} == {
        "CLOSURE",
        "HOLIDAY_HOURS",
        "RESERVATION",
        "TICKET",
    }
    closure = next(item for item in records if item["notice_type"] == "CLOSURE")
    assert closure["published_at"] == "2026-05-29"
    assert closure["source_url"] == "https://www.dpm.org.cn/announce_detail/100.html"
    ticket = next(item for item in records if item["notice_type"] == "TICKET")
    assert ticket["ticket_price"] == "旺季门票60元/人；淡季门票40元/人；珍宝馆10元/人；钟表馆10元/人"
    reservation = next(item for item in records if item["notice_type"] == "RESERVATION")
    assert reservation["reservation_url"] == "https://ticket.dpm.org.cn/"
    hours = next(item for item in records if item["title"] == "故宫博物院开放时间")
    assert hours["summary"] == "除法定节假日外周一闭馆；开放入馆08:30；停止入馆16:00；闭馆17:00"
    for item in records:
        assert item["poi_id"] == "B000A"
        assert item["notice_id"].startswith("dpm:")
        assert item["verified_at"] == "2026-07-22T00:00:00+00:00"
        assert item["deleted"] is False

    with ReviewStore(tmp_path / "official.sqlite3") as store:
        store.upsert_place_profile(_place())
        saved = [store.upsert_official_notice(item) for item in records]
        assert len(saved) == len(records)


def test_notice_ids_are_stable_and_duplicate_links_are_removed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = ANNOUNCEMENTS_HTML if request.url.path == "/announce.html" else BOOKING_HTML
        return httpx.Response(200, text=content, request=request)

    service = _service(handler)
    first = asyncio.run(service.fetch_for_place(_place(), "dpm"))
    second = asyncio.run(service.fetch_for_place(_place(), "dpm"))
    assert [item["notice_id"] for item in first] == [item["notice_id"] for item in second]
    assert len({item["notice_id"] for item in first}) == len(first)


def test_redirect_cannot_leave_official_allowlist() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.example/collect"},
            request=request,
        )

    with pytest.raises(OfficialSourceSecurityError):
        asyncio.run(_service(handler).fetch_for_place(_place(), "dpm"))


def test_response_size_is_limited_before_buffering() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": "5000"},
            content=b"small body",
            request=request,
        )

    with pytest.raises(OfficialResponseTooLargeError):
        asyncio.run(
            _service(handler, max_response_bytes=100).fetch_for_place(_place(), "dpm")
        )


def test_rejects_unknown_source_without_network_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="", request=request)

    with pytest.raises(ValueError, match="unsupported official source"):
        asyncio.run(_service(handler).fetch_for_place(_place(), "unknown"))
    assert calls == 0


def test_jiuzhai_document_adapter_extracts_announcements_and_facts() -> None:
    html = """
    <html><body>
      <a href="/news/notice/100">九寨沟景区临时闭园公告</a><span>2026-07-20</span>
      <p>旺季门票：190元/人。观光车票：90元/人。</p>
      <p>景区实行实名预约，最大承载量为4.1万人次/日。</p>
      <p>入园时间：8:00-14:00；闭园时间：18:00。</p>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, request=request)

    records = asyncio.run(_service(handler).fetch_for_place(_place(), "jiuzhai"))
    types = {item["notice_type"] for item in records}
    assert {"CLOSURE", "TICKET", "RESERVATION", "HOLIDAY_HOURS", "CAPACITY"} <= types
    assert all(item["notice_id"].startswith("jiuzhai:") for item in records)
    assert any("41000" in item["summary"] for item in records if item["notice_type"] == "CAPACITY")
