from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Callable, Mapping, Protocol, TypeVar


class LocatedPlace(Protocol):
    sourcePoiId: str
    latitude: float | None
    longitude: float | None


PlaceT = TypeVar("PlaceT", bound=LocatedPlace)
DistanceFn = Callable[[PlaceT, PlaceT], float]
ScoreFn = Callable[[PlaceT], float]
DayScoreFn = Callable[[PlaceT, int], float]


@dataclass(frozen=True)
class CandidateScore:
    preference: float
    recognition: float
    review_confidence: float
    weather: float
    season: float
    mandatory_affinity: float
    route_convenience: float
    freshness: float
    commute_penalty: float = 0.0
    crowd_penalty: float = 0.0
    uncertainty_penalty: float = 0.0

    @property
    def total(self) -> float:
        positive = (
            self.preference * 0.25
            + self.recognition * 0.18
            + self.review_confidence * 0.14
            + self.weather * 0.12
            + self.season * 0.10
            + self.mandatory_affinity * 0.08
            + self.route_convenience * 0.08
            + self.freshness * 0.05
        )
        return positive - self.commute_penalty - self.crowd_penalty - self.uncertainty_penalty


@dataclass(frozen=True)
class TimeWindow:
    start: int
    end: int
    # Attractions can stop admission before the venue closes.
    latest_start: int | None = None


@dataclass(frozen=True)
class VisitCandidate:
    place_id: str
    value: float
    duration_minutes: int
    windows: tuple[TimeWindow, ...]
    mandatory: bool = False
    uncertainty_penalty: float = 0.0
    category: str = ""
    region: str = ""


@dataclass(frozen=True)
class TravelEdge:
    origin_id: str
    destination_id: str
    duration_minutes: int
    distance_meters: int
    mode: str = "estimated"
    available: bool = True
    verified: bool = False


@dataclass(frozen=True)
class ScheduledVisit:
    place_id: str
    arrival: int
    start: int
    end: int


@dataclass(frozen=True)
class DaySolution:
    ordered_place_ids: tuple[str, ...] = ()
    visits: tuple[ScheduledVisit, ...] = ()
    objective: float = 0.0
    total_value: float = 0.0
    travel_minutes: int = 0
    waiting_minutes: int = 0
    distance_meters: int = 0
    longest_leg_minutes: int = 0
    long_wait_count: int = 0
    cross_region_count: int = 0
    repeated_category_count: int = 0
    finish_minute: int | None = None
    feasible: bool = True
    violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DaySolverConfig:
    day_start: int
    day_end: int
    max_visits: int
    travel_minute_penalty: float = 0.012
    distance_km_penalty: float = 0.025
    unverified_edge_penalty: float = 0.08
    waiting_minute_penalty: float = 0.004
    minimum_optional_gain: float = 0.01
    max_normal_leg_minutes: int = 40
    max_idle_minutes: int = 45
    excess_leg_minute_penalty: float = 0.035
    long_idle_minute_penalty: float = 0.018
    cross_region_penalty: float = 0.18
    repeated_category_penalty: float = 0.12


