from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.schemas.explore import PlaceDetail, PlaceSummary, ReviewHighlight, ReviewSource
from app.services.simple_cache import TtlCache


class PlaceReviewClient(Protocol):
    async def search_place(self, place: PlaceSummary) -> list[ReviewSource]: ...


class PlaceDetailService:
    def __init__(
        self,
        review_client: PlaceReviewClient,
        *,
        cache_ttl_seconds: int = 21600,
        empty_cache_ttl_seconds: int = 300,
    ) -> None:
        self._review_client = review_client
        self._cache_ttl_seconds = max(60, cache_ttl_seconds)
        self._empty_cache_ttl_seconds = max(30, empty_cache_ttl_seconds)
        self._cache: TtlCache[PlaceDetail] = TtlCache(max_items=256)

    async def get_detail(self, place: PlaceSummary) -> PlaceDetail:
        cache_key = ("place-detail", place.sourcePoiId)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        sources = await self._review_client.search_place(place)
        detail = _build_detail(place, sources)
        self._cache.set(
            cache_key,
            detail,
            ttl_seconds=self._cache_ttl_seconds if sources else self._empty_cache_ttl_seconds,
        )
        return detail


def _build_detail(place: PlaceSummary, sources: list[ReviewSource]) -> PlaceDetail:
    has_sources = bool(sources)
    return PlaceDetail(
        summary=place,
        images=place.images,
        openingHours=place.openingHoursWeek or place.openingHoursToday,
        phone=place.phone,
        description=_build_description(place),
        reviewTitle="真实评价" if has_sources else "地点亮点",
        reviewSubtitle=(
            f"根据 {len(sources)} 条公开用户内容整理，点击卡片可查看原文"
            if has_sources
            else "基于地点公开信息整理，出发前建议再次确认"
        ),
        positiveHighlights=_build_review_highlights(place, sources),
        negativeHighlights=_build_cautions(place, sources),
        reviewSources=sources,
        sourceLabels=sorted({source.platform for source in sources}),
        hasRealReviews=has_sources,
        reviewUpdatedAt=datetime.now(tz=timezone.utc).isoformat() if has_sources else None,
    )


def _build_description(place: PlaceSummary) -> str:
    location = place.address or place.districtName or place.cityName
    category = (place.typeName or place.category).replace(";", "、")
    parts = []
    if location:
        parts.append(f"{place.name}位于{location}")
    else:
        parts.append(place.name)
    if category:
        parts.append(f"地点类型为{category}")
    if place.businessArea:
        parts.append(f"所在商圈为{place.businessArea}")
    return "，".join(parts) + "。"


def _build_review_highlights(
    place: PlaceSummary,
    sources: list[ReviewSource],
) -> list[ReviewHighlight]:
    text = " ".join(filter(None, [item.title for item in sources] + [item.excerpt for item in sources]))
    aspect_groups = [
        ("环境与氛围", ("环境", "氛围", "景色", "建筑", "装修", "拍照"), "公开内容较多提到这里的环境、氛围或拍照体验。"),
        ("体验与特色", ("体验", "好玩", "值得", "特色", "展览", "文化"), "用户内容中较常出现体验感和地点特色相关描述。"),
        ("餐饮与服务", ("好吃", "味道", "菜品", "服务", "咖啡", "饮品"), "公开内容中有人分享了餐饮或现场服务体验。"),
    ]
    highlights = [
        ReviewHighlight(title=title, description=description)
        for title, keywords, description in aspect_groups
        if any(keyword in text for keyword in keywords)
    ]
    if sources and not highlights:
        highlights.append(
            ReviewHighlight(
                title="公开内容可参考",
                description=f"已找到 {len(sources)} 条与该地点相关的用户内容，可在下方直接查看原文。",
            )
        )
    if not sources:
        if place.rating:
            highlights.append(
                ReviewHighlight(
                    title="公开评分",
                    description=f"高德地点信息显示评分为 {place.rating} 分，可作为选择时的辅助参考。",
                )
            )
        if place.openingHoursWeek or place.openingHoursToday:
            highlights.append(
                ReviewHighlight(
                    title="行程更好安排",
                    description="已获取营业时间信息，适合在规划路线时预留到访时段。",
                )
            )
        if not highlights:
            highlights.append(
                ReviewHighlight(
                    title="地点信息明确",
                    description=f"已获取{place.typeName or place.category}分类和定位信息，可直接加入计划或导航。",
                )
            )
    return highlights[:3]


def _build_cautions(place: PlaceSummary, sources: list[ReviewSource]) -> list[ReviewHighlight]:
    text = " ".join(filter(None, [item.title for item in sources] + [item.excerpt for item in sources]))
    cautions: list[ReviewHighlight] = []
    if any(keyword in text for keyword in ("排队", "人多", "拥挤", "预约")):
        cautions.append(
            ReviewHighlight(title="高峰时段", description="部分公开内容提到排队、人流或预约，节假日前往建议提前确认。")
        )
    if any(keyword in text for keyword in ("停车", "交通", "偏远", "难找")):
        cautions.append(
            ReviewHighlight(title="交通提示", description="部分公开内容涉及停车或交通问题，出发前建议检查路线。")
        )
    if not place.openingHoursWeek and not place.openingHoursToday:
        cautions.append(
            ReviewHighlight(title="营业时间待确认", description="暂未获取可靠营业时间，建议到访前电话或通过官方渠道确认。")
        )
    return cautions[:2]
