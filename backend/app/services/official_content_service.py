from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.schemas.explore import PlaceSummary


class OfficialContentError(RuntimeError):
    """Raised when an official source cannot be fetched safely."""


class OfficialSourceSecurityError(OfficialContentError):
    """Raised when a request leaves the configured official-domain boundary."""


class OfficialResponseTooLargeError(OfficialContentError):
    """Raised before an unexpectedly large official response is buffered."""


class _TextAndLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.links: list[dict[str, object]] = []
        self._active_link: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        self.links.append({"href": href, "parts": [], "position": len(self.text_parts)})
        self._active_link = len(self.links) - 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            self._active_link = None

    def handle_data(self, data: str) -> None:
        value = _clean_text(data)
        if not value:
            return
        self.text_parts.append(value)
        if self._active_link is not None:
            parts = self.links[self._active_link]["parts"]
            assert isinstance(parts, list)
            parts.append(value)

    @property
    def text(self) -> str:
        return _clean_text(" ".join(self.text_parts))


_DPM_ANNOUNCEMENTS: Final = "https://www.dpm.org.cn/announce.html"
_DPM_BOOKING: Final = "https://www.dpm.org.cn/subject_booking/index.html"
_DPM_RESERVATION: Final = "https://ticket.dpm.org.cn/"
_DPM_HOSTS: Final = frozenset({"dpm.org.cn", "www.dpm.org.cn", "ticket.dpm.org.cn"})
_REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})
_DATE_PATTERN: Final = re.compile(r"(?<!\d)(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:日)?(?!\d)")


@dataclass(frozen=True)
class _DocumentSource:
    source_id: str
    official_name: str
    pages: tuple[str, ...]
    allowed_hosts: frozenset[str]
    detail_markers: tuple[str, ...]
    ticketing_url: str | None = None


_DOCUMENT_SOURCES: Final = {
    "jiuzhai": _DocumentSource(
        "jiuzhai",
        "九寨沟风景名胜区",
        (
            "https://www.jiuzhai.com/news/notice",
            "https://www.jiuzhai.com/intelligent-service/tickets",
        ),
        frozenset({"jiuzhai.com", "www.jiuzhai.com"}),
        ("/news/notice/",),
    ),
    "huangshan": _DocumentSource(
        "huangshan",
        "黄山风景区",
        (
            "https://hsgwh.huangshan.gov.cn/xwzx/tzgg/index.html",
            "https://hsgwh.huangshan.gov.cn/lyfw/lyfw/mp/index.html",
            "https://wap.huangshan.com.cn/hsdetail/ticket/park2017122114525726",
        ),
        frozenset({"hsgwh.huangshan.gov.cn", "wap.huangshan.com.cn"}),
        ("/xwzx/tzgg/", "/lyfw/lyfw/mp/", "/hsdetail/ticket/"),
        "https://www.huangshan.com.cn/",
    ),
    "bmy": _DocumentSource(
        "bmy",
        "秦始皇帝陵博物院",
        ("https://www.bmy.com.cn/guide/", "https://www.bmy.com.cn/guide/notice.html"),
        frozenset({"bmy.com.cn", "www.bmy.com.cn"}),
        ("/news/notice/", "/guide/notice"),
        "https://bmy.albatrip.cn/",
    ),
    "panda": _DocumentSource(
        "panda",
        "成都大熊猫繁育研究基地",
        ("https://www.panda.org.cn/cn/service/ticket/", "https://m.panda.org.cn/cn/"),
        frozenset({"panda.org.cn", "www.panda.org.cn", "m.panda.org.cn"}),
        ("/cn/news/", "/cn/notice/", "/cn/service/ticket/"),
        "https://pw.panda.org.cn/login.jhtml",
    ),
}


