from app.schemas.explore import PlaceSummary, ReviewSource
from app.services.content_cleaning import (
    clean_review_sources,
    compute_place_relevance,
    extract_experience_tags,
    normalize_ugc_text,
)


def _place() -> PlaceSummary:
    return PlaceSummary(
        id="amap:B001",
        sourcePoiId="B001",
        name="故宫博物院",
        category="scenic",
        categoryCode="110000",
        cityName="北京市",
        districtName="东城区",
    )


def test_normalize_removes_urls_contacts_and_markup() -> None:
    value = "<b>故宫拍照</b>  https://bad.example  加微信: abc12345\n很出片"
    assert normalize_ugc_text(value) == "故宫拍照 很出片"


def test_relevance_requires_place_identity_and_rewards_location() -> None:
    assert compute_place_relevance(_place(), "北京故宫博物院参观攻略", "东城区拍照机位") >= 0.9
    assert compute_place_relevance(_place(), "沈阳故宫攻略", "辽宁旅行") < 0.58


def test_cleaning_deduplicates_and_rejects_unrelated_notes() -> None:
    valid = ReviewSource(
        id="xiaohongshu:n1",
        platform="小红书",
        title="北京故宫博物院参观攻略",
        excerpt="东城区排队较久，但很值得，拍照很出片。",
        url="https://www.xiaohongshu.com/explore/n1",
        author="user-a",
    )
    duplicate = valid.model_copy()
    unrelated = valid.model_copy(
        update={
            "id": "xiaohongshu:n2",
            "title": "上海咖啡馆攻略",
            "excerpt": "咖啡很好喝",
            "url": "https://www.xiaohongshu.com/explore/n2",
        },
    )

    cleaned = clean_review_sources(_place(), [valid, duplicate, unrelated])

    assert len(cleaned) == 1
    assert set(cleaned[0].tags) >= {"PHOTO", "QUEUE", "WORTH_IT"}
    assert cleaned[0].relevance_score >= 0.9


def test_short_ambiguous_place_name_requires_own_location() -> None:
    place = PlaceSummary(
        id="amap:tianjin-xiaobailou",
        sourcePoiId="tianjin-xiaobailou",
        name="小白楼",
        category="scenic",
        categoryCode="110000",
        provinceName="天津市",
        cityName="天津市",
        districtName="和平区",
    )

    assert compute_place_relevance(place, "北京国贸CBD小白楼探店", "夜晚氛围很好") < 0.58
    assert compute_place_relevance(place, "天津小白楼拍照攻略", "和平区地铁站附近") >= 0.58


def test_walking_street_is_not_walking_intensity_and_food_must_be_near_place() -> None:
    assert "WALKING" not in extract_experience_tags("沿着湖南路步行街逛咖啡店")
    assert "WALKING" in extract_experience_tags("全程大概4km，约2-3小时")
    text = "民园广场适合拍照，之后依次前往" + "其他景点" * 25 + "古文化街，那里有很多美食小吃"
    assert "FOOD" not in extract_experience_tags(text, place_name="民园广场")
