import asyncio

from app.schemas.explore import CitySearchResult, PaginatedPlaces, PlaceSummary
from app.services.popular_poi_catalog import PopularPoiCatalogService, PopularPoiSeed


class FakePoiService:
    async def search_cities(self, **kwargs):
        return [CitySearchResult(id="city", name="北京市", adCode="110000", latitude=39.9, longitude=116.4)]

    async def search_pois(self, **kwargs):
        wrong = PlaceSummary(
            id="amap:wrong",
            sourcePoiId="wrong",
            name="故宫咖啡店",
            category="scenic",
            categoryCode="110000",
            rating="4.9",
        )
        right = PlaceSummary(
            id="amap:right",
            sourcePoiId="right",
            name="故宫博物院",
            category="scenic",
            categoryCode="110000",
            rating="4.8",
        )
        return PaginatedPlaces(items=[wrong, right], page=1, pageSize=10, total=2, hasMore=False)


def test_catalog_resolves_exact_amap_poi_over_similar_name() -> None:
    service = PopularPoiCatalogService(FakePoiService())
    resolved, missing = asyncio.run(service.resolve([PopularPoiSeed("北京市", "故宫博物院", 100)]))
    assert not missing
    assert resolved[0][1].sourcePoiId == "right"


def test_city_discovery_prioritizes_curated_seed_then_amap_order() -> None:
    service = PopularPoiCatalogService(FakePoiService())
    places = asyncio.run(service.discover_city("北京市", limit=2))
    assert [place.sourcePoiId for place in places] == ["right", "wrong"]
