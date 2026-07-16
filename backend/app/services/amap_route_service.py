from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.schemas.routes import (
    DayRoutePlan,
    DayRouteRequest,
    OptimizeDayRouteRequest,
    OptimizeDayRouteResponse,
    RouteCoordinate,
    RouteMode,
    RoutePlace,
    RouteSegment,
    RouteSegmentRequest,
    RouteStep,
)
from app.services.amap_client import AmapClient
from app.services.route_optimizer import optimize_place_order
from app.services.simple_cache import TtlCache

MAX_DAY_PLACES = 15


class AmapRouteService:
    def __init__(self, client: AmapClient) -> None:
        self._client = client
        self._segment_cache: TtlCache[RouteSegment] = TtlCache(max_items=512)

    async def segment(self, request: RouteSegmentRequest) -> RouteSegment:
        _validate_place(request.origin)
        _validate_place(request.destination)
        cache_key = (
            request.mode,
            request.origin.latitude,
            request.origin.longitude,
            request.destination.latitude,
            request.destination.longitude,
            request.origin.cityCode or request.origin.adCode or "",
            request.destination.cityCode or request.destination.adCode or "",
        )
        cached = self._segment_cache.get(cache_key)
        if cached is not None:
            return cached

        if request.mode == "walking":
            segment = await self._walking(request.origin, request.destination)
        elif request.mode == "driving":
            segment = await self._driving(request.origin, request.destination)
        elif request.mode == "transit":
            segment = await self._transit(request.origin, request.destination)
        elif request.mode == "cycling":
            segment = await self._cycling(request.origin, request.destination)
        else:
            raise HTTPException(status_code=422, detail="不支持的路线方式。")

        self._segment_cache.set(cache_key, segment, ttl_seconds=300)
        return segment

    async def calculate_day(self, request: DayRouteRequest) -> DayRoutePlan:
        _validate_day_places(request.places)
        segments: list[RouteSegment] = []
        for origin, destination in zip(request.places, request.places[1:]):
            segments.append(
                await self.segment(
                    RouteSegmentRequest(origin=origin, destination=destination, mode=request.mode),
                ),
            )
        return _build_day_plan(request.places, request.mode, segments)

    async def optimize_day(self, request: OptimizeDayRouteRequest) -> OptimizeDayRouteResponse:
        _validate_day_places(request.places)
        original_ids = [place.id for place in request.places]
        optimized_places = optimize_place_order(request.places)
        optimized_ids = [place.id for place in optimized_places]
        route = await self.calculate_day(DayRouteRequest(places=optimized_places, mode=request.mode))
        warning = None
        if len(request.places) > 8:
            warning = "9 个以上地点使用轻量优化算法，结果适合作为初版行程参考。"
        return OptimizeDayRouteResponse(
            originalPlaceIds=original_ids,
            optimizedPlaceIds=optimized_ids,
            optimizedPlaces=optimized_places,
            route=route,
            changed=original_ids != optimized_ids,
            warning=warning,
        )

    async def _walking(self, origin: RoutePlace, destination: RoutePlace) -> RouteSegment:
        payload = await self._client.get(
            "/v3/direction/walking",
            {
                "origin": _coord_param(origin),
                "destination": _coord_param(destination),
            },
        )
        return _segment_from_path(origin, destination, "walking", _first_path(payload))

    async def _driving(self, origin: RoutePlace, destination: RoutePlace) -> RouteSegment:
        payload = await self._client.get(
            "/v3/direction/driving",
            {
                "origin": _coord_param(origin),
                "destination": _coord_param(destination),
                "extensions": "base",
            },
        )
        return _segment_from_path(origin, destination, "driving", _first_path(payload))

    async def _cycling(self, origin: RoutePlace, destination: RoutePlace) -> RouteSegment:
        # 高德 Web 服务骑行接口返回结构和 v3 略有差异。为了避免额外 Key 暴露，
        # 仍通过同一个 AmapClient 代理；如果用户 Key 未开通，错误会在这里被友好抛出。
        payload = await self._client.get_raw(
            "/v4/direction/bicycling",
            {
                "origin": _coord_param(origin),
                "destination": _coord_param(destination),
            },
        )
        if str(payload.get("errcode", "0")) not in {"0", ""}:
            raise HTTPException(status_code=502, detail="高德骑行路线服务暂时不可用。")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        paths = data.get("paths") if isinstance(data.get("paths"), list) else []
        if not paths:
            raise HTTPException(status_code=502, detail="高德暂未返回可用骑行路线。")
        return _segment_from_path(origin, destination, "cycling", paths[0])

    async def _transit(self, origin: RoutePlace, destination: RoutePlace) -> RouteSegment:
        city = origin.cityCode or origin.adCode or origin.cityName or destination.cityCode or destination.adCode
        if not city:
            raise HTTPException(status_code=422, detail="公交路线需要城市编码或城市名称。")
        payload = await self._client.get(
            "/v3/direction/transit/integrated",
            {
                "origin": _coord_param(origin),
                "destination": _coord_param(destination),
                "city": city,
                "cityd": destination.cityCode or destination.adCode or destination.cityName or city,
                "extensions": "base",
            },
        )
        route = payload.get("route") if isinstance(payload.get("route"), dict) else {}
        transits = route.get("transits") if isinstance(route.get("transits"), list) else []
        if not transits:
            raise HTTPException(status_code=502, detail="高德暂未返回可用公交路线。")
        transit = transits[0]
        steps = _parse_transit_steps(transit)
        polyline = [point for step in steps for point in step.polyline]
        return RouteSegment(
            originId=origin.id,
            destinationId=destination.id,
            originName=origin.name,
            destinationName=destination.name,
            mode="transit",
            distanceMeters=_safe_int(transit.get("distance")),
            durationSeconds=_safe_int(transit.get("duration")),
            polyline=polyline,
            steps=steps,
        )