def solve_day_with_time_windows(
    candidates: list[VisitCandidate],
    edges: Mapping[tuple[str, str], TravelEdge],
    config: DaySolverConfig,
    *,
    start_id: str | None = None,
    end_id: str | None = None,
) -> DaySolution:
    """Build a compact executable day using insertion and bounded local search.

    The solver is deliberately deterministic. It never repairs an unavailable
    edge or a closed time window with invented travel/opening data. Mandatory
    candidates are inserted first; optional candidates are admitted only when
    the complete anchored route remains feasible and improves the objective.
    """
    if config.day_end <= config.day_start or config.max_visits <= 0:
        return DaySolution(feasible=False, violations=("invalid_day_window",))

    by_id = {candidate.place_id: candidate for candidate in candidates}
    ranked = sorted(
        by_id.values(),
        key=lambda item: (not item.mandatory, -item.value, item.place_id),
    )
    route: list[str] = []

    for candidate in (item for item in ranked if item.mandatory):
        inserted = _best_insertion(route, candidate.place_id, by_id, edges, config, start_id, end_id)
        if inserted is None:
            return DaySolution(
                ordered_place_ids=tuple(route),
                feasible=False,
                violations=(f"mandatory_unreachable:{candidate.place_id}",),
            )
        route = inserted

    # Regret insertion protects candidates with narrow feasible insertion slots
    # instead of consuming those slots by raw score order alone.
    while len(route) < config.max_visits:
        current = _evaluate(route, by_id, edges, config, start_id, end_id)
        choices: list[tuple[float, float, str, list[str]]] = []
        for candidate in ranked:
            if candidate.mandatory or candidate.place_id in route:
                continue
            options = _insertion_options(
                route, candidate.place_id, by_id, edges, config, start_id, end_id,
            )
            if not options:
                continue
            best_route, best_result = options[0]
            second_score = options[1][1].objective if len(options) > 1 else current.objective
            gain = best_result.objective - current.objective
            regret = max(0.0, best_result.objective - second_score)
            choices.append((gain + regret * 0.20, gain, candidate.place_id, best_route))
        if not choices:
            break
        _, gain, _, inserted = max(choices, key=lambda item: (item[0], item[1], item[2]))
        if route and gain < config.minimum_optional_gain:
            break
        route = inserted

    route = _local_search(route, ranked, by_id, edges, config, start_id, end_id)
    result = _evaluate(route, by_id, edges, config, start_id, end_id)
    missing = [item.place_id for item in ranked if item.mandatory and item.place_id not in route]
    if missing:
        return DaySolution(
            ordered_place_ids=result.ordered_place_ids,
            visits=result.visits,
            objective=result.objective,
            total_value=result.total_value,
            travel_minutes=result.travel_minutes,
            distance_meters=result.distance_meters,
            feasible=False,
            violations=tuple(f"mandatory_missing:{place_id}" for place_id in missing),
        )
    return result


def _best_insertion(
    route: list[str],
    place_id: str,
    candidates: Mapping[str, VisitCandidate],
    edges: Mapping[tuple[str, str], TravelEdge],
    config: DaySolverConfig,
    start_id: str | None,
    end_id: str | None,
) -> list[str] | None:
    options = _insertion_options(route, place_id, candidates, edges, config, start_id, end_id)
    return options[0][0] if options else None


def _insertion_options(
    route: list[str],
    place_id: str,
    candidates: Mapping[str, VisitCandidate],
    edges: Mapping[tuple[str, str], TravelEdge],
    config: DaySolverConfig,
    start_id: str | None,
    end_id: str | None,
) -> list[tuple[list[str], DaySolution]]:
    evaluated: list[tuple[list[str], DaySolution]] = []
    for index in range(len(route) + 1):
        proposal = route[:index] + [place_id] + route[index:]
        result = _evaluate(proposal, candidates, edges, config, start_id, end_id)
        if result.feasible:
            evaluated.append((proposal, result))
    evaluated.sort(key=lambda item: (item[1].objective, tuple(item[0])), reverse=True)
    return evaluated


def _local_search(
    route: list[str],
    ranked: list[VisitCandidate],
    candidates: Mapping[str, VisitCandidate],
    edges: Mapping[tuple[str, str], TravelEdge],
    config: DaySolverConfig,
    start_id: str | None,
    end_id: str | None,
) -> list[str]:
    best = list(route)
    best_score = _evaluate(best, candidates, edges, config, start_id, end_id).objective
    for _ in range(4):
        proposals: list[list[str]] = []
        for left in range(len(best)):
            for right in range(left + 1, len(best)):
                proposals.append(best[:left] + list(reversed(best[left : right + 1])) + best[right + 1 :])
                swapped = list(best)
                swapped[left], swapped[right] = swapped[right], swapped[left]
                proposals.append(swapped)
        for source in range(len(best)):
            for target in range(len(best)):
                if source == target:
                    continue
                relocated = list(best)
                item = relocated.pop(source)
                relocated.insert(target, item)
                proposals.append(relocated)
        unused = [item for item in ranked if item.place_id not in best]
        for old_index, old_id in enumerate(best):
            if candidates[old_id].mandatory:
                continue
            for replacement in unused[:10]:
                proposals.append(best[:old_index] + [replacement.place_id] + best[old_index + 1 :])

        improved = False
        for proposal in proposals:
            result = _evaluate(proposal, candidates, edges, config, start_id, end_id)
            if result.feasible and result.objective > best_score + 1e-6:
                best = proposal
                best_score = result.objective
                improved = True
        if not improved:
            break
    return best


