from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from app.schemas.explore import (
    CitySearchResult,
    PaginatedPlaces,
    PlaceImage,
    PlaceSuggestion,
    PlaceSummary,
    ReverseGeocodePoint,
)
from app.services.amap_categories import get_amap_category
from app.services.amap_client import AmapClient
from app.services.simple_cache import TtlCache

MAX_PAGE_SIZE = 30
MAX_KEYWORD_LENGTH = 60
MAX_PLACE_IMAGES = 10
DIRECT_MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}
PROVINCE_NAMES_BY_ADCODE_PREFIX = {
    "11": "北京市", "12": "天津市", "13": "河北省", "14": "山西省", "15": "内蒙古自治区",
    "21": "辽宁省", "22": "吉林省", "23": "黑龙江省", "31": "上海市", "32": "江苏省",
    "33": "浙江省", "34": "安徽省", "35": "福建省", "36": "江西省", "37": "山东省",
    "41": "河南省", "42": "湖北省", "43": "湖南省", "44": "广东省", "45": "广西壮族自治区",
    "46": "海南省", "50": "重庆市", "51": "四川省", "52": "贵州省", "53": "云南省",
    "54": "西藏自治区", "61": "陕西省", "62": "甘肃省", "63": "青海省", "64": "宁夏回族自治区",
    "65": "新疆维吾尔自治区", "71": "台湾省", "81": "香港特别行政区", "82": "澳门特别行政区",
}


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
        limit = min(max(limit, 1), 40)
        cache_key = ("cities", keyword, limit)
        cached = self._city_cache.get(cache_key)
        if cached is not None:
            return cached

        results = await self._search_cities_by_district(keyword, limit)
        if not results:
            results = await self._search_cities_by_geocode(keyword, limit)

        self._city_cache.set(cache_key, results, ttl_seconds=3600)
        return results

    async def list_prefecture_cities(self) -> list[CitySearchResult]:
        """Return mainland prefecture-level destinations and municipalities.

        The district endpoint is used only to build the collection queue.  A
        city remains keyed by its AMap adcode, so rerunning this discovery is
        idempotent even when administrative names change.
        """
        cache_key = ("prefecture-cities",)
        cached = self._city_cache.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._client.get(
            "/v3/config/district",
            {
                "keywords": "中华人民共和国",
                "subdistrict": 2,
                "extensions": "base",
            },
        )
        results: list[CitySearchResult] = []
        roots = payload.get("districts", [])
        for root in roots if isinstance(roots, list) else []:
            if not isinstance(root, dict):
                continue
            provinces = root.get("districts", [])
            for province in provinces if isinstance(provinces, list) else []:
                if not isinstance(province, dict):
                    continue
                province_name = _clean_string(province.get("name"))
                if province_name in DIRECT_MUNICIPALITIES:
                    city = _parse_city_result({**province, "province": province_name})
                    if city is not None:
                        results.append(city)
                    continue
                children = province.get("districts", [])
                for child in children if isinstance(children, list) else []:
                    if not isinstance(child, dict) or child.get("level") != "city":
                        continue
                    city = _parse_city_result({**child, "province": province_name})
                    if city is not None:
                        results.append(city)

        results = sorted(_dedupe_cities(results), key=lambda item: (item.adCode, item.name))
        self._city_cache.set(cache_key, results, ttl_seconds=86400)
        return results

    async def _search_cities_by_district(self, keyword: str, limit: int) -> list[CitySearchResult]:
        payload = await self._client.get(
            "/v3/config/district",
            {
                "keywords": keyword,
                "subdistrict": 1,
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
            name = _clean_string(item.get("name")) or ""
            level = _clean_string(item.get("level")) or ""
            # A province is a grouping choice rather than an itinerary
            # destination. Return its prefecture-level cities so the client can
            # ask the user to choose the actual destination. Direct-controlled
            # municipalities remain one selectable city instead of exposing
            # their districts as peer destinations.
            if level == "province" and name not in DIRECT_MUNICIPALITIES:
                children = item.get("districts") if isinstance(item.get("districts"), list) else []
                for child in children:
                    if not isinstance(child, dict) or child.get("level") != "city":
                        continue
                    enriched = {**child, "province": name}
                    city = _parse_city_result(enriched)
                    if city is not None:
                        results.append(city)
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

    async def reverse_geocode(
        self,
        *,
        latitude: float,
        longitude: float,
        radius: int = 50,
    ) -> ReverseGeocodePoint:
        payload = await self._client.get(
            "/v3/geocode/regeo",
            {
                "location": f"{longitude:.6f},{latitude:.6f}",
                "radius": min(max(radius, 1), 1000),
                "extensions": "all",
                "roadlevel": 0,
            },
        )
        regeocode = payload.get("regeocode")
        if not isinstance(regeocode, dict):
            raise HTTPException(status_code=502, detail="高德未返回该位置的地址信息，请稍后重试。")

        component = regeocode.get("addressComponent")
        component = component if isinstance(component, dict) else {}
        province = _clean_string(component.get("province"))
        city = _clean_string(component.get("city"))
        if not city and province in DIRECT_MUNICIPALITIES:
            city = province
        district = _clean_string(component.get("district"))
        adcode = _clean_string(component.get("adcode"))
        formatted_address = _clean_string(regeocode.get("formatted_address"))
        if not formatted_address:
            street_number = component.get("streetNumber")
            street_number = street_number if isinstance(street_number, dict) else {}
            formatted_address = "".join(
                filter(
                    None,
                    (
                        province,
                        city if city != province else None,
                        district,
                        _clean_string(component.get("township")),
                        _clean_string(street_number.get("street")),
                        _clean_string(street_number.get("number")),
                    ),
                )
            )

        nearby_pois: list[tuple[float, dict[str, Any]]] = []
        for poi in regeocode.get("pois", []):
            if not isinstance(poi, dict):
                continue
            distance = _safe_float_or_none(poi.get("distance"))
            if distance is not None and distance < 50:
                nearby_pois.append((distance, poi))
        nearby_pois.sort(key=lambda item: item[0])
        nearest_distance, nearest_poi = nearby_pois[0] if nearby_pois else (None, None)
        poi_name = _clean_string(nearest_poi.get("name")) if nearest_poi else None
        display_name = poi_name or formatted_address or "地图选定位置"

        return ReverseGeocodePoint(
            name=display_name,
            formattedAddress=formatted_address or display_name,
            provinceName=province,
            cityName=city,
            districtName=district,
            adCode=adcode,
            latitude=latitude,
            longitude=longitude,
            matchedPoiWithin50m=nearest_poi is not None,
            distanceMeters=round(nearest_distance) if nearest_distance is not None else None,
        )

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

        if category == "transport" and adcode:
            tips = await self._transport_hub_suggestions(
                keyword=keyword,
                adcode=adcode,
                city_limit=city_limit,
            )
            self._tips_cache.set(cache_key, tips, ttl_seconds=180)
            return tips

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
        if city_limit and adcode:
            tips = [tip for tip in tips if tip.adCode and _adcode_belongs_to_city(tip.adCode, adcode)]
        self._tips_cache.set(cache_key, tips, ttl_seconds=45)
        return tips

    async def _transport_hub_suggestions(
        self,
        *,
        keyword: str,
        adcode: str,
        city_limit: bool,
    ) -> list[PlaceSuggestion]:
        default_request = keyword in {"交通枢纽", "火车站|机场"}
        search_keywords = ("火车站", "高铁站", "机场") if default_request else (keyword,)
        places: list[PlaceSummary] = []
        for search_keyword in search_keywords:
            page = await self.search_pois(
                keyword=search_keyword,
                adcode=adcode,
                category="transport",
                page=1,
                page_size=30,
                city_limit=city_limit,
            )
            places.extend(page.items)
        deduped: list[PlaceSummary] = []
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        for place in places:
            normalized_name = re.sub(r"[\s·()（）-]", "", place.name)
            if place.sourcePoiId in seen_ids or normalized_name in seen_names:
                continue
            seen_ids.add(place.sourcePoiId)
            seen_names.add(normalized_name)
            deduped.append(place)
        candidates = [
            place
            for place in deduped
            if place.adCode
            and _adcode_belongs_to_city(place.adCode, adcode)
            and _is_railway_or_airport(place)
        ]
        candidates.sort(key=lambda place: _transport_hub_rank(place, keyword))
        return [_place_to_suggestion(place) for place in candidates[:30]]

    async def search_nearby_pois(
        self,
        *,
        latitude: float,
        longitude: float,
        adcode: str,
        category: str,
        keyword: str | None = None,
        radius_meters: int = 2500,
        page_size: int = 20,
    ) -> list[PlaceSummary]:
        category_mapping = get_amap_category(category)
        if category_mapping is None:
            raise HTTPException(status_code=422, detail="不支持的地点分类。")
        radius_meters = min(max(radius_meters, 200), 5000)
        page_size = min(max(page_size, 1), 25)
        normalized_adcode = _normalize_amap_city_adcode(adcode)
        clean_keyword = (keyword or "").strip()[:MAX_KEYWORD_LENGTH]
        cache_key = (
            "nearby",
            round(latitude, 3),
            round(longitude, 3),
            normalized_adcode,
            category,
            clean_keyword,
            radius_meters,
            page_size,
        )
        cached = self._places_cache.get(cache_key)
        if cached is not None:
            return cached.items
        params: dict[str, Any] = {
            "location": f"{longitude:.6f},{latitude:.6f}",
            "radius": radius_meters,
            "types": category_mapping.type_codes,
            "region": normalized_adcode,
            "city_limit": "true",
            "sortrule": "distance",
            "page_size": page_size,
            "page_num": 1,
            "show_fields": "business,photos",
        }
        if clean_keyword:
            params["keywords"] = clean_keyword
        try:
            payload = await self._client.get("/v5/place/around", params)
        except HTTPException:
            payload = await self._client.get(
                "/v3/place/around",
                {
                    "location": params["location"],
                    "radius": radius_meters,
                    "types": category_mapping.type_codes,
                    "city": normalized_adcode,
                    "keywords": clean_keyword,
                    "sortrule": "distance",
                    "offset": page_size,
                    "page": 1,
                    "extensions": "all",
                },
            )
        items = [
            _parse_place(item, category=category, category_code=category_mapping.code)
            for item in payload.get("pois", [])
            if isinstance(item, dict)
        ]
        response = PaginatedPlaces(
            items=items,
            page=1,
            pageSize=page_size,
            total=_safe_int(payload.get("count")),
            hasMore=False,
        )
        self._places_cache.set(cache_key, response, ttl_seconds=180)
        return items
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
            "region": normalized_adcode,
            "city_limit": str(city_limit).lower(),
            "page_size": min(page_size, 25),
            "page_num": page,
            "show_fields": "business,photos",
        }
        try:
            payload = await self._client.get("/v5/place/text", params)
        except HTTPException:
            # POI 2.0 may be unavailable for some Web service keys. Keep the
            # existing v3 path as a graceful fallback; opening hours will then
            # be marked as unverified instead of invented.
            payload = await self._client.get(
                "/v3/place/text",
                {
                    "keywords": effective_keyword,
                    "types": category_mapping.type_codes,
                    "city": normalized_adcode,
                    "citylimit": str(city_limit).lower(),
                    "offset": page_size,
                    "page": page,
                    "extensions": "all",
                },
            )
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
    business = raw.get("business") if isinstance(raw.get("business"), dict) else {}
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
        phone=_clean_string(business.get("tel")) or _clean_string(raw.get("tel")),
        rating=_clean_string(business.get("rating")) or _clean_string(biz_ext.get("rating")),
        costAverage=_clean_string(business.get("cost")) or _clean_string(biz_ext.get("cost")),
        images=images,
        coverImageUrl=images[0].url if images else None,
        imageUrls=[image.url for image in images],
        businessArea=_clean_string(business.get("business_area")) or _clean_string(raw.get("business_area")),
        openingHoursToday=_clean_string(business.get("opentime_today")),
        openingHoursWeek=_clean_string(business.get("opentime_week")),
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


def _place_to_suggestion(place: PlaceSummary) -> PlaceSuggestion:
    return PlaceSuggestion(
        id=place.id,
        name=place.name,
        district=place.districtName,
        address=place.address,
        cityName=place.cityName,
        adCode=place.adCode,
        typeCode=place.typeCode,
        latitude=place.latitude,
        longitude=place.longitude,
        hasLocation=place.latitude is not None and place.longitude is not None,
    )


def _is_railway_or_airport(place: PlaceSummary) -> bool:
    text = f"{place.name} {place.typeName or ''}"
    if any(
        word in text
        for word in (
            "地铁", "公交", "客运站", "停车场", "收费站", "加油站", "码头", "货运",
            "建设中", "暂停营业", "停止营业", "已关闭",
        )
    ):
        return False
    return any(word in text for word in ("机场", "航站楼", "火车站", "高铁站", "铁路车站")) or (
        place.name.endswith("站") and (place.typeCode or "").startswith("1502")
    )


def _transport_hub_rank(place: PlaceSummary, keyword: str) -> tuple[int, int, int, int, str]:
    compact_keyword = re.sub(r"[\s|]", "", keyword)
    exact_match = bool(compact_keyword and compact_keyword in re.sub(r"\s", "", place.name))
    name = place.name
    if name.endswith("机场") or (name.endswith("站") and not any(word in name for word in ("地铁", "公交"))):
        hub_level = 0
    elif "航站楼" in name:
        hub_level = 1
    else:
        hub_level = 2
    city_token = (place.cityName or "").removesuffix("市")
    named_for_city = bool(city_token and name.startswith(city_token))
    type_priority = 0 if (place.typeCode or "").startswith(("1501", "1502")) else 1
    return (0 if exact_match else 1, 0 if named_for_city else 1, hub_level, type_priority, name)


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

    province = _clean_string(raw.get("province")) or PROVINCE_NAMES_BY_ADCODE_PREFIX.get(adcode[:2])
    if province == "[]":
        province = None

    normalized_name = name
    if not normalized_name.endswith(("市", "区", "县", "州", "盟")) and raw.get("level") in {"city", "province"}:
        normalized_name = f"{normalized_name}市"

    normalized_adcode = _normalize_amap_city_adcode(adcode)
    municipality_name = PROVINCE_NAMES_BY_ADCODE_PREFIX.get(normalized_adcode[:2])
    if normalized_adcode[:2] in {"11", "12", "31", "50"} and municipality_name:
        normalized_name = municipality_name
        province = municipality_name

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
    seen: set[str] = set()
    result: list[CitySearchResult] = []
    for city in cities:
        key = _normalize_amap_city_adcode(city.adCode)
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


def _adcode_belongs_to_city(candidate: str, selected: str) -> bool:
    candidate = _normalize_amap_city_adcode(candidate.strip())
    selected = _normalize_amap_city_adcode(selected.strip())
    if len(candidate) < 6 or len(selected) < 6:
        return candidate == selected
    if selected.endswith("0000"):
        return candidate[:2] == selected[:2]
    if selected.endswith("00"):
        return candidate[:4] == selected[:4]
    return candidate == selected


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


def _safe_float_or_none(value: Any) -> float | None:
    if value is None or value == []:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
