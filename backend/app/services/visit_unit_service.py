from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from app.schemas.explore import PlaceSummary


VisitUnitPolicy = Literal["BUNDLE", "COLOCATE", "MULTI_DAY_ALLOWED"]


@dataclass(frozen=True)
class VisitUnitMemberDefinition:
    aliases: tuple[str, ...]
    recommended_minutes: int


@dataclass(frozen=True)
class VisitUnitDefinition:
    unit_id: str
    canonical_name: str
    city_names: tuple[str, ...]
    parent_aliases: tuple[str, ...]
    members: tuple[VisitUnitMemberDefinition, ...]
    policy: VisitUnitPolicy
    source_url: str
    internal_transfer_minutes: int = 10
    max_member_span_km: float = 8.0


@dataclass(frozen=True)
class ResolvedVisitUnit:
    unit_id: str
    name: str
    policy: VisitUnitPolicy
    places: tuple[PlaceSummary, ...]
    source_url: str | None = None

    @property
    def sourcePoiId(self) -> str:
        return f"visit-unit:{self.unit_id}"

    @property
    def latitude(self) -> float | None:
        values = [place.latitude for place in self.places if place.latitude is not None]
        return sum(values) / len(values) if values else None

    @property
    def longitude(self) -> float | None:
        values = [place.longitude for place in self.places if place.longitude is not None]
        return sum(values) / len(values) if values else None

    @property
    def weight(self) -> int:
        return len(self.places)


# These are evidence-backed data records. The resolver and itinerary solver do
# not contain destination-specific branches and can consume additional records
# from an official-content pipeline without code changes.
OFFICIAL_VISIT_UNIT_DEFINITIONS: tuple[VisitUnitDefinition, ...] = (
    VisitUnitDefinition(
        unit_id="bmy-main-visit",
        canonical_name="秦始皇帝陵博物院",
        city_names=("西安", "西安市"),
        parent_aliases=("秦始皇帝陵博物院", "始皇帝博物馆", "始皇帝博物院"),
        members=(
            VisitUnitMemberDefinition(
                aliases=("秦始皇兵马俑博物馆", "秦始皇兵马俑", "秦陵兵马俑", "兵马俑"),
                recommended_minutes=90,
            ),
            VisitUnitMemberDefinition(
                aliases=("秦始皇陵考古遗址公园", "秦始皇帝陵博物院丽山园", "始皇帝博物馆丽山园", "丽山园"),
                recommended_minutes=90,
            ),
        ),
        policy="BUNDLE",
        source_url="https://www.bmy.com.cn/guide.html",
        internal_transfer_minutes=15,
        max_member_span_km=8.0,
    ),
)


def resolve_visit_units(
    places: list[PlaceSummary],
    *,
    distance: Callable[[PlaceSummary, PlaceSummary], float],
    definitions: tuple[VisitUnitDefinition, ...] = OFFICIAL_VISIT_UNIT_DEFINITIONS,
) -> tuple[list[PlaceSummary], list[ResolvedVisitUnit]]:
    """Resolve official complexes before assigning attractions to trip days.

    A parent POI is suppressed only when at least two distinct executable
    members are present and pass the configured geographic sanity check. This
    prevents a weak name match from deleting the only usable attraction.
    """
    remaining = list(places)
    resolved: list[ResolvedVisitUnit] = []
    consumed_ids: set[str] = set()

    for definition in definitions:
        candidates = [
            place
            for place in remaining
            if place.sourcePoiId not in consumed_ids and _city_matches(place, definition.city_names)
        ]
        matched_members: list[tuple[int, PlaceSummary, VisitUnitMemberDefinition]] = []
        member_ids: set[str] = set()
        for order, member in enumerate(definition.members):
            matches = [
                place
                for place in candidates
                if place.sourcePoiId not in member_ids and _matches_any_alias(place.name, member.aliases)
            ]
            if not matches:
                continue
            selected = max(matches, key=lambda place: _alias_match_quality(place.name, member.aliases))
            matched_members.append((order, selected, member))
            member_ids.add(selected.sourcePoiId)

        if len(matched_members) < 2 or not _members_are_geographically_valid(
            [item[1] for item in matched_members], distance, definition.max_member_span_km,
        ):
            continue

        parent_ids = {
            place.sourcePoiId
            for place in candidates
            if place.sourcePoiId not in member_ids
            and _matches_any_alias(place.name, definition.parent_aliases)
        }
        annotated: list[PlaceSummary] = []
        for order, place, member in sorted(matched_members, key=lambda item: item[0]):
            annotated.append(
                place.model_copy(
                    update={
                        "visitUnitId": definition.unit_id,
                        "visitUnitName": definition.canonical_name,
                        "visitUnitPolicy": definition.policy,
                        "visitUnitMemberOrder": order,
                        "visitUnitTransferMinutes": (
                            0 if order == 0 else definition.internal_transfer_minutes
                        ),
                        "visitUnitSourceUrl": definition.source_url,
                        "recommendedVisitMinutes": member.recommended_minutes,
                    },
                ),
            )
        consumed_ids.update(member_ids)
        consumed_ids.update(parent_ids)
        resolved.append(
            ResolvedVisitUnit(
                unit_id=definition.unit_id,
                name=definition.canonical_name,
                policy=definition.policy,
                places=tuple(annotated),
                source_url=definition.source_url,
            ),
        )

    by_id = {
        place.sourcePoiId: place
        for unit in resolved
        for place in unit.places
    }
    normalized_places = [
        by_id.get(place.sourcePoiId, place)
        for place in remaining
        if place.sourcePoiId not in consumed_ids or place.sourcePoiId in by_id
    ]
    bundled_ids = set(by_id)
    resolved.extend(
        ResolvedVisitUnit(
            unit_id=f"poi:{place.sourcePoiId}",
            name=place.name,
            policy="COLOCATE",
            places=(place,),
        )
        for place in normalized_places
        if place.sourcePoiId not in bundled_ids
    )
    return normalized_places, resolved


def _city_matches(place: PlaceSummary, city_names: tuple[str, ...]) -> bool:
    if not place.cityName:
        return True
    city = _normalize(place.cityName)
    return any(city == _normalize(value) for value in city_names)


def _matches_any_alias(name: str, aliases: tuple[str, ...]) -> bool:
    normalized = _normalize(name)
    return any(_normalize(alias) in normalized for alias in aliases)


def _alias_match_quality(name: str, aliases: tuple[str, ...]) -> tuple[int, int, int]:
    normalized = _normalize(name)
    exact = max((len(_normalize(alias)) for alias in aliases if _normalize(alias) == normalized), default=0)
    contained = max((len(_normalize(alias)) for alias in aliases if _normalize(alias) in normalized), default=0)
    return exact > 0, contained, -len(normalized)


def _members_are_geographically_valid(
    places: list[PlaceSummary],
    distance: Callable[[PlaceSummary, PlaceSummary], float],
    max_span_km: float,
) -> bool:
    return all(
        distance(left, right) <= max_span_km
        for index, left in enumerate(places)
        for right in places[index + 1 :]
    )


def _normalize(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())
