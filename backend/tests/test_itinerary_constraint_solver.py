from dataclasses import dataclass

from app.services.itinerary_constraint_solver import (
    CandidateScore,
    DaySolverConfig,
    TimeWindow,
    TravelEdge,
    VisitCandidate,
    improve_day_partition,
    optimize_open_route,
    partition_by_geography,
    solve_day_with_time_windows,
)


@dataclass
class Point:
    sourcePoiId: str
    latitude: float
    longitude: float
    value: float = 0.5


def distance(left: Point, right: Point) -> float:
    return abs(left.latitude - right.latitude) + abs(left.longitude - right.longitude)


def test_candidate_score_uses_documented_weights_and_penalties() -> None:
    score = CandidateScore(
        preference=1.0,
        recognition=1.0,
        review_confidence=1.0,
        weather=1.0,
        season=1.0,
        mandatory_affinity=1.0,
        route_convenience=1.0,
        freshness=1.0,
        commute_penalty=0.10,
        uncertainty_penalty=0.05,
    )

    assert score.total == 0.85


def test_geographic_partition_keeps_compact_regions_together() -> None:
    places = [
        Point("west-a", 0.0, 0.0, 1.0),
        Point("west-b", 0.1, 0.1, 0.8),
        Point("east-a", 10.0, 10.0, 0.9),
        Point("east-b", 10.1, 10.1, 0.7),
    ]

    groups = partition_by_geography(
        places,
        2,
        score=lambda place: place.value,
        distance=distance,
        capacity=2,
    )

    assert {place.sourcePoiId for place in groups[0]} in (
        {"west-a", "west-b"},
        {"east-a", "east-b"},
    )
    assert all(len(group) == 2 for group in groups)


def test_day_partition_local_search_moves_weather_suitable_place() -> None:
    indoor = Point("indoor", 0.0, 0.0)
    outdoor = Point("outdoor", 0.1, 0.1)
    neutral = Point("neutral", 10.0, 10.0)

    groups = improve_day_partition(
        [[outdoor, indoor], [neutral]],
        day_score=lambda place, day: 10.0 if place.sourcePoiId == "indoor" and day == 2 else 1.0,
        distance=distance,
        capacity=2,
        compactness_penalty=0.0,
    )

    assert "indoor" in {place.sourcePoiId for place in groups[1]}


def test_two_opt_removes_crossing_route_with_fixed_anchors() -> None:
    start = Point("start", 0.0, 0.0)
    end = Point("end", 3.0, 0.0)
    places = [
        Point("a", 1.0, 1.0),
        Point("b", 2.0, -1.0),
        Point("c", 2.0, 1.0),
        Point("d", 1.0, -1.0),
    ]

    ordered = optimize_open_route(places, distance=distance, start=start, end=end)

    assert {place.sourcePoiId for place in ordered} == {"a", "b", "c", "d"}
    route = [start, *ordered, end]
    assert sum(distance(left, right) for left, right in zip(route, route[1:])) <= 9.0


def test_time_window_solver_rejects_closed_high_value_place() -> None:
    candidates = [
        VisitCandidate("closed", 10.0, 90, (TimeWindow(8 * 60, 9 * 60),)),
        VisitCandidate("open", 4.0, 90, (TimeWindow(9 * 60, 17 * 60),)),
    ]
    edges = {
        ("hotel", "closed"): TravelEdge("hotel", "closed", 20, 2000, verified=True),
        ("hotel", "open"): TravelEdge("hotel", "open", 20, 2000, verified=True),
        ("open", "hotel"): TravelEdge("open", "hotel", 20, 2000, verified=True),
    }

    result = solve_day_with_time_windows(
        candidates,
        edges,
        DaySolverConfig(day_start=9 * 60, day_end=18 * 60, max_visits=2),
        start_id="hotel",
        end_id="hotel",
    )

    assert result.feasible is True
    assert result.ordered_place_ids == ("open",)


def test_time_window_solver_keeps_mandatory_and_avoids_unavailable_edge() -> None:
    candidates = [
        VisitCandidate("must", 1.0, 60, (TimeWindow(9 * 60, 18 * 60),), mandatory=True),
        VisitCandidate("far", 8.0, 60, (TimeWindow(9 * 60, 18 * 60),)),
        VisitCandidate("near", 3.0, 60, (TimeWindow(9 * 60, 18 * 60),)),
    ]
    edges = {
        ("start", "must"): TravelEdge("start", "must", 10, 500, verified=True),
        ("must", "end"): TravelEdge("must", "end", 10, 500, verified=True),
        ("must", "far"): TravelEdge("must", "far", 10, 500, available=False, verified=True),
        ("far", "end"): TravelEdge("far", "end", 10, 500, verified=True),
        ("must", "near"): TravelEdge("must", "near", 10, 500, verified=True),
        ("near", "must"): TravelEdge("near", "must", 10, 500, verified=True),
        ("start", "near"): TravelEdge("start", "near", 10, 500, verified=True),
        ("near", "end"): TravelEdge("near", "end", 10, 500, verified=True),
        ("start", "far"): TravelEdge("start", "far", 10, 500, verified=True),
        ("far", "must"): TravelEdge("far", "must", 10, 500, available=False, verified=True),
    }

    result = solve_day_with_time_windows(
        candidates,
        edges,
        DaySolverConfig(day_start=9 * 60, day_end=18 * 60, max_visits=2),
        start_id="start",
        end_id="end",
    )

    assert result.feasible is True
    assert "must" in result.ordered_place_ids
    assert "near" in result.ordered_place_ids
    assert "far" not in result.ordered_place_ids


