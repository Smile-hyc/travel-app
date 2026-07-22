from __future__ import annotations

import re
import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.schemas.explore import PlaceSummary, ReviewSource
from app.services.content_cleaning import MIN_RELEVANCE_SCORE, compute_place_relevance


class ReviewProviderError(RuntimeError):
    def __init__(self, kind: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


class TikhubReviewClient:
    """Optional Xiaohongshu public-content adapter.

    The provider response has changed shape between API revisions, so parsing is
    intentionally defensive. Provider failures raise a typed error so they are
    never persisted as a misleading "this place has no notes" result.
    """

    SEARCH_PATH = "/api/v1/xiaohongshu/app_v2/search_notes"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._last_error: ReviewProviderError | None = None

    @property
    def configured(self) -> bool:
        return self._settings.authorized_ugc_configured

    @property
    def last_error(self) -> ReviewProviderError | None:
        return self._last_error

    async def search_place(self, place: PlaceSummary) -> list[ReviewSource]:
        if not self.configured:
            return []

        query = " ".join(part for part in (place.cityName, place.name) if part).strip()
        if not query:
            return []

        timeout = httpx.Timeout(
            connect=self._settings.tikhub_connect_timeout_seconds,
            read=self._settings.tikhub_read_timeout_seconds,
            write=8.0,
            pool=5.0,
        )
        headers = {"Authorization": f"Bearer {self._settings.tikhub_api_key.strip()}"}
        params = {
            "keyword": query,
            "page": 1,
            "sort_type": "popularity_descending",
            "note_type": "不限",
            "time_filter": "不限",
            "source": "explore_feed",
            "ai_mode": 0,
        }
        try:
            client = await self._get_client(timeout)
            response = await client.get(
                self.SEARCH_PATH,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            kind = {
                401: "AUTH_ERROR",
                403: "AUTH_ERROR",
                402: "QUOTA_EXHAUSTED",
                429: "RATE_LIMITED",
            }.get(status, "UPSTREAM_ERROR")
            error = ReviewProviderError(kind, f"UGC provider returned HTTP {status}.", status_code=status)
            self._last_error = error
            raise error from exc
        except httpx.RequestError as exc:
            error = ReviewProviderError("NETWORK_ERROR", "UGC provider request failed.")
            self._last_error = error
            raise error from exc
        except (ValueError, TypeError) as exc:
            error = ReviewProviderError("INVALID_RESPONSE", "UGC provider returned invalid JSON.")
            self._last_error = error
            raise error from exc

        self._last_error = None

        candidates = _find_note_candidates(payload)
        results: list[ReviewSource] = []
        seen: set[str] = set()
        for candidate in candidates:
            source = _parse_note(candidate)
            if source is None or source.id in seen or not _is_relevant(source, place):
                continue
            seen.add(source.id)
            results.append(
                source.model_copy(
                    update={
                        "relevanceScore": compute_place_relevance(
                            place,
                            source.title,
                            source.excerpt,
                        ),
                    },
                ),
            )
            if len(results) >= max(1, min(self._settings.tikhub_max_sources, 12)):
                break
        return results

    async def search_places(self, places: list[PlaceSummary]) -> dict[str, list[ReviewSource]]:
        """Search a bounded POI batch through one reusable HTTP connection pool."""
        semaphore = asyncio.Semaphore(4)

        async def search(place: PlaceSummary) -> tuple[str, list[ReviewSource]]:
            async with semaphore:
                return place.sourcePoiId, await self.search_place(place)

        pairs = await asyncio.gather(*(search(place) for place in places))
        return dict(pairs)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        base_url=self._settings.tikhub_base_url.rstrip("/"),
                        timeout=timeout,
                        trust_env=True,
                    )
        return self._client


def _find_note_candidates(value: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return

        note = node.get("note_card") if isinstance(node.get("note_card"), dict) else node
        note_id = _first_text(note, "note_id", "id", "noteId")
        title = _first_text(note, "display_title", "title", "name")
        if note_id and title:
            candidates.append(node)
            return
        for child in node.values():
            visit(child)

    visit(value)
    return candidates


def _parse_note(raw: dict[str, Any], *, provider: str | None = None) -> ReviewSource | None:
    note = raw.get("note_card") if isinstance(raw.get("note_card"), dict) else raw
    note_id = _first_text(note, "note_id", "id", "noteId") or _first_text(raw, "id", "note_id")
    title = _first_text(note, "display_title", "title", "name")
    if not note_id or not title:
        return None

    user = note.get("user") if isinstance(note.get("user"), dict) else {}
    author = _first_text(user, "nickname", "nick_name", "name")
    excerpt = _first_text(note, "desc", "description", "content")
    interact_info = note.get("interact_info") if isinstance(note.get("interact_info"), dict) else {}
    like_count = _first_text(interact_info, "liked_count", "like_count", "likes")
    raw_url = _first_text(raw, "url", "note_url", "share_url") or _first_text(
        note, "url", "note_url", "share_url"
    )
    if raw_url and raw_url.startswith(("https://", "http://")):
        url = raw_url
    else:
        xsec_token = _first_text(raw, "xsec_token", "xsecToken") or _first_text(
            note, "xsec_token", "xsecToken"
        )
        query = urlencode({"xsec_token": xsec_token, "xsec_source": "pc_search"}) if xsec_token else ""
        url = f"https://www.xiaohongshu.com/explore/{note_id}" + (f"?{query}" if query else "")
    published = _format_timestamp(note.get("time") or note.get("timestamp") or note.get("publish_time"))
    return ReviewSource(
        id=f"xiaohongshu:{note_id}",
        platform="小红书",
        title=title[:80],
        url=url,
        author=author[:40] if author else None,
        excerpt=excerpt[:180] if excerpt else None,
        publishedAt=published,
        # UGC media is intentionally neither downloaded nor propagated into the
        # product data model. Place imagery comes from AMap/official sources.
        coverImageUrl=None,
        likeCount=like_count[:20] if like_count else None,
        # Provider identity is an internal implementation detail. The UI only
        # receives the authorized platform source and traceable original URL.
        provider=None,
    )


def _find_cover_image_url(note: dict[str, Any], raw: dict[str, Any]) -> str | None:
    for container in (note.get("cover"), raw.get("cover")):
        url = _image_url_from_value(container)
        if url:
            return url
    for key in ("image_list", "images_list", "images"):
        for container in (note.get(key), raw.get(key)):
            url = _image_url_from_value(container)
            if url:
                return url
    return None


def _image_url_from_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() if value.startswith(("https://", "http://")) else None
    if isinstance(value, list):
        for item in value[:3]:
            url = _image_url_from_value(item)
            if url:
                return url
        return None
    if not isinstance(value, dict):
        return None
    for key in ("url_default", "url_pre", "url", "url_1", "url_2", "master_url"):
        url = _image_url_from_value(value.get(key))
        if url:
            return url
    for key in ("info_list", "url_list"):
        url = _image_url_from_value(value.get(key))
        if url:
            return url
    return None


def _is_relevant(source: ReviewSource, place: PlaceSummary) -> bool:
    return compute_place_relevance(place, source.title, source.excerpt) >= MIN_RELEVANCE_SCORE


def _base_place_name(name: str) -> str:
    return re.sub(r"[（(][^）)]*(?:店|馆|院|景区|分店)?[）)]", "", name).strip()


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s·•,，。.!！?？()（）\-_]", "", value).lower()


def _first_text(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is None or isinstance(value, (dict, list)):
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _format_timestamp(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value).strip()[:32] or None
