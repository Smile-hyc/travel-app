from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from app.schemas.explore import PlaceSummary
from app.services.amap_poi_service import AmapPoiService


@dataclass(frozen=True)
class PopularPoiSeed:
    city: str
    name: str
    priority: int
    tier: str = "HOT"
    official_source_id: str | None = None


POPULAR_POI_SEEDS: tuple[PopularPoiSeed, ...] = (
    PopularPoiSeed("北京市", "故宫博物院", 100, official_source_id="dpm"),
    PopularPoiSeed("北京市", "八达岭长城", 98, official_source_id="badaling"),
    PopularPoiSeed("北京市", "颐和园", 96),
    PopularPoiSeed("北京市", "天坛公园", 94),
    PopularPoiSeed("上海市", "上海迪士尼度假区", 98, official_source_id="shanghai_disney"),
    PopularPoiSeed("上海市", "东方明珠广播电视塔", 91),
    PopularPoiSeed("西安市", "秦始皇帝陵博物院", 98, official_source_id="bmy"),
    PopularPoiSeed("西安市", "陕西历史博物馆", 95, official_source_id="sxhm"),
    PopularPoiSeed("成都市", "成都大熊猫繁育研究基地", 98, official_source_id="panda"),
    PopularPoiSeed("成都市", "武侯祠", 91),
    PopularPoiSeed("杭州市", "杭州西湖风景名胜区", 99, official_source_id="west_lake"),
    PopularPoiSeed("杭州市", "灵隐寺", 94),
    PopularPoiSeed("南京市", "中山陵", 94),
    PopularPoiSeed("南京市", "南京博物院", 93, official_source_id="njmuseum"),
    PopularPoiSeed("重庆市", "洪崖洞民俗风貌区", 96),
    PopularPoiSeed("苏州市", "拙政园", 94),
    PopularPoiSeed("黄山市", "黄山风景区", 99, official_source_id="huangshan"),
    PopularPoiSeed("九寨沟县", "九寨沟", 99, official_source_id="jiuzhai"),
    PopularPoiSeed("张家界市", "张家界国家森林公园", 98),
    PopularPoiSeed("厦门市", "鼓浪屿", 96),
    PopularPoiSeed("桂林市", "漓江风景名胜区", 96),
    PopularPoiSeed("三亚市", "亚龙湾", 92),
    PopularPoiSeed("长沙市", "岳麓山", 90),
    PopularPoiSeed("武汉市", "黄鹤楼", 93),
    PopularPoiSeed("开封市", "清明上河园", 90),
)


class PopularPoiCatalogService:
    def __init__(self, poi_service: AmapPoiService, *, concurrency: int = 4) -> None:
        self._poi_service = poi_service
        self._concurrency = max(1, min(concurrency, 8))

    @property
    def seeds(self) -> tuple[PopularPoiSeed, ...]:
        return POPULAR_POI_SEEDS

    async def resolve(
        self,
        seeds: list[PopularPoiSeed],
    ) -> tuple[list[tuple[PopularPoiSeed, PlaceSummary]], list[PopularPoiSeed]]:
        semaphore = asyncio.Semaphore(self._concurrency)

        async def resolve_one(seed: PopularPoiSeed):
            async with semaphore:
                try:
                    return seed, await self._resolve_one(seed)
                except Exception:
                    return seed, None

        pairs = await asyncio.gather(*(resolve_one(seed) for seed in seeds[:100]))
        resolved = [(seed, place) for seed, place in pairs if place is not None]
        missing = [seed for seed, place in pairs if place is None]
        return resolved, missing

    async def _resolve_one(self, seed: PopularPoiSeed) -> PlaceSummary | None:
        cities = await self._poi_service.search_cities(keyword=seed.city, limit=5)
        if not cities:
            return None
        result = await self._poi_service.search_pois(
            keyword=seed.name,
            adcode=cities[0].adCode,
            category="scenic",
            page=1,
            page_size=10,
            city_limit=True,
        )
        if not result.items:
            return None
        expected = _normalize(seed.name)
        ranked = sorted(
            result.items,
            key=lambda place: (
                _normalize(place.name) == expected,
                expected in _normalize(place.name) or _normalize(place.name) in expected,
                _rating(place.rating),
            ),
            reverse=True,
        )
        best = ranked[0]
        return best if _name_match_score(expected, _normalize(best.name)) >= 0.65 else None

    async def discover_city(self, city_name: str, *, limit: int = 12) -> list[PlaceSummary]:
        """Discover a city's popular scenic POIs for on-demand database bootstrap."""
        cities = await self._poi_service.search_cities(keyword=city_name, limit=5)
        if not cities:
            return []
        city = next((item for item in cities if _normalize(item.name) == _normalize(city_name)), cities[0])
        result = await self._poi_service.search_pois(
            keyword=None,
            adcode=city.adCode,
            category="scenic",
            page=1,
            page_size=max(1, min(limit, 25)),
            city_limit=True,
        )
        unique = {place.sourcePoiId: place for place in result.items}
        return sorted(
            unique.values(),
            key=lambda place: (_rating(place.rating), bool(place.images), place.name),
            reverse=True,
        )[: max(1, min(limit, 25))]


def seed_by_official_source(source_id: str) -> PopularPoiSeed | None:
    return next((seed for seed in POPULAR_POI_SEEDS if seed.official_source_id == source_id), None)


def _normalize(value: str) -> str:
    return re.sub(r"[\s·•,，。()（）\-_/]", "", value).lower()


def _name_match_score(expected: str, actual: str) -> float:
    if not expected or not actual:
        return 0.0
    if expected == actual:
        return 1.0
    if expected in actual or actual in expected:
        return min(len(expected), len(actual)) / max(len(expected), len(actual))
    shared = len(set(expected) & set(actual))
    return shared / max(len(set(expected)), 1)


def _rating(value: str | None) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0
