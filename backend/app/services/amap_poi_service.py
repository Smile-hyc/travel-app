from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from app.schemas.explore import CitySearchResult, PaginatedPlaces, PlaceImage, PlaceSuggestion, PlaceSummary
from app.services.amap_categories import get_amap_category
from app.services.amap_client import AmapClient
from app.services.simple_cache import TtlCache

MAX_PAGE_SIZE = 30
MAX_KEYWORD_LENGTH = 60
MAX_PLACE_IMAGES = 10


class AmapPoiService:
    def __init__(self, client: AmapClient) -> None:
        self._client = client
        self._places_cache: TtlCache[PaginatedPlaces] = TtlCache(max_items=256)
        self._tips_cache: TtlCache[list[PlaceSuggestion]] = TtlCache(max_items=256)
        self._city_cache: TtlCache[list[CitySearchResult]] = TtlCache(max_items=128)

    async def search_cities(self, *, keyword: str, limit: int = 12) -> list[CitySearchResult]:
        keyword = keyword.strip()
        if len(keyword) < 2:
            return []
        keyword = keyword[:MAX_KEYWORD_LENGTH]
        limit = min(max(limit, 1), 20)
        cache_key = ("cities", keyword, limit)
        cached = self._city_cache.get(cache_key)
        if cached is not None:
            return cached

        results = await self._search_cities_by_district(keyword, limit)
        if not results:
            results = await self._search_cities_by_geocode(keyword, limit)

        self._city_cache.set(cache_key, results, ttl_seconds=3600)
        return results

    async def _search_cities_by_district(self, keyword: str, limit: int) -> list[CitySearchResult]:
        payload = await self._client.get(
            "/v3/config/district",
            {
                "keywords": keyword,
                "subdistrict": 0,
                "extensions": "base",
                "page": 1,
                "offset": limit,
            },
        )
        districts = payload.get("districts", [])
        results: list[CitySearchResult] = []
        for item in districts:
            if not isinstance(item, dict):
                continue
            city = _parse_city_result(item)
            if city is not None:
                results.append(city)
        return _dedupe_cities(results)[:limit]

    async def _search_cities_by_geocode(self, keyword: str, limit: int) -> list[CitySearchResult]:
        payload = await self._client.get(
            "/v3/geocode/geo",
            {
                "address": keyword,
                "city": "",
                "batch": "false",
            },
        )
        geocodes = payload.get("geocodes", [])
        results: list[CitySearchResult] = []
        for item in geocodes:
            if not isinstance(item, dict):
                continue
            city = _parse_city_result(item)
            if city is not None:
                results.append(city)
        return _dedupe_cities(results)[:limit]

    async def input_tips(
        self,
        *,
        keyword: str,
        adcode: str | None,
        category: str | None,
        city_limit: bool,
        latitude: float | None,
        longitude: float | None,
    ) -> list[PlaceSuggestion]:
        keyword = keyword.strip()
        if len(keyword) < 2:
            return []
        keyword = keyword[:MAX_KEYWORD_LENGTH]
        category_mapping = get_amap_category(category) if category else None
        cache_key = ("tips", keyword, adcode or "", category or "", city_limit, latitude, longitude)
        cached = self._tips_cache.get(cache_key)
        if cached is not None:
            return cached

        params: dict[str, Any] = {
            "keywords": keyword,
            "datatype": "poi",
            "citylimit": str(city_limit).lower(),
        }
        if adcode:
            params["city"] = _normalize_amap_city_adcode(adcode)
        if category_mapping:
            params["type"] = category_mapping.type_codes
        if latitude is not None and longitude is not None:
            params["location"] = f"{longitude},{latitude}"

        payload = await self._client.get("/v3/assistant/inputtips", params)
        tips = [_parse_suggestion(item) for item in payload.get("tips", []) if isinstance(item, dict)]
        self._tips_cache.set(cache_key, tips, ttl_seconds=45)
        return tips

    async def search_pois(
        self,
        *,
        keyword: str | None,
        adcode: str,
        category: str,
        page: int,
        page_size: int,
        city_limit: bool,
    ) -> PaginatedPlaces:
        category_mapping = get_amap_category(category)
        if category_mapping is None:
            raise HTTPException(status_code=422, detail="不支持的地点分类。")

        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        clean_keyword = (keyword or "").strip()[:MAX_KEYWORD_LENGTH]
        effective_keyword = clean_keyword or category_mapping.keyword
        normalized_adcode = _normalize_amap_city_adcode(adcode)
        cache_key = ("search", effective_keyword, normalized_adcode, category, page, page_size, city_limit)
        cached = self._places_cache.get(cache_key)
        if cached is not None:
            return cached

        params: dict[str, Any] = {
            "keywords": effective_keyword,
            "types": category_mapping.type_codes,
            "city": normalized_adcode,
            "citylimit": str(city_limit).lower(),
            "offset": page_size,
            "page": page,
            "extensions": "all",
        }
        payload = await self._client.get("/v3/place/text", params)
        total = _safe_int(payload.get("count"))
        items = [
            _parse_place(item, category=category, category_code=category_mapping.code)
            for item in payload.get("pois", [])
            if isinstance(item, dict)
        ]
        response = PaginatedPlaces(
            items=items,
            page=page,
            pageSize=page_size,
            total=total,
            hasMore=page * page_size < total,
        )
        self._places_cache.set(cache_key, response, ttl_seconds=180 if clean_keyword else 300)
        return response


