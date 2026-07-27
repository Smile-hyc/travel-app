from app.schemas.explore import PlaceSummary
from app.services.travel_plan_generation_service import TravelPlanGenerationService
from app.services.visit_unit_service import resolve_visit_units


def _place(place_id: str, name: str, latitude: float, longitude: float, **updates) -> PlaceSummary:
    return PlaceSummary(
        id=place_id,
        sourcePoiId=place_id,
        name=name,
        category="scenic",
        categoryCode="scenic",
        cityName="西安市",
        latitude=latitude,
        longitude=longitude,
        openingHoursWeek="周一至周日 08:30-18:30",
        **updates,
    )


def test_official_parent_and_members_become_one_executable_visit_unit() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    parent = _place("parent", "秦始皇帝陵博物院", 34.3837, 109.2812)
    warriors = _place("warriors", "秦始皇兵马俑博物馆", 34.3841, 109.2785)
    lishan = _place("lishan", "秦始皇帝陵博物院丽山园", 34.3688, 109.2538)

    normalized, units = resolve_visit_units(
        [parent, warriors, lishan],
        distance=service._distance,
    )

    assert {place.sourcePoiId for place in normalized} == {"warriors", "lishan"}
    assert len(units) == 1
    unit = units[0]
    assert unit.policy == "BUNDLE"
    assert [place.sourcePoiId for place in unit.places] == ["warriors", "lishan"]
    assert [place.recommendedVisitMinutes for place in unit.places] == [90, 90]
    assert unit.places[1].visitUnitTransferMinutes == 15
    assert unit.source_url == "https://www.bmy.com.cn/guide.html"


def test_unrelated_nearby_attractions_are_not_merged_by_distance_alone() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    museum = _place("museum", "陕西历史博物馆", 34.2251, 108.9530)
    pagoda = _place("pagoda", "大雁塔", 34.2185, 108.9642)

    normalized, units = resolve_visit_units([museum, pagoda], distance=service._distance)

    assert normalized == [museum, pagoda]
    assert len(units) == 2
    assert all(unit.policy == "COLOCATE" and len(unit.places) == 1 for unit in units)


def test_incomplete_official_complex_keeps_parent_instead_of_deleting_it() -> None:
    service = TravelPlanGenerationService(object(), object(), reveal_delay_seconds=0)
    parent = _place("parent", "秦始皇帝陵博物院", 34.3837, 109.2812)
    warriors = _place("warriors", "秦始皇兵马俑博物馆", 34.3841, 109.2785)

    normalized, units = resolve_visit_units([parent, warriors], distance=service._distance)

    assert normalized == [parent, warriors]
    assert len(units) == 2
    assert all(unit.policy == "COLOCATE" for unit in units)