class OfficialContentService:
    """Fetch small, attributable records from explicitly supported official sites.

    Official pages are monitored as documents, not treated as undocumented ticket
    APIs. Every emitted mapping can be passed directly to
    :meth:`ReviewStore.upsert_official_notice`.
    """

    supported_source_ids: Final = frozenset({"dpm", *_DOCUMENT_SOURCES})

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 8.0,
        max_response_bytes: int = 1_000_000,
        max_redirects: int = 3,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if client is not None and transport is not None:
            raise ValueError("pass client or transport, not both")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")
        self._client = client
        self._transport = transport
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 3.0))
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._now = now or (lambda: datetime.now(tz=timezone.utc))

    async def fetch_for_place(self, place: PlaceSummary, source_id: str) -> list[dict]:
        if source_id not in self.supported_source_ids:
            raise ValueError(f"unsupported official source: {source_id}")

        if source_id != "dpm":
            return await self._fetch_document_source(place, _DOCUMENT_SOURCES[source_id])

        pages: dict[str, str] = {}
        failures: list[OfficialContentError] = []
        for key, url in (("announcements", _DPM_ANNOUNCEMENTS), ("booking", _DPM_BOOKING)):
            try:
                pages[key] = await self._fetch_text(url, allowed_hosts=_DPM_HOSTS)
            except OfficialSourceSecurityError:
                raise
            except OfficialContentError as exc:
                failures.append(exc)

        if not pages:
            raise failures[0]

        verified_at = self._now().astimezone(timezone.utc).isoformat()
        records: list[dict] = []
        if "announcements" in pages:
            records.extend(
                _parse_dpm_announcements(
                    pages["announcements"],
                    poi_id=place.sourcePoiId,
                    verified_at=verified_at,
                )
            )
        if "booking" in pages:
            records.extend(
                _parse_dpm_booking(
                    pages["booking"],
                    poi_id=place.sourcePoiId,
                    verified_at=verified_at,
                )
            )

        unique: dict[str, dict] = {}
        for record in records:
            unique[record["notice_id"]] = record
        return list(unique.values())

    async def _fetch_document_source(
        self,
        place: PlaceSummary,
        source: _DocumentSource,
    ) -> list[dict]:
        verified_at = self._now().astimezone(timezone.utc).isoformat()
        records: list[dict] = []
        failures: list[OfficialContentError] = []
        for page_url in source.pages:
            try:
                html = await self._fetch_text(page_url, allowed_hosts=source.allowed_hosts)
            except OfficialSourceSecurityError:
                raise
            except OfficialContentError as exc:
                failures.append(exc)
                continue
            records.extend(
                _parse_document_source(
                    html,
                    page_url=page_url,
                    source=source,
                    poi_id=place.sourcePoiId,
                    verified_at=verified_at,
                ),
            )
        if not records and failures:
            raise failures[0]
        return list({item["notice_id"]: item for item in records}.values())

    async def _fetch_text(self, url: str, *, allowed_hosts: frozenset[str]) -> str:
        self._validate_url(url, allowed_hosts)
        if self._client is not None:
            return await self._fetch_with_client(self._client, url, allowed_hosts)
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            follow_redirects=False,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/150.0.0.0 Safari/537.36 AITravelCourseDemo/1.0"
                ),
            },
        ) as client:
            return await self._fetch_with_client(client, url, allowed_hosts)

    async def _fetch_with_client(
        self,
        client: httpx.AsyncClient,
        url: str,
        allowed_hosts: frozenset[str],
    ) -> str:
        current = url
        for redirect_count in range(self._max_redirects + 1):
            self._validate_url(current, allowed_hosts)
            try:
                async with client.stream(
                    "GET",
                    current,
                    timeout=self._timeout,
                    follow_redirects=False,
                    headers={"Accept": "text/html,application/xhtml+xml"},
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise OfficialContentError("official source returned an empty redirect")
                        if redirect_count >= self._max_redirects:
                            raise OfficialContentError("official source exceeded redirect limit")
                        current = urljoin(str(response.url), location)
                        self._validate_url(current, allowed_hosts)
                        continue

                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise OfficialContentError(
                            f"official source returned HTTP {response.status_code}"
                        ) from exc

                    content_length = response.headers.get("content-length")
                    if content_length and content_length.isdigit():
                        if int(content_length) > self._max_response_bytes:
                            raise OfficialResponseTooLargeError(
                                "official response exceeds configured byte limit"
                            )

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_response_bytes:
                            raise OfficialResponseTooLargeError(
                                "official response exceeds configured byte limit"
                            )
                    encoding = response.encoding or "utf-8"
                    return bytes(body).decode(encoding, errors="replace")
            except OfficialContentError:
                raise
            except httpx.HTTPError as exc:
                raise OfficialContentError("official source request failed") from exc
        raise OfficialContentError("official source exceeded redirect limit")

    @staticmethod
    def _validate_url(url: str, allowed_hosts: frozenset[str]) -> None:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or host not in allowed_hosts:
            raise OfficialSourceSecurityError("official URL is outside the source allowlist")
        if parsed.username or parsed.password or parsed.port not in (None, 443):
            raise OfficialSourceSecurityError("official URL contains forbidden authority data")


def _parse_dpm_announcements(html: str, *, poi_id: str, verified_at: str) -> list[dict]:
    parser = _TextAndLinkParser()
    parser.feed(html)
    records: list[dict] = []
    seen_urls: set[str] = set()
    for link in parser.links:
        href = str(link["href"])
        source_url = _canonical_url(urljoin(_DPM_ANNOUNCEMENTS, href))
        path = urlsplit(source_url).path
        if "/announce_detail/" not in path or not path.endswith(".html"):
            continue
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        title = _clean_text(" ".join(str(item) for item in link["parts"]))
        if not title:
            continue
        position = int(link["position"])
        date_context = " ".join(parser.text_parts[max(0, position - 2) : position + 8])
        published_at = _extract_date(date_context)
        records.append(
            _notice(
                poi_id=poi_id,
                stable_key=source_url,
                notice_type=_classify_notice(title),
                title=title,
                summary=f"故宫博物院官网公告：{title}",
                source_url=source_url,
                published_at=published_at,
                verified_at=verified_at,
            )
        )
    return records


def _parse_dpm_booking(html: str, *, poi_id: str, verified_at: str) -> list[dict]:
    parser = _TextAndLinkParser()
    parser.feed(html)
    text = parser.text
    records: list[dict] = []

    reservation_parts = _sentences_matching(text, ("实名制预约", "7日前20:00"), limit=2)
    if reservation_parts:
        records.append(
            _notice(
                poi_id=poi_id,
                stable_key=f"{_DPM_BOOKING}#reservation",
                notice_type="RESERVATION",
                title="故宫博物院预约规则",
                summary="；".join(reservation_parts),
                source_url=_DPM_BOOKING,
                reservation_url=_DPM_RESERVATION,
                verified_at=verified_at,
            )
        )

    ticket_price = _extract_dpm_ticket_price(text)
    if ticket_price:
        records.append(
            _notice(
                poi_id=poi_id,
                stable_key=f"{_DPM_BOOKING}#ticket",
                notice_type="TICKET",
                title="故宫博物院官方票价",
                summary=ticket_price,
                source_url=_DPM_BOOKING,
                reservation_url=_DPM_RESERVATION,
                ticket_price=ticket_price,
                verified_at=verified_at,
            )
        )

    opening_hours = _extract_dpm_opening_hours(text)
    if opening_hours:
        records.append(
            _notice(
                poi_id=poi_id,
                stable_key=f"{_DPM_BOOKING}#opening-hours",
                notice_type="HOLIDAY_HOURS",
                title="故宫博物院开放时间",
                summary=opening_hours,
                source_url=_DPM_BOOKING,
                verified_at=verified_at,
            )
        )
    return records


def _notice(
    *,
    poi_id: str,
    stable_key: str,
    notice_type: str,
    title: str,
    summary: str,
    source_url: str,
    verified_at: str,
    reservation_url: str | None = None,
    ticket_price: str | None = None,
    published_at: str | None = None,
    source_id: str = "dpm",
) -> dict:
    digest = hashlib.sha256(f"{source_id}\n{stable_key}".encode("utf-8")).hexdigest()[:32]
    return {
        "notice_id": f"{source_id}:{digest}",
        "poi_id": poi_id,
        "notice_type": notice_type,
        "title": title,
        "summary": summary,
        "source_url": source_url,
        "reservation_url": reservation_url,
        "ticket_price": ticket_price,
        "effective_from": None,
        "effective_to": None,
        "published_at": published_at,
        "verified_at": verified_at,
        "deleted": False,
    }


def _parse_document_source(
    html: str,
    *,
    page_url: str,
    source: _DocumentSource,
    poi_id: str,
    verified_at: str,
) -> list[dict]:
    parser = _TextAndLinkParser()
    parser.feed(html)
    records: list[dict] = []
    seen: set[str] = set()
    for link in parser.links:
        title = _clean_text(" ".join(str(item) for item in link["parts"]))
        if not _interesting_official_title(title):
            continue
        source_url = _canonical_url(urljoin(page_url, str(link["href"])))
        if (urlsplit(source_url).hostname or "").lower() not in source.allowed_hosts:
            continue
        if source.detail_markers and not any(
            marker in urlsplit(source_url).path for marker in source.detail_markers
        ):
            continue
        if source_url in seen:
            continue
        seen.add(source_url)
        position = int(link["position"])
        context = " ".join(parser.text_parts[max(0, position - 2) : position + 8])
        records.append(
            _notice(
                poi_id=poi_id,
                stable_key=source_url,
                notice_type=_classify_notice(title),
                title=title[:160],
                summary=f"{source.official_name}官方发布：{title}"[:500],
                source_url=source_url,
                published_at=_extract_date(context),
                verified_at=verified_at,
                source_id=source.source_id,
            ),
        )
        if len(records) >= 40:
            break

    text = parser.text
    facts = _extract_document_facts(text, source)
    for notice_type, title, summary, ticket_price in facts:
        records.append(
            _notice(
                poi_id=poi_id,
                stable_key=f"{page_url}#{notice_type.lower()}",
                notice_type=notice_type,
                title=title,
                summary=summary,
                source_url=page_url,
                reservation_url=source.ticketing_url,
                ticket_price=ticket_price,
                verified_at=verified_at,
                source_id=source.source_id,
            ),
        )
    return records


def _interesting_official_title(title: str) -> bool:
    if len(title) < 4 or len(title) > 180:
        return False
    return any(
        word in title
        for word in (
            "公告",
            "通告",
            "通知",
            "提示",
            "开放",
            "闭园",
            "闭馆",
            "停运",
            "恢复运营",
            "预约",
            "门票",
            "票价",
            "限流",
            "承载量",
        )
    )


def _extract_document_facts(
    text: str,
    source: _DocumentSource,
) -> list[tuple[str, str, str, str | None]]:
    facts: list[tuple[str, str, str, str | None]] = []
    ticket_parts = _sentences_matching(text, ("门票", "票价", "观光车票"), limit=3)
    ticket_parts = [item for item in ticket_parts if "元" in item]
    if ticket_parts:
        summary = "；".join(ticket_parts)[:600]
        facts.append(("TICKET", f"{source.official_name}官方票价", summary, summary))

    reservation_parts = _sentences_matching(
        text,
        ("实名预约", "提前预约", "预订时间", "购票方式"),
        limit=3,
    )
    if reservation_parts:
        facts.append(
            (
                "RESERVATION",
                f"{source.official_name}预约规则",
                "；".join(reservation_parts)[:600],
                None,
            ),
        )

    opening_parts = _sentences_matching(
        text,
        ("开放时间", "入园时间", "停止检票", "闭馆时间", "闭园时间"),
        limit=4,
    )
    if opening_parts:
        facts.append(
            (
                "HOLIDAY_HOURS",
                f"{source.official_name}开放时间",
                "；".join(opening_parts)[:600],
                None,
            ),
        )

    capacity = re.search(
        r"(?:最大(?:游客)?承载量|日承载量|最大限流人数)[^。；]{0,40}?"
        r"(\d+(?:\.\d+)?)\s*(万)?\s*人(?:次)?(?:/日|每天|每日)?",
        text,
    )
    if capacity:
        amount = float(capacity.group(1)) * (10000 if capacity.group(2) else 1)
        facts.append(
            (
                "CAPACITY",
                f"{source.official_name}最大承载量",
                f"官网公布最大承载量约{int(amount)}人次/日。",
                None,
            ),
        )
    return facts


def _classify_notice(title: str) -> str:
    compact = title.replace(" ", "")
    if any(
        word in compact
        for word in ("闭馆", "闭园", "暂停开放", "停止开放", "临时关闭", "封闭", "停运")
    ):
        return "CLOSURE"
    if "开放时间" in compact or (
        any(word in compact for word in ("春节", "五一", "国庆", "假期", "节假日"))
        and any(word in compact for word in ("开放", "开馆", "入馆"))
    ):
        return "HOLIDAY_HOURS"
    if any(word in compact for word in ("承载量", "限流", "预约已满", "售罄")):
        return "CAPACITY"
    if any(word in compact for word in ("预约", "订票")):
        return "RESERVATION"
    if any(word in compact for word in ("票价", "门票", "半价", "免票")):
        return "TICKET"
    return "NOTICE"


def _extract_dpm_ticket_price(text: str) -> str | None:
    season = re.search(
        r"旺季[^。；]{0,80}?门票\s*[：:]?\s*(\d+)\s*元/人[；;。]?\s*"
        r"[^。；]{0,60}?淡季[^。；]{0,80}?门票\s*[：:]?\s*(\d+)\s*元/人",
        text,
    )
    if not season:
        return None
    parts = [f"旺季门票{season.group(1)}元/人", f"淡季门票{season.group(2)}元/人"]
    for venue in ("珍宝馆", "钟表馆"):
        match = re.search(rf"{venue}[^。；]{{0,40}}?门票\s*[：:]?\s*(\d+)\s*元/人", text)
        if match:
            parts.append(f"{venue}{match.group(1)}元/人")
    return "；".join(parts)


def _extract_dpm_opening_hours(text: str) -> str | None:
    match = re.search(
        r"(\d{1,2}:\d{2})\s*开放入馆时间\s*(\d{1,2}:\d{2})\s*"
        r"停止入馆时间\s*(\d{1,2}:\d{2})\s*闭馆时间",
        text,
    )
    if not match:
        return None
    prefix = "除法定节假日外周一闭馆；" if "周一闭馆" in text else ""
    return (
        f"{prefix}开放入馆{match.group(1)}；停止入馆{match.group(2)}；"
        f"闭馆{match.group(3)}"
    )


def _sentences_matching(text: str, needles: tuple[str, ...], *, limit: int) -> list[str]:
    sentences = [_clean_text(item) for item in re.split(r"[。；;]", text)]
    result: list[str] = []
    for needle in needles:
        for sentence in sentences:
            if needle in sentence and sentence not in result:
                result.append(sentence[:300])
                break
        if len(result) >= limit:
            break
    return result


def _extract_date(text: str) -> str | None:
    match = _DATE_PATTERN.search(text)
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date().isoformat()
    except ValueError:
        return None


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    netloc = host if parsed.port in (None, 443) else parsed.netloc
    path = re.sub(r"/{2,}", "/", parsed.path) or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
