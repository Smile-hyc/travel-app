from fastapi import APIRouter, Depends

from app.main_state import get_amap_route_service
from app.schemas.routes import (
    DayRoutePlan,
    DayRouteRequest,
    OptimizeDayRouteRequest,
    OptimizeDayRouteResponse,
    RouteSegment,
    RouteSegmentRequest,
)
from app.services.amap_route_service import AmapRouteService

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/segment", response_model=RouteSegment)
async def calculate_segment(
    request: RouteSegmentRequest,
    service: AmapRouteService = Depends(get_amap_route_service),
) -> RouteSegment:
    return await service.segment(request)


@router.post("/day/calculate", response_model=DayRoutePlan)
async def calculate_day_route(
    request: DayRouteRequest,
    service: AmapRouteService = Depends(get_amap_route_service),
) -> DayRoutePlan:
    return await service.calculate_day(request)


@router.post("/day/optimize", response_model=OptimizeDayRouteResponse)
async def optimize_day_route(
    request: OptimizeDayRouteRequest,
    service: AmapRouteService = Depends(get_amap_route_service),
) -> OptimizeDayRouteResponse:
    return await service.optimize_day(request)
