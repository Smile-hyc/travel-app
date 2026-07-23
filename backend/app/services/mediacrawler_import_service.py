from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.explore import ReviewSource
from app.services.place_detail_service import PlaceDetailService
from app.services.popular_poi_catalog import PopularPoiCatalogService, PopularPoiSeed


class MediaCrawlerImportError(RuntimeError):
    pass


class MediaCrawlerImportService:
    """Import MediaCrawler JSONL exports into the normalized evidence store."""

    def __init__(
        self,
        catalog: PopularPoiCatalogService,
        detail_service: PlaceDetailService,
        *,
        data_root: str | Path,
        run_root: str | Path | None = None,
        max_file_bytes: int = 20_000_000,
    ) -> None:
        self._catalog = catalog
        self._detail_service = detail_service
        self._data_root = Path(data_root).expanduser().resolve()
        self._run_root = Path(run_root).expanduser().resolve() if run_root else None
        self._max_file_bytes = max_file_bytes

    def list_exports(self) -> list[dict[str, object]]:
        if not self._data_root.exists():
            return []
        return [
            {
                "fileName": path.name,
                "sizeBytes": path.stat().st_size,
                "modifiedAt": datetime.fromtimestamp(
                    path.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat(),
            }
            for path in sorted(
                self._data_root.glob("search_contents_*.jsonl"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )[:50]
        ]

    async def import_export(self, *, file_name: str, city_name: str) -> dict[str, Any]:
        path = self._safe_export_path(file_name)
        rows = self._load_rows(path)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            keyword = str(row.get("source_keyword") or "").strip()
            if keyword:
                grouped[keyword].append(row)

        imported: list[dict[str, object]] = []
        missing: list[str] = []
        city_places = await self._catalog.discover_city(city_name, limit=25)
        for keyword, items in grouped.items():
            normalized_keyword = _normalize(keyword)
            matched = next(
                (
                    place
                    for place in city_places
                    if normalized_keyword == _normalize(place.name)
                    or normalized_keyword in _normalize(place.name)
                    or _normalize(place.name) in normalized_keyword
                ),
                None,
            )
            resolved = []
            if matched is not None:
                resolved = [
                    (PopularPoiSeed(city_name, keyword, priority=80, tier="HOT"), matched),
                ]
            else:
                resolved, _ = await self._catalog.resolve(
                    [PopularPoiSeed(city_name, keyword, priority=80, tier="HOT")],
                )
            if not resolved:
                missing.append(keyword)
                continue
            _, place = resolved[0]
            result = self._detail_service.import_review_sources(
                place,
                [_to_review_source(item) for item in items if item.get("note_id")],
            )
            imported.append({key: value for key, value in result.items() if key != "detail"})

        return {
            "fileName": path.name,
            "cityName": city_name,
            "rowCount": len(rows),
            "keywordCount": len(grouped),
            "imported": imported,
            "missingKeywords": missing,
            "fetchedCount": sum(int(item["fetchedCount"]) for item in imported),
            "acceptedCount": sum(int(item["acceptedCount"]) for item in imported),
        }

    def import_manifest_export(
        self,
        *,
        export_path: str | Path,
        places_by_keyword: dict[str, Any],
        candidate_limit: int = 30,
    ) -> dict[str, Any]:
        """Import one isolated crawler run using an explicit query-to-POI map."""
        path = Path(export_path).expanduser().resolve()
        if self._run_root is None or not path.is_relative_to(self._run_root):
            raise MediaCrawlerImportError("crawler export is outside the configured run directory")
        if not path.is_file() or path.suffix.lower() != ".jsonl":
            raise MediaCrawlerImportError("crawler export does not exist")
        if path.stat().st_size > self._max_file_bytes:
            raise MediaCrawlerImportError("MediaCrawler export exceeds size limit")

        rows = self._load_rows(path)
        by_poi: dict[str, dict[str, Any]] = {}
        unmatched = 0
        limit = max(1, min(candidate_limit, 60))
        for row in rows:
            keyword = str(row.get("source_keyword") or "").strip()
            place = places_by_keyword.get(keyword)
            if place is None:
                unmatched += 1
                continue
            bucket = by_poi.setdefault(
                place.sourcePoiId,
                {"place": place, "rows": [], "keywords": set()},
            )
            bucket["keywords"].add(keyword)
            if len(bucket["rows"]) < limit:
                bucket["rows"].append(row)

        imported: list[dict[str, object]] = []
        for bucket in by_poi.values():
            place = bucket["place"]
            sources = [
                _to_review_source(item)
                for item in bucket["rows"]
                if item.get("note_id")
            ]
            result = self._detail_service.import_review_sources(place, sources)
            imported.append(
                {
                    key: value
                    for key, value in result.items()
                    if key != "detail"
                }
                | {"keywords": sorted(bucket["keywords"])},
            )

        return {
            "fileName": path.name,
            "rowCount": len(rows),
            "unmatchedRowCount": unmatched,
            "imported": imported,
            "fetchedCount": sum(int(item["fetchedCount"]) for item in imported),
            "acceptedCount": sum(int(item["acceptedCount"]) for item in imported),
        }

    def _safe_export_path(self, file_name: str) -> Path:
        if not file_name or Path(file_name).name != file_name or not file_name.endswith(".jsonl"):
            raise MediaCrawlerImportError("invalid MediaCrawler export file name")
        path = (self._data_root / file_name).resolve()
        if path.parent != self._data_root or not path.is_file():
            raise MediaCrawlerImportError("MediaCrawler export does not exist")
        if path.stat().st_size > self._max_file_bytes:
            raise MediaCrawlerImportError("MediaCrawler export exceeds size limit")
        return path

    @staticmethod
    def _load_rows(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        # Iterate physical JSONL records. ``str.splitlines`` also splits on
        # Unicode paragraph separators that may legitimately appear in notes.
        with path.open("r", encoding="utf-8") as lines:
            records = list(lines)
        for line_number, line in enumerate(records, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MediaCrawlerImportError(
                    f"invalid JSONL at line {line_number}",
                ) from exc
            if isinstance(item, dict):
                rows.append(item)
        return rows


def _to_review_source(item: dict[str, Any]) -> ReviewSource:
    note_id = str(item["note_id"]).strip()
    note_url = str(item.get("note_url") or "").strip()
    if not note_url.startswith("https://www.xiaohongshu.com/"):
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    published = _timestamp(item.get("time"))
    title = str(item.get("title") or item.get("desc") or "小红书旅行笔记").strip()
    description = str(item.get("desc") or "").strip()
    author = str(item.get("creator_hash") or item.get("nickname") or note_id).strip()
    return ReviewSource(
        id=f"xiaohongshu:{note_id}",
        platform="小红书",
        title=title[:100],
        excerpt=description[:500] or None,
        url=note_url,
        author=author[:128],
        publishedAt=published,
        likeCount=str(item.get("liked_count"))[:20] if item.get("liked_count") is not None else None,
        provider="mediacrawler_local",
    )


def _timestamp(value: Any) -> str | None:
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _normalize(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())