def _evaluate(
    route: list[str],
    candidates: Mapping[str, VisitCandidate],
    edges: Mapping[tuple[str, str], TravelEdge],
    config: DaySolverConfig,
    start_id: str | None,
    end_id: str | None,
) -> DaySolution:
    current = config.day_start
    previous_id = start_id
    visits: list[ScheduledVisit] = []
    travel_minutes = 0
    waiting_minutes = 0
    distance_meters = 0
    unverified_edges = 0
    longest_leg_minutes = 0
    long_wait_count = 0
    cross_region_count = 0
    repeated_category_count = 0
    excess_leg_minutes = 0
    excess_idle_minutes = 0
    violations: list[str] = []

    for place_id in route:
        candidate = candidates.get(place_id)
        if candidate is None:
            violations.append(f"unknown_candidate:{place_id}")
            break
        if previous_id is not None:
            edge = edges.get((previous_id, place_id))
            if edge is None or not edge.available:
                violations.append(f"route_unavailable:{previous_id}:{place_id}")
                break
            current += max(0, edge.duration_minutes)
            travel_minutes += max(0, edge.duration_minutes)
            longest_leg_minutes = max(longest_leg_minutes, max(0, edge.duration_minutes))
            excess_leg_minutes += max(0, edge.duration_minutes - config.max_normal_leg_minutes)
            distance_meters += max(0, edge.distance_meters)
            unverified_edges += int(not edge.verified)
            previous_candidate = candidates.get(previous_id)
            if previous_candidate is not None:
                if (
                    previous_candidate.region
                    and candidate.region
                    and previous_candidate.region != candidate.region
                ):
                    cross_region_count += 1
                if (
                    previous_candidate.category
                    and candidate.category
                    and previous_candidate.category == candidate.category
                ):
                    repeated_category_count += 1
        arrival = current
        slot = next(
            (
                (max(arrival, window.start), max(arrival, window.start) + candidate.duration_minutes)
                for window in sorted(candidate.windows, key=lambda item: item.start)
                if max(arrival, window.start) <= (
                    window.latest_start if window.latest_start is not None else window.end
                )
                and max(arrival, window.start) + candidate.duration_minutes <= min(window.end, config.day_end)
            ),
            None,
        )
        if slot is None:
            violations.append(f"time_window:{place_id}")
            break
        start, end = slot
        wait = max(0, start - arrival)
        waiting_minutes += wait
        if wait > config.max_idle_minutes:
            long_wait_count += 1
            excess_idle_minutes += wait - config.max_idle_minutes
        visits.append(ScheduledVisit(place_id=place_id, arrival=arrival, start=start, end=end))
        current = end
        previous_id = place_id

    if not violations and end_id is not None and previous_id is not None:
        edge = edges.get((previous_id, end_id))
        if edge is None or not edge.available:
            violations.append(f"route_unavailable:{previous_id}:{end_id}")
        else:
            current += max(0, edge.duration_minutes)
            travel_minutes += max(0, edge.duration_minutes)
            longest_leg_minutes = max(longest_leg_minutes, max(0, edge.duration_minutes))
            excess_leg_minutes += max(0, edge.duration_minutes - config.max_normal_leg_minutes)
            distance_meters += max(0, edge.distance_meters)
            unverified_edges += int(not edge.verified)
            if current > config.day_end:
                violations.append("end_anchor_late")

    total_value = sum(candidates[place_id].value for place_id in route if place_id in candidates)
    uncertainty = sum(candidates[place_id].uncertainty_penalty for place_id in route if place_id in candidates)
    objective = (
        total_value
        - travel_minutes * config.travel_minute_penalty
        - distance_meters / 1000 * config.distance_km_penalty
        - unverified_edges * config.unverified_edge_penalty
        - waiting_minutes * config.waiting_minute_penalty
        - excess_leg_minutes * config.excess_leg_minute_penalty
        - excess_idle_minutes * config.long_idle_minute_penalty
        - cross_region_count * config.cross_region_penalty
        - repeated_category_count * config.repeated_category_penalty
        - uncertainty
    )
    return DaySolution(
        ordered_place_ids=tuple(route),
        visits=tuple(visits),
        objective=objective,
        total_value=total_value,
        travel_minutes=travel_minutes,
        waiting_minutes=waiting_minutes,
        distance_meters=distance_meters,
        longest_leg_minutes=longest_leg_minutes,
        long_wait_count=long_wait_count,
        cross_region_count=cross_region_count,
        repeated_category_count=repeated_category_count,
        finish_minute=current if not violations else None,
        feasible=not violations,
        violations=tuple(violations),
    )


