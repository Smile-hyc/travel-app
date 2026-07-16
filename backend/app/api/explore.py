from fastapi import APIRouter, Query

from app.main_state import get_amap_poi_service, get_amap_weather_service
from app.schemas.explore import CitySearchResult, ExploreWeather, PaginatedPlaces, PlaceSuggestion

router = APIRouter(prefix="/api/explore", tags=["explore"])


@router.get("/cities/search", response_model=list[CitySearchResult])
async def search_cities(
    keyword: str = Query(..., min_length=1, max_length=60),
    limit: int = Query(12, ge=1, le=20),
) -> list[CitySearchResult]:
    service = get_amap_poi_service()
    return await service.search_cities(keyword=keyword, limit=limit)


@router.get("/input-tips", response_model=list[PlaceSuggestion])
async def input_tips(
    keyword: str = Query(..., min_length=1, max_length=60),
    adcode: str | None = Query(default=None, max_length=12),
    city_limit: bool = True,
    category: str | None = Query(default=None, max_length=32),
    latitude: float | None = None,
    longitude: float | None = None,
) -> list[PlaceSuggestion]:
    service = get_amap_poi_service()
    return await service.input_tips(
        keyword=keyword,
        adcode=adcode,
        category=category,
        city_limit=city_limit,
        latitude=latitude,
        longitude=longitude,
    )


@router.get("/pois/search", response_model=PaginatedPlaces)
async def search_pois(
    adcode: str = Query(..., min_length=4, max_length=12),
    category: str = Query(..., min_length=2, max_length=32),
    keyword: str | None = Query(default=None, max_length=60),
    page: int = Query(default=1, ge=1, le=50),
    page_size: int = Query(default=20, ge=1, le=30),
    city_limit: bool = True,
) -> PaginatedPlaces:
    service = get_amap_poi_service()
    return await service.search_pois(
        keyword=keyword,
        adcode=adcode,
        category=category,
        page=page,
        page_size=page_size,
        city_limit=city_limit,
    )


@router.get("/weather", response_model=ExploreWeather)
async def get_city_weather(
    adcode: str = Query(..., min_length=4, max_length=12),
) -> ExploreWeather:
    service = get_amap_weather_service()
    return await service.get_city_weather(adcode=adcode)
