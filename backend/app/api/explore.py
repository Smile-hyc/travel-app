import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.main_state import get_amap_poi_service, get_amap_weather_service, get_place_detail_service
from app.schemas.explore import (
    CitySearchResult,
    ExploreWeather,
    PaginatedPlaces,
    PlaceDetail,
    PlaceSuggestion,
    PlaceSummary,
    ReviewBatchRequest,
    ReviewBatchResponse,
    ReverseGeocodePoint,
)

router = APIRouter(prefix="/api/explore", tags=["explore"])


@router.get("/cities/search", response_model=list[CitySearchResult])
async def search_cities(
    keyword: str = Query(..., min_length=1, max_length=60),
    limit: int = Query(30, ge=1, le=40),
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


@router.get("/reverse-geocode", response_model=ReverseGeocodePoint)
async def reverse_geocode(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius: int = Query(default=50, ge=1, le=1000),
) -> ReverseGeocodePoint:
    service = get_amap_poi_service()
    return await service.reverse_geocode(
        latitude=latitude,
        longitude=longitude,
        radius=radius,
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


@router.post("/pois/detail", response_model=PlaceDetail)
async def get_place_detail(place: PlaceSummary) -> PlaceDetail:
    """Return facts immediately and enqueue missing experience evidence."""
    service = get_place_detail_service()
    return await service.get_detail(place)


@router.post("/reviews/batch", response_model=ReviewBatchResponse, status_code=202)
async def prepare_place_reviews(request: ReviewBatchRequest) -> ReviewBatchResponse:
    """Upsert 1-30 final itinerary POIs and enqueue one bounded enrichment batch."""
    service = get_place_detail_service()
    return await service.ensure_batch(request.places, force_refresh=request.forceRefresh)


@router.get("/reviews/batches/{batch_id}/events")
async def stream_place_review_events(batch_id: str) -> StreamingResponse:
    """Stream cache/enrichment changes without holding up itinerary generation."""
    service = get_place_detail_service()
    if service.get_batch(batch_id) is None:
        raise HTTPException(status_code=404, detail="评价批次不存在或已过期。")

    async def event_stream():
        async for event in service.stream_batch(batch_id):
            payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
            yield f"event: review\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/weather", response_model=ExploreWeather)
async def get_city_weather(
    adcode: str = Query(..., min_length=4, max_length=12),
) -> ExploreWeather:
    service = get_amap_weather_service()
    return await service.get_city_weather(adcode=adcode)
