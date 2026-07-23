import asyncio

from fastapi import HTTPException

from app.schemas.routes import RoutePlace, RouteSegment, RouteSegmentRequest
from app.services.amap_route_service import AmapRouteService


def _place(place_id: str) -> RoutePlace:
    return RoutePlace(id=place_id, name=place_id, latitude=39.9, longitude=116.4, adCode="110000")


def _segment(mode: str, distance: int, minutes: int) -> RouteSegment:
    return RouteSegment(
        originId="a",
        destinationId="b",
        originName="a",
        destinationName="b",
        mode=mode,
        distanceMeters=distance,
        durationSeconds=minutes * 60,
    )


def test_best_segment_compares_modes_instead_of_returning_first_success() -> None:
    class FakeRouteService(AmapRouteService):
        def __init__(self) -> None:
            pass

        async def segment(self, request):
            return {
                "walking": _segment("walking", 3200, 45),
                "transit": _segment("transit", 3600, 18),
                "cycling": _segment("cycling", 3300, 16),
                "driving": _segment("driving", 4100, 12),
            }[request.mode]

    result = asyncio.run(
        FakeRouteService().best_segment(
            origin=_place("a"),
            destination=_place("b"),
            preference="TRANSIT",
        ),
    )

    assert result.mode == "transit"


def test_empty_transit_result_falls_back_to_another_real_mode() -> None:
    class FakeRouteService(AmapRouteService):
        def __init__(self) -> None:
            pass

        async def segment(self, request):
            if request.mode == "transit":
                raise HTTPException(status_code=502, detail="当前时段没有公交方案")
            if request.mode == "walking":
                return _segment("walking", 900, 14)
            raise HTTPException(status_code=502, detail="不可用")

    result = asyncio.run(
        FakeRouteService().best_segment(
            origin=_place("a"),
            destination=_place("b"),
            preference="TRANSIT",
        ),
    )

    assert result.mode == "walking"


def test_segment_dispatches_to_concrete_route_implementation() -> None:
    class FakeRouteService(AmapRouteService):
        def __init__(self) -> None:
            self._segment_cache = type(
                "Cache",
                (),
                {"get": staticmethod(lambda _key: None), "set": staticmethod(lambda *_args, **_kwargs: None)},
            )()

        async def _walking(self, origin, destination):
            return _segment("walking", 800, 12)

    result = asyncio.run(
        FakeRouteService().segment(
            RouteSegmentRequest(origin=_place("a"), destination=_place("b"), mode="walking"),
        ),
    )

    assert result.mode == "walking"
    assert callable(getattr(AmapRouteService, "calculate_day"))
    assert callable(getattr(AmapRouteService, "_transit"))


def test_road_time_matrix_batches_origins_by_destination() -> None:
    class FakeClient:
        calls = 0

        async def get(self, path, params):
            assert path == "/v3/distance"
            self.calls += 1
            origin_count = len(params["origins"].split("|"))
            return {
                "results": [
                    {
                        "origin_id": str(index + 1),
                        "distance": str(1000 + index * 100),
                        "duration": str(600 + index * 60),
                    }
                    for index in range(origin_count)
                ],
            }

    client = FakeClient()
    service = AmapRouteService(client)
    places = [_place("a"), _place("b"), _place("c")]

    matrix = asyncio.run(service.road_time_matrix(places))

    assert client.calls == 3
    assert len(matrix) == 6
    assert matrix[("a", "b")][0] >= 10