def proximity_score(distance_km: float, scale_km: float = 5.0) -> float:
    """Return a stable 0..1 convenience score without a hard distance cliff."""
    return exp(-max(0.0, distance_km) / max(scale_km, 0.1))


def partition_by_geography(
    places: list[PlaceT],
    day_count: int,
    *,
    score: Callable[[PlaceT], float],
    distance: Callable[[PlaceT, PlaceT], float],
    capacity: int,
) -> list[list[PlaceT]]:
    """Create balanced, compact day regions before choosing visit order.

    Seeds favor high-value places while remaining geographically distinct.
    Remaining places are assigned to the nearest region with a load penalty,
    which prevents one dense city center from consuming every day.
    """
    if day_count <= 0:
        return []
    ranked = sorted(places, key=lambda place: (-score(place), place.sourcePoiId))
    if not ranked:
        return [[] for _ in range(day_count)]

    seeds = [ranked[0]]
    remaining = ranked[1:]
    while remaining and len(seeds) < day_count:
        next_seed = max(
            remaining,
            key=lambda place: (
                min(distance(place, seed) for seed in seeds) * 0.65 + score(place) * 0.35,
                score(place),
            ),
        )
        seeds.append(next_seed)
        remaining.remove(next_seed)

    groups: list[list[PlaceT]] = [[seed] for seed in seeds]
    groups.extend([] for _ in range(day_count - len(groups)))
    seed_ids = {seed.sourcePoiId for seed in seeds}
    for place in (item for item in ranked if item.sourcePoiId not in seed_ids):
        eligible = [index for index, group in enumerate(groups) if len(group) < capacity]
        if not eligible:
            break

        def assignment_cost(index: int) -> float:
            group = groups[index]
            if not group:
                return -score(place)
            mean_distance = sum(distance(place, member) for member in group) / len(group)
            load_penalty = (len(group) / max(capacity, 1)) * 2.0
            return mean_distance + load_penalty - score(place) * 0.12

        groups[min(eligible, key=assignment_cost)].append(place)
    return groups


