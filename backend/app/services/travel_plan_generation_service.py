from __future__ import annotations

import asyncio
import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException

from app.schemas.ai import (
    AiGeneratedDay,
    AiGeneratedPlace,
    AiPlanQuality,
    AiPlanGenerationRequest,
    AiPlanGenerationResponse,
    AiPlanProgressEvent,
)
from app.schemas.explore import PlaceSummary
from app.services.amap_poi_service import AmapPoiService
from app.services.ark_client import ArkClient


PREFERENCE_CATEGORIES = {
    "吃": "food",
    "美食": "food",
    "喝": "drink",
    "咖啡": "drink",
    "购物": "shopping",
    "逛街": "shopping",
}

ProgressCallback = Callable[
    [int, str, int, list[AiGeneratedDay] | None, AiPlanProgressEvent | None, int | None],
    None,
]
PACE_PLACE_COUNTS = {"RELAXED": 3, "BALANCED": 4, "INTENSIVE": 5}


class TravelPlanGenerationService:
    def __init__(
        self,
        ark_client: ArkClient,
        poi_service: AmapPoiService,
        reveal_delay_seconds: float = 0.24,
    ) -> None:
        self._ark_client = ark_client
        self._poi_service = poi_service
        self._reveal_delay_seconds = reveal_delay_seconds

    async def generate(
        self,
        request: AiPlanGenerationRequest,
        progress: ProgressCallback | None = None,
    ) -> AiPlanGenerationResponse:
        self._validate_time_window(request)
        self._notify(progress, 5, "正在理解目的地与旅行约束")
        destination = request.destination.strip()
        cities = await self._poi_service.search_cities(keyword=destination, limit=5)
        if not cities:
            raise HTTPException(status_code=422, detail="没有找到这个目的地，请输入城市名称后重试。")

        city = cities[0]
        self._notify(progress, 18, f"已定位 {city.name}，正在检索真实地点")
        categories = self._categories_for(request.preferences)
        target_count = min(36, max(request.dayCount * PACE_PLACE_COUNTS[request.pace] + 6, 12))
        per_category = min(24, max(8, math.ceil(target_count / len(categories)) + 4))
        search_results = await asyncio.gather(
            *[
                self._poi_service.search_pois(
                    keyword=None,
                    adcode=city.adCode,
                    category=category,
                    page=1,
                    page_size=per_category,
                    city_limit=True,
                )
                for category in categories
            ],
        )
        candidates = self._dedupe_candidates(
            [place for result in search_results for place in result.items],
        )
        if len(candidates) < request.dayCount * 2:
            raise HTTPException(
                status_code=422,
                detail=f"{destination}当前可用的真实地点数据不足，请稍后重试或缩短行程天数。",
            )

        self._notify(progress, 44, f"已筛选 {len(candidates)} 个高德真实地点")
        fallback = self._build_heuristic_days(request, candidates)
        await self._publish_draft(progress, fallback)
        warnings: list[str] = []
        model_name: str | None = self._ark_client.model_name
        used_fallback = False
        try:
            self._notify(
                progress,
                74,
                "路线草案已绘制，AI 正在优化跨天顺序与游玩节奏",
                len(fallback),
                partial_days=fallback,
                event=self._event(
                    "ANALYSIS",
                    "已用真实地点形成可用草案，继续优化主题、时间与停留说明。",
                ),
                active_day_index=fallback[-1].dayIndex if fallback else None,
            )
            ai_payload = await self._generate_with_ai(request, city.name, candidates)
            self._notify(progress, 86, "AI 编排完成，正在校验地点与时间", len(fallback))
            days = self._merge_ai_result(request, ai_payload, candidates, fallback)
        except (HTTPException, ValueError, json.JSONDecodeError, TypeError) as exc:
            days = fallback
            model_name = None
            used_fallback = True
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            warnings.append(f"AI 编排暂时不可用，已使用地点偏好与距离规则生成：{detail}")

        self._notify(
            progress,
            94,
            "正在生成质量报告并保存结果",
            len(days),
            partial_days=days,
            event=self._event(
                "PLAN_REFINED",
                "地点、时间和每日主题已完成校验，正在保存最终版本。",
            ),
            active_day_index=days[-1].dayIndex if days else None,
        )
        all_places = [place for day in days for place in day.places]
        duplicate_count = len(all_places) - len({place.sourcePoiId for place in all_places})

        return AiPlanGenerationResponse(
            requestId=str(uuid.uuid4()),
            title=f"{city.name.rstrip('市')} {request.dayCount} 日智能行程",
            destination=city.name,
            dateRange=request.dateRange.strip(),
            dayCount=request.dayCount,
            preferences=self._clean_preferences(request.preferences),
            days=days,
            warnings=warnings,
            generatedAt=datetime.now(timezone.utc).isoformat(),
            model=model_name,
            quality=AiPlanQuality(
                realPoiRatio=1.0,
                duplicatePlaceCount=duplicate_count,
                totalPlaceCount=len(all_places),
                usedFallback=used_fallback,
                dataSources=["AMAP"] if used_fallback else ["AMAP", "ARK"],
            ),
        )

    async def _publish_draft(
        self,
        callback: ProgressCallback | None,
        days: list[AiGeneratedDay],
    ) -> None:
        if callback is None or not days:
            return
        total_places = sum(len(day.places) for day in days)
        revealed_places = 0
        partial_days: list[AiGeneratedDay] = []

        for day in days:
            partial_day = day.model_copy(update={"places": []}, deep=True)
            partial_days.append(partial_day)
            self._notify(
                callback,
                46 + round(24 * revealed_places / max(total_places, 1)),
                f"正在规划第 {day.dayIndex} 天的地点与路线",
                day.dayIndex - 1,
                partial_days=partial_days,
                event=self._event(
                    "DAY_STARTED",
                    f"开始规划第 {day.dayIndex} 天：以少折返、节奏可执行为优先。",
                    day_index=day.dayIndex,
                ),
                active_day_index=day.dayIndex,
            )

            for place_index, place in enumerate(day.places):
                previous = partial_day.places[-1] if partial_day.places else None
                partial_day.places.append(place.model_copy(deep=True))
                partial_day.estimatedDistanceKm = self._day_distance(partial_day.places)
                revealed_places += 1
                self._notify(
                    callback,
                    46 + round(24 * revealed_places / max(total_places, 1)),
                    f"已加入 {place.name}，正在延伸第 {day.dayIndex} 天路线",
                    day.dayIndex - 1,
                    partial_days=partial_days,
                    event=self._event(
                        "PLACE_ADDED",
                        self._placement_reason(place, previous, day.dayIndex, place_index),
                        day_index=day.dayIndex,
                        place_id=place.id,
                    ),
                    active_day_index=day.dayIndex,
                )
                if self._reveal_delay_seconds > 0:
                    await asyncio.sleep(self._reveal_delay_seconds)

            self._notify(
                callback,
                46 + round(24 * revealed_places / max(total_places, 1)),
                f"第 {day.dayIndex} 天路线草案已完成",
                day.dayIndex,
                partial_days=partial_days,
                event=self._event(
                    "DAY_COMPLETED",
                    f"第 {day.dayIndex} 天已串联 {len(day.places)} 个地点，预估连线约 {day.estimatedDistanceKm} km。",
                    day_index=day.dayIndex,
                ),
                active_day_index=day.dayIndex,
            )

    def _placement_reason(
        self,
        place: AiGeneratedPlace,
        previous: AiGeneratedPlace | None,
        day_index: int,
        place_index: int,
    ) -> str:
        if previous is None:
            area = place.districtName or place.cityName or "核心区域"
            return f"把 {place.name} 作为第 {day_index} 天起点，先覆盖{area}的重点地点。"
        distance = self._distance_coordinates(
            previous.latitude,
            previous.longitude,
            place.latitude,
            place.longitude,
        )
        if place.category in {"food", "drink"}:
            return f"在 {previous.name} 后安排 {place.name}，补充用餐停留；两点直线约 {distance:.1f} km。"
        return f"从 {previous.name} 顺路加入 {place.name}，两点直线约 {distance:.1f} km，减少跨区折返。"

    def _event(
        self,
        event_type: str,
        message: str,
        day_index: int | None = None,
        place_id: str | None = None,
    ) -> AiPlanProgressEvent:
        return AiPlanProgressEvent(
            sequence=1,
            type=event_type,
            message=message,
            dayIndex=day_index,
            placeId=place_id,
            createdAt=datetime.now(timezone.utc).isoformat(),
        )

    def _categories_for(self, preferences: list[str]) -> list[str]:
        categories = ["scenic", "food"]
        for preference in preferences:
            for keyword, category in PREFERENCE_CATEGORIES.items():
                if keyword in preference and category not in categories:
                    categories.append(category)
        return categories[:4]

    def _dedupe_candidates(self, places: list[PlaceSummary]) -> list[PlaceSummary]:
        result: list[PlaceSummary] = []
        seen: set[str] = set()
        for place in places:
            if place.sourcePoiId in seen or place.latitude is None or place.longitude is None:
                continue
            if any(self._same_real_world_place(place, existing) for existing in result):
                continue
            seen.add(place.sourcePoiId)
            result.append(place)
        return result

    def _same_real_world_place(self, left: PlaceSummary, right: PlaceSummary) -> bool:
        if self._distance(left, right) > 0.6:
            return False
        left_name = re.sub(r"[^\w\u4e00-\u9fff]", "", left.name).lower()
        right_name = re.sub(r"[^\w\u4e00-\u9fff]", "", right.name).lower()
        shorter, longer = sorted((left_name, right_name), key=len)
        if len(shorter) >= 3 and shorter in longer:
            return True
        if re.search(r"[\u4e00-\u9fff]", left_name) is None or re.search(r"[\u4e00-\u9fff]", right_name) is None:
            return False
        common_prefix = 0
        for left_char, right_char in zip(left_name, right_name):
            if left_char != right_char:
                break
            common_prefix += 1
        return common_prefix >= 3

    async def _generate_with_ai(
        self,
        request: AiPlanGenerationRequest,
        city_name: str,
        candidates: list[PlaceSummary],
    ) -> dict[str, Any]:
        compact_candidates = [
            {
                "sourcePoiId": place.sourcePoiId,
                "name": place.name,
                "category": place.category,
                "type": place.typeName,
                "address": place.address,
                "district": place.districtName,
                "latitude": place.latitude,
                "longitude": place.longitude,
            }
            for place in candidates[: min(len(candidates), max(24, request.dayCount * 7))]
        ]
        prompt = {
            "destination": city_name,
            "dateRange": request.dateRange,
            "dayCount": request.dayCount,
            "preferences": self._clean_preferences(request.preferences),
            "freeText": (request.freeText or "").strip(),
            "pace": request.pace,
            "transportPreference": request.transportPreference,
            "dailyTimeWindow": f"{request.dailyStart}-{request.dailyEnd}",
            "candidatePlaces": compact_candidates,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是结构化旅行行程规划器。只能使用候选地点中的 sourcePoiId，不能虚构地点。"
                    "综合用户偏好、地点类别、行政区和经纬度，尽量让同一天的地点相近，并穿插餐饮。"
                    f"旅行节奏为 {request.pace}，每天目标地点数为 {PACE_PLACE_COUNTS[request.pace]}，"
                    f"每日活动必须处于 {request.dailyStart}-{request.dailyEnd}，交通偏好为 {request.transportPreference}。"
                    "同一地点不可重复。只输出 JSON，不要 Markdown。"
                    "JSON 格式：{\"title\":\"\",\"days\":[{\"dayIndex\":1,\"title\":\"\","
                    "\"summary\":\"\",\"places\":[{\"sourcePoiId\":\"\",\"start\":\"09:00\","
                    "\"end\":\"10:30\",\"note\":\"不超过35字的真实可核验游玩建议\"}]}]}。"
                    "无法确认票价、营业时间或预约规则时不要编造。"
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ]
        raw = await self._ark_client.chat(
            messages,
            max_tokens=min(5000, max(2200, request.dayCount * 650)),
            temperature=0.25,
            timeout_seconds=90.0,
        )
        return json.loads(self._extract_json(raw))

    def _extract_json(self, text: str) -> str:
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("模型没有返回结构化行程")
        return text[start : end + 1]

    def _merge_ai_result(
        self,
        request: AiPlanGenerationRequest,
        payload: dict[str, Any],
        candidates: list[PlaceSummary],
        fallback: list[AiGeneratedDay],
    ) -> list[AiGeneratedDay]:
        by_id = {place.sourcePoiId: place for place in candidates}
        fallback_by_day = {day.dayIndex: day for day in fallback}
        used: set[str] = set()
        result: list[AiGeneratedDay] = []
        raw_days = payload.get("days") if isinstance(payload, dict) else None
        raw_days = raw_days if isinstance(raw_days, list) else []

        for day_index in range(1, request.dayCount + 1):
            raw_day = next(
                (
                    day
                    for day in raw_days
                    if isinstance(day, dict) and self._safe_int(day.get("dayIndex")) == day_index
                ),
                {},
            )
            raw_places = raw_day.get("places") if isinstance(raw_day, dict) else []
            raw_places = raw_places if isinstance(raw_places, list) else []
            generated_places: list[AiGeneratedPlace] = []
            for position, raw_place in enumerate(raw_places[:5]):
                if not isinstance(raw_place, dict):
                    continue
                source_id = str(raw_place.get("sourcePoiId") or "").strip()
                place = by_id.get(source_id)
                if place is None or source_id in used:
                    continue
                used.add(source_id)
                generated_places.append(self._to_generated_place(place, position, raw_place, request))

            fallback_day = fallback_by_day[day_index]
            for place in fallback_day.places:
                if len(generated_places) >= min(4, len(candidates)):
                    break
                if place.sourcePoiId not in used:
                    used.add(place.sourcePoiId)
                    generated_places.append(place)

            result.append(
                AiGeneratedDay(
                    dayIndex=day_index,
                    title=self._clean_text(raw_day.get("title"), fallback_day.title, 32),
                    summary=self._clean_text(raw_day.get("summary"), fallback_day.summary, 80),
                    places=generated_places,
                    estimatedDistanceKm=self._day_distance(generated_places),
                    intensity=self._intensity(generated_places),
                ),
            )
        return result

    def _build_heuristic_days(
        self,
        request: AiPlanGenerationRequest,
        candidates: list[PlaceSummary],
    ) -> list[AiGeneratedDay]:
        scenic = [place for place in candidates if place.category == "scenic"]
        food = [place for place in candidates if place.category in {"food", "drink"}]
        other = [place for place in candidates if place.category not in {"scenic", "food", "drink"}]
        ordered = scenic + other + food
        used: set[str] = set()
        days: list[AiGeneratedDay] = []
        per_day = min(PACE_PLACE_COUNTS[request.pace], max(2, len(candidates) // request.dayCount))

        for day_index in range(1, request.dayCount + 1):
            seed = next((place for place in ordered if place.sourcePoiId not in used), None)
            if seed is None:
                break
            selected = [seed]
            used.add(seed.sourcePoiId)
            while len(selected) < per_day:
                available = [place for place in candidates if place.sourcePoiId not in used]
                if not available:
                    break
                needs_food = len(selected) == per_day - 1 and not any(
                    place.category in {"food", "drink"} for place in selected
                )
                pool = [place for place in available if place.category in {"food", "drink"}] if needs_food else available
                if not pool:
                    pool = available
                center = selected[-1]
                next_place = min(pool, key=lambda place: self._distance(center, place))
                selected.append(next_place)
                used.add(next_place.sourcePoiId)

            days.append(
                AiGeneratedDay(
                    dayIndex=day_index,
                    title=f"DAY {day_index} · {selected[0].districtName or request.destination}",
                    summary="按地点距离顺路串联，兼顾游玩节奏与用餐停留。",
                    places=[
                        self._to_generated_place(place, index, {}, request)
                        for index, place in enumerate(selected)
                    ],
                    estimatedDistanceKm=self._day_distance_from_summaries(selected),
                    intensity=self._intensity_count(len(selected)),
                ),
            )
        return days

    def _to_generated_place(
        self,
        place: PlaceSummary,
        position: int,
        ai: dict[str, Any],
        request: AiPlanGenerationRequest,
    ) -> AiGeneratedPlace:
        default_start, default_end = self._default_slot(request, position)
        return AiGeneratedPlace(
            id=place.id,
            source=place.source,
            sourcePoiId=place.sourcePoiId,
            name=place.name,
            category=place.category,
            categoryCode=place.categoryCode,
            typeName=place.typeName,
            typeCode=place.typeCode,
            address=place.address,
            provinceName=place.provinceName,
            cityName=place.cityName,
            districtName=place.districtName,
            adCode=place.adCode,
            cityCode=place.cityCode,
            latitude=place.latitude or 0.0,
            longitude=place.longitude or 0.0,
            thumbnailUrl=place.coverImageUrl,
            imageUrls=place.imageUrls,
            suggestedStart=self._clean_time(ai.get("start"), default_start),
            suggestedEnd=self._clean_time(ai.get("end"), default_end),
            note=self._clean_text(
                ai.get("note"),
                "根据地点实际开放信息安排停留，出发前建议再次确认。",
                80,
            ),
        )

    def _distance(self, left: PlaceSummary, right: PlaceSummary) -> float:
        left_lat = math.radians(left.latitude or 0.0)
        right_lat = math.radians(right.latitude or 0.0)
        delta_lat = right_lat - left_lat
        delta_lng = math.radians((right.longitude or 0.0) - (left.longitude or 0.0))
        value = math.sin(delta_lat / 2) ** 2 + math.cos(left_lat) * math.cos(right_lat) * math.sin(delta_lng / 2) ** 2
        return 6371.0 * 2 * math.asin(math.sqrt(value))

    def _clean_preferences(self, preferences: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in preferences if item.strip()))[:12]

    def _clean_time(self, value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        return text if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text) else fallback

    def _clean_text(self, value: Any, fallback: str, limit: int) -> str:
        text = str(value or "").strip()
        return (text or fallback)[:limit]

    def _safe_int(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _validate_time_window(self, request: AiPlanGenerationRequest) -> None:
        if self._time_to_minutes(request.dailyEnd) - self._time_to_minutes(request.dailyStart) < 240:
            raise HTTPException(status_code=422, detail="每日可用时间至少需要 4 小时。")

    def _default_slot(self, request: AiPlanGenerationRequest, position: int) -> tuple[str, str]:
        start = self._time_to_minutes(request.dailyStart)
        end = self._time_to_minutes(request.dailyEnd)
        count = PACE_PLACE_COUNTS[request.pace]
        interval = max(60, (end - start) // count)
        slot_start = min(start + position * interval, end - 45)
        slot_end = min(slot_start + max(45, min(100, interval - 20)), end)
        return self._minutes_to_time(slot_start), self._minutes_to_time(slot_end)

    def _time_to_minutes(self, value: str) -> int:
        hour, minute = value.split(":", 1)
        return int(hour) * 60 + int(minute)

    def _minutes_to_time(self, value: int) -> str:
        return f"{value // 60:02d}:{value % 60:02d}"

    def _day_distance(self, places: list[AiGeneratedPlace]) -> float:
        return round(
            sum(
                self._distance_coordinates(left.latitude, left.longitude, right.latitude, right.longitude)
                for left, right in zip(places, places[1:])
            ),
            1,
        )

    def _day_distance_from_summaries(self, places: list[PlaceSummary]) -> float:
        return round(sum(self._distance(left, right) for left, right in zip(places, places[1:])), 1)

    def _distance_coordinates(
        self,
        left_latitude: float,
        left_longitude: float,
        right_latitude: float,
        right_longitude: float,
    ) -> float:
        left_lat = math.radians(left_latitude)
        right_lat = math.radians(right_latitude)
        delta_lat = right_lat - left_lat
        delta_lng = math.radians(right_longitude - left_longitude)
        value = math.sin(delta_lat / 2) ** 2 + math.cos(left_lat) * math.cos(right_lat) * math.sin(delta_lng / 2) ** 2
        return 6371.0 * 2 * math.asin(math.sqrt(value))

    def _intensity(self, places: list[AiGeneratedPlace]) -> str:
        return self._intensity_count(len(places))

    def _intensity_count(self, count: int) -> str:
        if count <= 3:
            return "轻松"
        if count == 4:
            return "适中"
        return "充实"

    def _notify(
        self,
        callback: ProgressCallback | None,
        progress: int,
        stage: str,
        completed_days: int = 0,
        partial_days: list[AiGeneratedDay] | None = None,
        event: AiPlanProgressEvent | None = None,
        active_day_index: int | None = None,
    ) -> None:
        if callback is not None:
            callback(
                progress,
                stage,
                completed_days,
                partial_days,
                event,
                active_day_index,
            )