def _parse_place(raw: dict[str, Any], *, category: str, category_code: str) -> PlaceSummary:
    longitude, latitude = _parse_location(raw.get("location"))
    biz_ext = raw.get("biz_ext") if isinstance(raw.get("biz_ext"), dict) else {}
    photos = raw.get("photos") if isinstance(raw.get("photos"), list) else []
    source_poi_id = _clean_string(raw.get("id")) or _clean_string(raw.get("name")) or "unknown"
    images = _parse_place_images(photos, source_poi_id=source_poi_id, place_name=_clean_string(raw.get("name")))
    return PlaceSummary(
        id=f"amap:{source_poi_id}",
        source="AMAP",
        sourcePoiId=source_poi_id,
        name=_clean_string(raw.get("name")) or "未命名地点",
        category=category,
        categoryCode=category_code,
        typeName=_clean_string(raw.get("type")),
        typeCode=_clean_string(raw.get("typecode")),
        address=_clean_string(raw.get("address")),
        provinceName=_clean_string(raw.get("pname")),
        cityName=_clean_string(raw.get("cityname")),
        districtName=_clean_string(raw.get("adname")),
        adCode=_clean_string(raw.get("adcode")),
        cityCode=_clean_string(raw.get("citycode")),
        latitude=latitude,
        longitude=longitude,
        distanceMeters=_safe_int_or_none(raw.get("distance")),
        phone=_clean_string(raw.get("tel")),
        rating=_clean_string(biz_ext.get("rating")),
        costAverage=_clean_string(biz_ext.get("cost")),
        images=images,
        coverImageUrl=images[0].url if images else None,
        imageUrls=[image.url for image in images],
        businessArea=_clean_string(raw.get("business_area")),
    )


def _parse_place_images(
    photos: list[Any],
    *,
    source_poi_id: str,
    place_name: str | None,
) -> list[PlaceImage]:
    images: list[PlaceImage] = []
    seen: set[str] = set()
    for photo in photos:
        if not isinstance(photo, dict):
            continue
        url = _clean_image_url(photo.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        images.append(
            PlaceImage(
                id=f"amap-photo:{source_poi_id}:{len(images) + 1}",
                url=url,
                thumbnailUrl=url,
                title=_clean_string(photo.get("title")) or place_name,
                isPrimary=len(images) == 0,
            ),
        )
        if len(images) >= MAX_PLACE_IMAGES:
            break
    return images


def _clean_image_url(value: Any) -> str | None:
    url = _clean_string(value)
    if not url or len(url) > 2048:
        return None
    lowered = url.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return None
    return url


def _parse_suggestion(raw: dict[str, Any]) -> PlaceSuggestion:
    longitude, latitude = _parse_location(raw.get("location"))
    tip_id = _clean_string(raw.get("id")) or _clean_string(raw.get("name")) or "unknown"
    return PlaceSuggestion(
        id=f"amap-tip:{tip_id}",
        name=_clean_string(raw.get("name")) or "未命名地点",
        district=_clean_string(raw.get("district")),
        address=_clean_string(raw.get("address")),
        cityName=_clean_string(raw.get("city")),
        adCode=_clean_string(raw.get("adcode")),
        typeCode=_clean_string(raw.get("typecode")),
        latitude=latitude,
        longitude=longitude,
        hasLocation=latitude is not None and longitude is not None,
    )


def _parse_city_result(raw: dict[str, Any]) -> CitySearchResult | None:
    longitude, latitude = _parse_location(raw.get("center") or raw.get("location"))
    adcode = _clean_string(raw.get("adcode"))
    name = (
        _clean_string(raw.get("name"))
        or _clean_string(raw.get("city"))
        or _clean_string(raw.get("formatted_address"))
    )
    if latitude is None or longitude is None or not adcode or not name:
        return None

    province = _clean_string(raw.get("province"))
    if province == "[]":
        province = None

    normalized_name = name
    if not normalized_name.endswith(("市", "区", "县", "州", "盟")) and raw.get("level") in {"city", "province"}:
        normalized_name = f"{normalized_name}市"

    normalized_adcode = _normalize_amap_city_adcode(adcode)

    return CitySearchResult(
        id=f"amap-city:{normalized_adcode}:{normalized_name}",
        name=normalized_name,
        provinceName=province,
        adCode=normalized_adcode,
        latitude=latitude,
        longitude=longitude,
        defaultZoom=13.2,
    )


def _dedupe_cities(cities: list[CitySearchResult]) -> list[CitySearchResult]:
    seen: set[tuple[str, str]] = set()
    result: list[CitySearchResult] = []
    for city in cities:
        key = (city.adCode, city.name)
        if key in seen:
            continue
        seen.add(key)
        result.append(city)
    return result


def _normalize_amap_city_adcode(adcode: str) -> str:
    return {
        "110100": "110000",
        "120100": "120000",
        "310100": "310000",
        "500100": "500000",
    }.get(adcode, adcode)


def _parse_location(value: Any) -> tuple[float | None, float | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    parts = value.split(",")
    if len(parts) != 2:
        return None, None
    try:
        longitude = float(parts[0])
        latitude = float(parts[1])
    except ValueError:
        return None, None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None, None
    return longitude, latitude


def _clean_string(value: Any) -> str | None:
    if value is None or value == []:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int:
    return _safe_int_or_none(value) or 0


def _safe_int_or_none(value: Any) -> int | None:
    if value is None or value == []:
        return None
    match = re.search(r"\d+", str(value))
    if not match:
        return None
    return int(match.group(0))