def test_time_window_enforces_last_admission_before_closing_time() -> None:
    candidate = VisitCandidate(
        "museum",
        5.0,
        45,
        (TimeWindow(8 * 60 + 30, 17 * 60, latest_start=16 * 60),),
    )
    edges = {("hotel", "museum"): TravelEdge("hotel", "museum", 10, 800, verified=True)}

    feasible = solve_day_with_time_windows(
        [candidate],
        edges,
        DaySolverConfig(day_start=15 * 60 + 30, day_end=18 * 60, max_visits=1),
        start_id="hotel",
    )
    too_late = solve_day_with_time_windows(
        [candidate],
        edges,
        DaySolverConfig(day_start=16 * 60, day_end=18 * 60, max_visits=1),
        start_id="hotel",
    )

    assert feasible.ordered_place_ids == ("museum",)
    assert too_late.ordered_place_ids == ()


def test_comfort_policy_rejects_small_value_gain_from_very_long_transfer() -> None:
    candidates = [
        VisitCandidate("near", 5.0, 60, (TimeWindow(9 * 60, 18 * 60),), category="park", region="west"),
        VisitCandidate("far", 5.4, 60, (TimeWindow(9 * 60, 18 * 60),), category="museum", region="east"),
    ]
    edges = {
        ("hotel", "near"): TravelEdge("hotel", "near", 15, 1500, verified=True),
        ("near", "hotel"): TravelEdge("near", "hotel", 15, 1500, verified=True),
        ("hotel", "far"): TravelEdge("hotel", "far", 90, 18000, verified=True),
        ("far", "hotel"): TravelEdge("far", "hotel", 90, 18000, verified=True),
        ("near", "far"): TravelEdge("near", "far", 90, 18000, verified=True),
        ("far", "near"): TravelEdge("far", "near", 90, 18000, verified=True),
    }

    result = solve_day_with_time_windows(
        candidates,
        edges,
        DaySolverConfig(
            day_start=9 * 60,
            day_end=18 * 60,
            max_visits=1,
            max_normal_leg_minutes=35,
            excess_leg_minute_penalty=0.08,
        ),
        start_id="hotel",
        end_id="hotel",
    )

    assert result.ordered_place_ids == ("near",)
    assert result.longest_leg_minutes == 15


def test_underfilled_day_accepts_a_compact_slightly_negative_insertion() -> None:
    candidates = [
        VisitCandidate("main", 5.0, 105, (TimeWindow(9 * 60, 20 * 60),), category="museum"),
        VisitCandidate("nearby", 0.05, 105, (TimeWindow(9 * 60, 20 * 60),), category="park"),
    ]
    edges = {
        ("hotel", "main"): TravelEdge("hotel", "main", 10, 500, verified=True),
        ("main", "hotel"): TravelEdge("main", "hotel", 10, 500, verified=True),
        ("hotel", "nearby"): TravelEdge("hotel", "nearby", 10, 500, verified=True),
        ("nearby", "hotel"): TravelEdge("nearby", "hotel", 10, 500, verified=True),
        ("main", "nearby"): TravelEdge("main", "nearby", 10, 500, verified=True),
        ("nearby", "main"): TravelEdge("nearby", "main", 10, 500, verified=True),
    }

    result = solve_day_with_time_windows(
        candidates,
        edges,
        DaySolverConfig(
            day_start=9 * 60,
            day_end=20 * 60,
            max_visits=2,
            minimum_visit_minutes=210,
            minimum_underfilled_gain=-0.20,
        ),
        start_id="hotel",
        end_id="hotel",
    )

    assert set(result.ordered_place_ids) == {"main", "nearby"}
    assert result.visit_minutes == 210


def test_underfilled_day_does_not_use_a_long_transfer_as_filler() -> None:
    candidates = [
        VisitCandidate("main", 5.0, 105, (TimeWindow(9 * 60, 20 * 60),)),
        VisitCandidate("remote", 4.9, 105, (TimeWindow(9 * 60, 20 * 60),)),
    ]
    edges = {
        ("hotel", "main"): TravelEdge("hotel", "main", 10, 500, verified=True),
        ("main", "hotel"): TravelEdge("main", "hotel", 10, 500, verified=True),
        ("hotel", "remote"): TravelEdge("hotel", "remote", 70, 12000, verified=True),
        ("remote", "hotel"): TravelEdge("remote", "hotel", 70, 12000, verified=True),
        ("main", "remote"): TravelEdge("main", "remote", 70, 12000, verified=True),
        ("remote", "main"): TravelEdge("remote", "main", 70, 12000, verified=True),
    }

    result = solve_day_with_time_windows(
        candidates,
        edges,
        DaySolverConfig(
            day_start=9 * 60,
            day_end=20 * 60,
            max_visits=2,
            minimum_visit_minutes=210,
            minimum_underfilled_gain=-100.0,
            max_normal_leg_minutes=40,
        ),
        start_id="hotel",
        end_id="hotel",
    )

    assert result.ordered_place_ids == ("main",)
    assert result.longest_leg_minutes == 10