def improve_day_partition(
    groups: list[list[PlaceT]],
    *,
    day_score: DayScoreFn,
    distance: DistanceFn,
    capacity: int,
    compactness_penalty: float = 0.10,
) -> list[list[PlaceT]]:
    """Improve a geographic partition with deterministic day-move and swap steps."""
    best = [list(group) for group in groups]

    def objective(candidate_groups: list[list[PlaceT]]) -> float:
        value = 0.0
        for day_index, group in enumerate(candidate_groups, start=1):
            value += sum(day_score(place, day_index) for place in group)
            pair_distances = [
                distance(left, right)
                for index, left in enumerate(group)
                for right in group[index + 1 :]
            ]
            if pair_distances:
                value -= sum(pair_distances) / len(pair_distances) * compactness_penalty
        return value

    best_score = objective(best)
    for _ in range(5):
        proposals: list[list[list[PlaceT]]] = []
        for source_index, source in enumerate(best):
            for place_index in range(len(source)):
                if len(source) <= 1:
                    continue
                for target_index, target in enumerate(best):
                    if source_index == target_index or len(target) >= capacity:
                        continue
                    proposal = [list(group) for group in best]
                    moved = proposal[source_index].pop(place_index)
                    proposal[target_index].append(moved)
                    proposals.append(proposal)
        for left_index in range(len(best)):
            for right_index in range(left_index + 1, len(best)):
                for left_place_index in range(len(best[left_index])):
                    for right_place_index in range(len(best[right_index])):
                        proposal = [list(group) for group in best]
                        proposal[left_index][left_place_index], proposal[right_index][right_place_index] = (
                            proposal[right_index][right_place_index],
                            proposal[left_index][left_place_index],
                        )
                        proposals.append(proposal)

        improved: list[list[PlaceT]] | None = None
        improved_score = best_score
        for proposal in proposals:
            proposal_score = objective(proposal)
            if proposal_score > improved_score + 1e-6:
                improved = proposal
                improved_score = proposal_score
        if improved is None:
            break
        best = improved
        best_score = improved_score

    for group in best:
        group.sort(key=lambda place: place.sourcePoiId)
    return best


def optimize_open_route(
    places: list[PlaceT],
    *,
    distance: Callable[[PlaceT, PlaceT], float],
    start: PlaceT | None = None,
    end: PlaceT | None = None,
) -> list[PlaceT]:
    """Nearest insertion followed by bounded 2-opt for an open anchored route."""
    if len(places) < 2:
        return list(places)

    remaining = list(places)
    if start is None:
        ordered = [remaining.pop(0)]
    else:
        first = min(remaining, key=lambda place: distance(start, place))
        remaining.remove(first)
        ordered = [first]
    while remaining:
        current = ordered[-1]
        following = min(
            remaining,
            key=lambda place: distance(current, place)
            + (distance(place, end) * 0.15 if end is not None else 0.0),
        )
        remaining.remove(following)
        ordered.append(following)

    def route_length(route: list[PlaceT]) -> float:
        legs: list[tuple[PlaceT, PlaceT]] = list(zip(route, route[1:]))
        total = sum(distance(left, right) for left, right in legs)
        if start is not None:
            total += distance(start, route[0])
        if end is not None:
            total += distance(route[-1], end)
        return total

    best = ordered
    best_length = route_length(best)
    # For the small daily routes used here, exhaustive pair swaps complement
    # 2-opt and avoid local minima in open routes with two fixed anchors.
    for _ in range(5):
        improved = False
        for left in range(0, len(best) - 1):
            for right in range(left + 1, len(best)):
                candidate = best[:left] + list(reversed(best[left : right + 1])) + best[right + 1 :]
                candidate_length = route_length(candidate)
                if candidate_length + 0.05 < best_length:
                    best = candidate
                    best_length = candidate_length
                    improved = True
        for left in range(len(best) - 1):
            for right in range(left + 1, len(best)):
                candidate = list(best)
                candidate[left], candidate[right] = candidate[right], candidate[left]
                candidate_length = route_length(candidate)
                if candidate_length + 0.05 < best_length:
                    best = candidate
                    best_length = candidate_length
                    improved = True
        if not improved:
            break
    return best


def route_length(
    places: list[PlaceT],
    *,
    distance: Callable[[PlaceT, PlaceT], float],
    start: PlaceT | None = None,
    end: PlaceT | None = None,
) -> float:
    if not places:
        return 0.0
    total = sum(distance(left, right) for left, right in zip(places, places[1:]))
    if start is not None:
        total += distance(start, places[0])
    if end is not None:
        total += distance(places[-1], end)
    return total
