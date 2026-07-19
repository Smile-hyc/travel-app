from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.schemas.explore import PlaceSummary, ReviewSource
from app.services.tikhub_review_client import _find_note_candidates, _is_relevant, _parse_note


class RnoteReviewClient:
    """Rnote Xiaohongshu search adapter.

    One place lookup intentionally performs only one billable search request.
    Search results are parsed defensively because Rnote returns the upstream
    Xiaohongshu payload without publishing a response schema in OpenAPI.
    """

    SEARCH_PATH = "/api/v2/crawler/search/notes"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return self._settings.rnote_configured

    async def search_place(self, place: PlaceSummary) -> list[ReviewSource]:
        if not self.configured:
            return []

        query = " ".join(part for part in (place.cityName, place.name) if part).strip()
        if not query:
            return []

        timeout = httpx.Timeout(
            connect=self._settings.rnote_connect_timeout_seconds,
            read=self._settings.rnote_read_timeout_seconds,
            write=8.0,
            pool=5.0,
        )
        params = {
            "keyword": query,
            "page": 1,
            "sort_type": "general",
            "note_type": "不限",
            "time_filter": "不限",
            "source": "explore_feed",
            "ai_mode": 0,
        }
        headers = {
            "X-API-Key": self._settings.rnote_api_key.strip(),
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{self._settings.rnote_base_url.rstrip('/')}{self.SEARCH_PATH}",
                    params=params,
                    headers=headers,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return []

        if isinstance(payload, dict) and payload.get("success") is False:
            return []
        return _parse_search_results(
            payload,
            place=place,
            limit=max(1, min(self._settings.rnote_max_sources, 12)),
        )


def _parse_search_results(
    payload: Any,
    *,
    place: PlaceSummary,
    limit: int,
) -> list[ReviewSource]:
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    results: list[ReviewSource] = []
    seen: set[str] = set()
    for candidate in _find_note_candidates(data):
        source = _parse_note(candidate, provider="Rnote API")
        if source is None or source.id in seen or not _is_relevant(source, place):
            continue
        seen.add(source.id)
        results.append(source)
        if len(results) >= limit:
            break
    return results