def _validate_day_places(places: list[RoutePlace]) -> None:
    if len(places) > MAX_DAY_PLACES:
        raise HTTPException(status_code=422, detail=f"单日最多支持 {MAX_DAY_PLACES} 个地点参与路线计算。")
    for place in places:
        _validate_place(place)


def _validate_place(place: RoutePlace) -> None:
    if not (-90 <= place.latitude <= 90 and -180 <= place.longitude <= 180):
        raise HTTPException(status_code=422, detail=f"{place.name} 的经纬度无效，无法规划路线。")


def _build_day_plan(places: list[RoutePlace], mode: RouteMode, segments: list[RouteSegment]) -> DayRoutePlan:
    return DayRoutePlan(
        places=places,
        segments=segments,
        totalDistanceMeters=sum(segment.distanceMeters for segment in segments),
        totalDurationSeconds=sum(segment.durationSeconds for segment in segments),
        mode=mode,
    )


def _coord_param(place: RoutePlace) -> str:
    return f"{place.longitude},{place.latitude}"


def _first_path(payload: dict[str, Any]) -> dict[str, Any]:
    route = payload.get("route") if isinstance(payload.get("route"), dict) else {}
    paths = route.get("paths") if isinstance(route.get("paths"), list) else []
    if not paths:
        raise HTTPException(status_code=502, detail="高德暂未返回可用路线。")
    return paths[0]


def _segment_from_path(origin: RoutePlace, destination: RoutePlace, mode: RouteMode, path: dict[str, Any]) -> RouteSegment:
    steps = _parse_steps(path.get("steps"))
    polyline = [point for step in steps for point in step.polyline]
    return RouteSegment(
        originId=origin.id,
        destinationId=destination.id,
        originName=origin.name,
        destinationName=destination.name,
        mode=mode,
        distanceMeters=_safe_int(path.get("distance")),
        durationSeconds=_safe_int(path.get("duration")),
        polyline=polyline,
        steps=steps,
    )


def _parse_steps(raw_steps: Any) -> list[RouteStep]:
    if not isinstance(raw_steps, list):
        return []
    result: list[RouteStep] = []
    for item in raw_steps:
        if not isinstance(item, dict):
            continue
        result.append(
            RouteStep(
                instruction=_clean_string(item.get("instruction")),
                distanceMeters=_safe_int_or_none(item.get("distance")),
                durationSeconds=_safe_int_or_none(item.get("duration")),
                polyline=_parse_polyline(item.get("polyline")),
            ),
        )
    return result


def _parse_transit_steps(transit: dict[str, Any]) -> list[RouteStep]:
    segments = transit.get("segments") if isinstance(transit.get("segments"), list) else []
    steps: list[RouteStep] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        walking = segment.get("walking") if isinstance(segment.get("walking"), dict) else {}
        steps.extend(_parse_steps(walking.get("steps")))
        bus = segment.get("bus") if isinstance(segment.get("bus"), dict) else {}
        buslines = bus.get("buslines") if isinstance(bus.get("buslines"), list) else []
        for busline in buslines:
            if not isinstance(busline, dict):
                continue
            steps.append(
                RouteStep(
                    instruction=_clean_string(busline.get("name")),
                    distanceMeters=_safe_int_or_none(busline.get("distance")),
                    durationSeconds=_safe_int_or_none(busline.get("duration")),
                    polyline=_parse_polyline(busline.get("polyline")),
                ),
            )
    return steps


def _parse_polyline(value: Any) -> list[RouteCoordinate]:
    if not isinstance(value, str) or not value.strip():
        return []
    points: list[RouteCoordinate] = []
    for pair in value.split(";"):
        parts = pair.split(",")
        if len(parts) != 2:
            continue
        try:
            longitude = float(parts[0])
            latitude = float(parts[1])
        except ValueError:
            continue
        points.append(RouteCoordinate(latitude=latitude, longitude=longitude))
    return points


def _safe_int(value: Any) -> int:
    parsed = _safe_int_or_none(value)
    return parsed if parsed is not None else 0


def _safe_int_or_none(value: Any) -> int | None:
    try:
        if value in (None, "", "[]"):
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _clean_string(value: Any) -> str | None:
    if value in (None, "", "[]"):
        return None
    return str(value)
