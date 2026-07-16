from __future__ import annotations

import itertools
import math

from app.schemas.routes import RoutePlace


def optimize_place_order(places: list[RoutePlace]) -> list[RoutePlace]:
    if len(places) <= 2:
        return places
    if len(places) <= 8:
        return _exact_order_with_fixed_start(places)
    return _two_opt(_nearest_neighbor(places))


def route_score(places: list[RoutePlace]) -> float:
    return sum(_distance(a, b) for a, b in zip(places, places[1:]))


def _exact_order_with_fixed_start(places: list[RoutePlace]) -> list[RoutePlace]:
    start = places[0]
    rest = places[1:]
    best = places
    best_score = route_score(places)
    for candidate_rest in itertools.permutations(rest):
        candidate = [start, *candidate_rest]
        score = route_score(candidate)
        if score < best_score:
            best = candidate
            best_score = score
    return best


def _nearest_neighbor(places: list[RoutePlace]) -> list[RoutePlace]:
    remaining = places[1:].copy()
    ordered = [places[0]]
    while remaining:
        current = ordered[-1]
        next_place = min(remaining, key=lambda place: _distance(current, place))
        ordered.append(next_place)
        remaining.remove(next_place)
    return ordered


def _two_opt(places: list[RoutePlace]) -> list[RoutePlace]:
    best = places
    best_score = route_score(best)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best)):
                if j - i == 1:
                    continue
                candidate = best[:i] + best[i:j][::-1] + best[j:]
                score = route_score(candidate)
                if score < best_score:
                    best = candidate
                    best_score = score
                    improved = True
    return best


def _distance(a: RoutePlace, b: RoutePlace) -> float:
    radius = 6_371_000.0
    lat1 = math.radians(a.latitude)
    lat2 = math.radians(b.latitude)
    delta_lat = math.radians(b.latitude - a.latitude)
    delta_lon = math.radians(b.longitude - a.longitude)
    h = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(h), math.sqrt(1 - h))
