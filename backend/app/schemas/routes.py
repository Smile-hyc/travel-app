from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RouteMode = Literal["walking", "driving", "cycling", "transit"]


class RouteCoordinate(BaseModel):
    latitude: float
    longitude: float


class RoutePlace(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    address: str | None = None
    cityName: str | None = None
    adCode: str | None = None
    cityCode: str | None = None


class RouteStep(BaseModel):
    instruction: str | None = None
    distanceMeters: int | None = None
    durationSeconds: int | None = None
    polyline: list[RouteCoordinate] = Field(default_factory=list)


class RouteSegmentRequest(BaseModel):
    origin: RoutePlace
    destination: RoutePlace
    mode: RouteMode = "walking"
    departureDate: str | None = None
    departureTime: str | None = None


class RouteSegment(BaseModel):
    originId: str
    destinationId: str
    originName: str
    destinationName: str
    mode: RouteMode
    distanceMeters: int
    durationSeconds: int
    polyline: list[RouteCoordinate] = Field(default_factory=list)
    steps: list[RouteStep] = Field(default_factory=list)
    warning: str | None = None


class DayRouteRequest(BaseModel):
    places: list[RoutePlace] = Field(default_factory=list, max_length=15)
    mode: RouteMode = "walking"


class DayRoutePlan(BaseModel):
    places: list[RoutePlace]
    segments: list[RouteSegment]
    totalDistanceMeters: int
    totalDurationSeconds: int
    mode: RouteMode
    warning: str | None = None


class OptimizeDayRouteRequest(BaseModel):
    places: list[RoutePlace] = Field(default_factory=list, max_length=15)
    mode: RouteMode = "walking"


class OptimizeDayRouteResponse(BaseModel):
    originalPlaceIds: list[str]
    optimizedPlaceIds: list[str]
    optimizedPlaces: list[RoutePlace]
    route: DayRoutePlan
    changed: bool
    warning: str | None = None
