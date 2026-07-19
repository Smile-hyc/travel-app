from __future__ import annotations

import asyncio
import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import HTTPException

from app.schemas.ai import (
    AiGeneratedDay,
    AiGeneratedPlace,
    AiGeneratedTransfer,
    AiPlanQuality,
    AiPlanGenerationRequest,
    AiPlanGenerationResponse,
    AiPlanProgressEvent,
)
from app.schemas.explore import PlaceSummary
from app.schemas.routes import RoutePlace
from app.services.amap_poi_service import AmapPoiService
from app.services.amap_route_service import AmapRouteService
from app.services.amap_weather_service import AmapWeatherForecastDay, AmapWeatherService
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
        route_service: AmapRouteService | None = None,
        weather_service: AmapWeatherService | None = None,
        reveal_delay_seconds: float = 0.24,
        ai_optimization_timeout_seconds: float = 18.0,
    ) -> None:
        self._ark_client = ark_client
        self._poi_service = poi_service
        self._route_service = route_service
        self._weather_service = weather_service
        self._reveal_delay_seconds = reveal_delay_seconds
        self._ai_optimization_timeout_seconds = ai_optimization_timeout_seconds

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
        weather_forecast: list[AmapWeatherForecastDay] = []
        if self._weather_service is not None:
            try:
                weather_forecast = await self._weather_service.get_city_forecast(adcode=city.adCode)
                weather_text = "；".join(day.text for day in weather_forecast[: min(request.dayCount, 4)])
                self._notify(
                    progress,
                    22,
                    "已取得高德天气预报，正在调整室内外地点权重",
                    event=self._event(
                        "WEATHER_CHECK",
                        f"可用预报：{weather_text}",
                        evidence=[day.text for day in weather_forecast[:4]],
                        decision="雨雪、高温或大风时优先室内地点；天气数据超出预报范围时不做推断。",
                    ),
                )
            except HTTPException as exc:
                self._notify(
                    progress,
                    22,
                    "天气预报暂不可用，将不基于天气作推断",
                    event=self._event(
                        "WEATHER_CHECK",
                        str(exc.detail),
                        decision="保留其他硬约束，不虚构未来天气。",
                    ),
                )
        categories = self._categories_for(request.preferences)
        target_count = min(36, max(request.dayCount * PACE_PLACE_COUNTS[request.pace] + 6, 12))
        per_category = min(24, max(8, math.ceil(target_count / len(categories)) + 4))
        search_tasks = [
            self._poi_service.search_pois(
                keyword=self._category_search_keyword(city.name, category),
                adcode=city.adCode,
                category=category,
                page=1,
                page_size=per_category,
                city_limit=True,
            )
            for category in categories
        ]
        transport_queries = list(
            dict.fromkeys(
                value.strip()
                for value in (request.arrivalStation, request.departureStation)
                if value and value.strip()
            ),
        )
        for query in transport_queries:
            search_tasks.append(
                self._poi_service.search_pois(
                    keyword=query,
                    adcode=city.adCode,
                    category="transport",
                    page=1,
                    page_size=12,
                    city_limit=True,
                ),
            )
        hotel_queries = list(
            dict.fromkeys(
                [
                    *([request.hotelName.strip()] if request.hotelName and request.hotelName.strip() else []),
                    *(stay.name.strip() for stay in request.hotelStays if stay.name.strip()),
                ],
            ),
        )
        for query in hotel_queries:
            search_tasks.append(
                self._poi_service.search_pois(
                    keyword=query,
                    adcode=city.adCode,
                    category="lodging",
                    page=1,
                    page_size=16,
                    city_limit=True,
                ),
            )
        search_results = await asyncio.gather(*search_tasks)
        candidates = self._dedupe_candidates(
            [place for result in search_results for place in result.items],
        )
        if len(candidates) < request.dayCount * 2:
            raise HTTPException(
                status_code=422,
                detail=f"{destination}当前可用的真实地点数据不足，请稍后重试或缩短行程天数。",
            )

        arrival_anchor = self._select_station(candidates, request.arrivalStation or "") if request.arrivalStation else None
        departure_anchor = (
            self._select_station(candidates, request.departureStation or "")
            if request.departureStation
            else None
        )
        hotel_by_name = {
            query: self._select_hotel(candidates, query, arrival_anchor)
            for query in hotel_queries
        }
        anchor_text = "、".join(
            dict.fromkeys(
                place.name
                for place in [arrival_anchor, departure_anchor, *hotel_by_name.values()]
                if place is not None
            ),
        )
        self._notify(
            progress,
            44,
            f"已筛选 {len(candidates)} 个高德真实地点" + (f"，锚点为 {anchor_text}" if anchor_text else ""),
            event=self._event(
                "ANCHOR_APPLIED",
                f"仅采用用户明确填写的交通与住宿锚点：{anchor_text or '未填写，因此不自动加入车站、机场或酒店'}。",
                evidence=[value for value in transport_queries + hotel_queries],
                decision="未填写的交通枢纽和酒店不会进入行程。",
            ),
        )
        fallback = self._build_heuristic_days(
            request,
            candidates,
            arrival_anchor=arrival_anchor,
            departure_anchor=departure_anchor,
            hotel_by_name=hotel_by_name,
            city_name=city.name,
            weather_forecast=weather_forecast,
        )
        fallback = await self._apply_actual_routes(request, fallback, weather_forecast, progress)
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
            ai_payload = await self._optimize_with_heartbeat(
                request,
                city.name,
                candidates,
                fallback,
                progress,
            )
            self._notify(progress, 86, "AI 编排完成，正在校验地点与时间", len(fallback))
            days = self._merge_ai_result(request, ai_payload, candidates, fallback)
            days = await self._apply_actual_routes(request, days, weather_forecast, progress)
        except (HTTPException, ValueError, json.JSONDecodeError, TypeError, asyncio.TimeoutError) as exc:
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
        evidence: list[str] | None = None,
        decision: str | None = None,
    ) -> AiPlanProgressEvent:
        return AiPlanProgressEvent(
            sequence=1,
            type=event_type,
            message=message,
            dayIndex=day_index,
            placeId=place_id,
            evidence=(evidence or [])[:8],
            decision=decision,
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
        seen_brands: set[tuple[str, str]] = set()
        for place in places:
            if place.sourcePoiId in seen or place.latitude is None or place.longitude is None:
                continue
            if any(self._same_real_world_place(place, existing) for existing in result):
                continue
            brand = self._brand_key(place.name)
            brand_key = (place.category, brand)
            if place.category in {"food", "drink", "lodging"} and brand and brand_key in seen_brands:
                continue
            seen.add(place.sourcePoiId)
            if brand:
                seen_brands.add(brand_key)
            result.append(place)
        return result

    def _brand_key(self, name: str) -> str:
        if not any(mark in name for mark in ("(", "（", "店", "酒店", "宾馆")):
            return ""
        base = re.split(r"[（(]", name, maxsplit=1)[0]
        base = re.sub(r"(?:旗舰店|总店|分店|酒店|宾馆|店)$", "", base)
        return re.sub(r"[^\w\u4e00-\u9fff]", "", base).lower()

    def _same_real_world_place(self, left: PlaceSummary, right: PlaceSummary) -> bool:
        distance = self._distance(left, right)
        left_name = re.sub(r"[^\w\u4e00-\u9fff]", "", left.name).lower()
        right_name = re.sub(r"[^\w\u4e00-\u9fff]", "", right.name).lower()
        shorter, longer = sorted((left_name, right_name), key=len)
        if len(shorter) >= 3 and shorter in longer and distance <= 1.5:
            return True
        if distance > 0.6:
            return False
        if re.search(r"[\u4e00-\u9fff]", left_name) is None or re.search(r"[\u4e00-\u9fff]", right_name) is None:
            return False
        common_prefix = 0
        for left_char, right_char in zip(left_name, right_name):
            if left_char != right_char:
                break
            common_prefix += 1
        return common_prefix >= 3

    def _category_search_keyword(self, city_name: str, category: str) -> str | None:
        city = city_name.rstrip("市")
        if category != "food":
            return None
        local_food_keywords = {
            "北京": "北京烤鸭",
            "上海": "本帮菜",
            "成都": "川菜火锅",
            "重庆": "重庆火锅",
            "西安": "西安特色小吃",
            "广州": "广府粤菜",
            "南京": "南京特色美食",
            "杭州": "杭帮菜",
            "苏州": "苏帮菜",
            "厦门": "闽南小吃",
        }
        return local_food_keywords.get(city, f"{city}特色美食")

    def _select_station(self, candidates: list[PlaceSummary], query: str) -> PlaceSummary | None:
        clean_query = re.sub(r"\s+", "", query)
        stations = [
            place
            for place in candidates
            if place.category == "transport"
            and (
                any(keyword in (place.typeName or "") for keyword in ("火车站", "铁路", "高铁"))
                or (
                    place.name.endswith("站")
                    and not any(keyword in place.name for keyword in ("地铁", "公交", "客运", "收费"))
                )
            )
        ]
        if not stations:
            return None
        return max(
            stations,
            key=lambda place: (
                20.0 if clean_query and clean_query in re.sub(r"\s+", "", place.name) else 0.0
            ) + self._quality_score(place),
        )

    def _select_hotel(
        self,
        candidates: list[PlaceSummary],
        requested_name: str | None,
        station: PlaceSummary | None,
    ) -> PlaceSummary | None:
        hotels = [place for place in candidates if place.category == "lodging"]
        if not hotels:
            return None
        requested = re.sub(r"\s+", "", requested_name or "")
        if requested:
            exact = [place for place in hotels if requested in re.sub(r"\s+", "", place.name)]
            if exact:
                return max(exact, key=self._quality_score)
        scenic = sorted(
            (place for place in candidates if place.category == "scenic"),
            key=self._quality_score,
            reverse=True,
        )[:6]
        center_places = scenic or ([station] if station is not None else [])

        def hotel_score(place: PlaceSummary) -> float:
            distance_penalty = 0.0
            if center_places:
                distance_penalty = sum(self._distance(place, target) for target in center_places) / len(center_places)
            name_penalty = 4.0 if any(word in place.name for word in ("公寓", "民宿", "招待所")) else 0.0
            return self._quality_score(place) - distance_penalty * 0.8 - name_penalty

        return max(hotels, key=hotel_score)

    def _quality_score(self, place: PlaceSummary) -> float:
        try:
            rating = float(place.rating or 0)
        except ValueError:
            rating = 0.0
        photo_bonus = 1.2 if place.coverImageUrl else 0.0
        address_bonus = 0.4 if place.address else 0.0
        branch_penalty = 0.8 if any(mark in place.name for mark in ("入口", "售票处", "停车场")) else 0.0
        return rating * 3.0 + photo_bonus + address_bonus - branch_penalty

    async def _optimize_with_heartbeat(
        self,
        request: AiPlanGenerationRequest,
        city_name: str,
        candidates: list[PlaceSummary],
        fallback: list[AiGeneratedDay],
        progress: ProgressCallback | None,
    ) -> dict[str, Any]:
        task = asyncio.create_task(self._generate_with_ai(request, city_name, candidates, fallback, progress))
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        timeout = max(0.05, self._ai_optimization_timeout_seconds)
        heartbeat = 0
        try:
            while True:
                elapsed = loop.time() - started_at
                remaining = timeout - elapsed
                if remaining <= 0:
                    raise asyncio.TimeoutError
                done, _ = await asyncio.wait({task}, timeout=min(2.0, remaining))
                if task in done:
                    return task.result()
                heartbeat += 1
                progress_value = min(84, 74 + heartbeat * 2)
                self._notify(
                    progress,
                    progress_value,
                    f"正在校验营业时间与跨天顺序（约剩 {max(1, round(remaining))} 秒）",
                    len(fallback),
                    partial_days=fallback,
                    event=self._event(
                        "ANALYSIS",
                        "正在检查景点开放时段、午晚餐时间和每天的区域跨度；草案已可用，不会无限等待。",
                    ),
                    active_day_index=fallback[-1].dayIndex if fallback else None,
                )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail=f"AI 优化超过 {int(timeout)} 秒，已自动采用通过时间约束的路线草案。",
            ) from exc
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def _generate_with_ai(
        self,
        request: AiPlanGenerationRequest,
        city_name: str,
        candidates: list[PlaceSummary],
        fallback: list[AiGeneratedDay],
        progress: ProgressCallback | None,
    ) -> dict[str, Any]:
        ordered_candidates = sorted(
            candidates,
            key=lambda place: (
                0 if place.category in {"transport", "lodging"} else 1,
                -self._quality_score(place),
            ),
        )
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
                "rating": place.rating,
                "openingHoursToday": place.openingHoursToday,
                "openingHoursWeek": place.openingHoursWeek,
            }
            for place in ordered_candidates[: min(len(ordered_candidates), max(24, request.dayCount * 7))]
        ]
        prompt = {
            "destination": city_name,
            "dateRange": request.dateRange,
            "dayCount": request.dayCount,
            "preferences": self._clean_preferences(request.preferences),
            "freeText": (request.freeText or "").strip(),
            "arrivalStation": (request.arrivalStation or "").strip(),
            "arrivalDay": request.arrivalDay,
            "arrivalTime": request.arrivalTime,
            "departureStation": (request.departureStation or "").strip(),
            "departureDay": request.departureDay or request.dayCount,
            "departureTime": request.departureTime,
            "hotelName": (request.hotelName or "").strip(),
            "hotelStays": [stay.model_dump() for stay in request.hotelStays],
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
                    "综合用户偏好、地点类别、行政区、经纬度、评分和开放时间，尽量让同一天的地点相近。"
                    "只有用户明确给出车站、机场或酒店时才能加入；按其到达、离开和入住日期作为硬锚点。"
                    "餐饮放在11:30-13:30或17:30-19:30，并位于前后景点的通勤链上。"
                    "景点的游览区间必须完全落在已提供的开放时间内；缺少开放时间时仅安排在09:30-16:30。"
                    f"旅行节奏为 {request.pace}，每天目标地点数为 {PACE_PLACE_COUNTS[request.pace]}，"
                    f"每日活动必须处于 {request.dailyStart}-{request.dailyEnd}，交通偏好为 {request.transportPreference}。"
                    "同一地点不可重复。输出 NDJSON（每一物理行都是独立 JSON，不要 Markdown）。"
                    "规划过程中先连续输出若干可审计事件："
                    "{\"kind\":\"event\",\"type\":\"MODEL_REASON\",\"message\":\"不超过120字\","
                    "\"dayIndex\":1,\"evidence\":[\"输入或候选数据事实\"],\"decision\":\"采取的可见决策\"}。"
                    "这些是简短决策摘要，不要声称或输出隐藏思维链。最后仅输出一行结果："
                    "{\"kind\":\"result\",\"plan\":{\"title\":\"\",\"days\":[{\"dayIndex\":1,\"title\":\"\","
                    "\"summary\":\"\",\"places\":[{\"sourcePoiId\":\"\",\"start\":\"09:00\","
                    "\"end\":\"10:30\",\"note\":\"不超过35字的真实可核验游玩建议\"}]}]}}。"
                    "无法确认票价、营业时间或预约规则时不要编造。"
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ]
        final_payload: dict[str, Any] | None = None
        line_buffer = ""
        emitted_messages: set[str] = set()

        def consume_line(line: str) -> None:
            nonlocal final_payload
            line = line.strip()
            if not line:
                return
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                return
            if not isinstance(item, dict):
                return
            if item.get("kind") == "result" and isinstance(item.get("plan"), dict):
                final_payload = item["plan"]
                return
            if item.get("kind") != "event":
                return
            message = self._clean_text(item.get("message"), "模型正在比较候选地点。", 160)
            if message in emitted_messages:
                return
            emitted_messages.add(message)
            raw_day = self._safe_int(item.get("dayIndex"))
            day_index = raw_day if raw_day and 1 <= raw_day <= request.dayCount else None
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            self._notify(
                progress,
                min(85, 75 + len(emitted_messages)),
                message,
                len(fallback),
                partial_days=fallback,
                event=self._event(
                    "MODEL_REASON",
                    message,
                    day_index=day_index,
                    evidence=[str(value)[:120] for value in evidence if str(value).strip()][:8],
                    decision=self._clean_text(item.get("decision"), "继续校验候选顺序。", 240),
                ),
                active_day_index=day_index,
            )

        def on_delta(delta: str) -> None:
            nonlocal line_buffer
            line_buffer += delta
            while "\n" in line_buffer:
                line, line_buffer = line_buffer.split("\n", 1)
                consume_line(line)

        if hasattr(self._ark_client, "chat_stream"):
            raw = await self._ark_client.chat_stream(
                messages,
                on_delta=on_delta,
                max_tokens=min(5000, max(2200, request.dayCount * 650)),
                temperature=0.25,
                timeout_seconds=self._ai_optimization_timeout_seconds + 2.0,
            )
            consume_line(line_buffer)
        else:
            raw = await self._ark_client.chat(
                messages,
                max_tokens=min(5000, max(2200, request.dayCount * 650)),
                temperature=0.25,
                timeout_seconds=self._ai_optimization_timeout_seconds + 2.0,
            )
        if final_payload is not None:
            return final_payload
        # Compatibility with existing models and test doubles that still emit
        # one ordinary JSON object instead of NDJSON.
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
                if len(generated_places) >= min(5, len(candidates)):
                    break
                if place.sourcePoiId not in used:
                    used.add(place.sourcePoiId)
                    generated_places.append(place)

            generated_places = self._reschedule_generated_sequence(request, generated_places, day_index)

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

    def _reschedule_generated_sequence(
        self,
        request: AiPlanGenerationRequest,
        places: list[AiGeneratedPlace],
        day_index: int,
    ) -> list[AiGeneratedPlace]:
        summaries = [
            PlaceSummary(
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
                latitude=place.latitude,
                longitude=place.longitude,
                phone=place.phone,
                rating=place.rating,
                costAverage=place.costAverage,
                coverImageUrl=place.thumbnailUrl,
                imageUrls=place.imageUrls,
                businessArea=place.businessArea,
                openingHoursToday=place.openingHoursToday,
                openingHoursWeek=place.openingHoursWeek,
            )
            for place in places
        ]
        return self._schedule_places(request, summaries, day_index)

    def _build_heuristic_days(
        self,
        request: AiPlanGenerationRequest,
        candidates: list[PlaceSummary],
        arrival_anchor: PlaceSummary | None = None,
        departure_anchor: PlaceSummary | None = None,
        hotel_by_name: dict[str, PlaceSummary | None] | None = None,
        city_name: str | None = None,
        weather_forecast: list[AmapWeatherForecastDay] | None = None,
    ) -> list[AiGeneratedDay]:
        scenic = [place for place in candidates if place.category == "scenic"]
        food = sorted(
            (place for place in candidates if place.category in {"food", "drink"}),
            key=lambda place: self._quality_score(place) + self._local_food_score(city_name or request.destination, place),
            reverse=True,
        )
        used: set[str] = set()
        days: list[AiGeneratedDay] = []
        scenic_target = {"RELAXED": 2, "BALANCED": 3, "INTENSIVE": 3}[request.pace]
        hotel_by_name = hotel_by_name or {}
        weather_forecast = weather_forecast or []
        hotel_stays = self._normalized_hotel_stays(request)
        departure_day = request.departureDay or request.dayCount

        for day_index in range(1, request.dayCount + 1):
            weather = weather_forecast[day_index - 1] if day_index <= len(weather_forecast) else None
            ranked_scenic = sorted(
                (place for place in scenic if place.sourcePoiId not in used),
                key=lambda place: self._quality_score(place) + self._weather_place_score(place, weather),
                reverse=True,
            )
            seed = ranked_scenic[0] if ranked_scenic else None
            if seed is None:
                break
            selected = [seed]
            used.add(seed.sourcePoiId)
            full_day = self._is_full_day_scenic(seed)
            target = 1 if full_day else scenic_target
            while len(selected) < target:
                available = [place for place in scenic if place.sourcePoiId not in used]
                if not available:
                    break
                center = selected[-1]
                next_place = min(
                    available,
                    key=lambda place: (
                        self._distance(center, place)
                        - self._quality_score(place) * 0.08
                        - self._weather_place_score(place, weather) * 0.12
                    ),
                )
                selected.append(next_place)
                used.add(next_place.sourcePoiId)

            meal_anchor = selected[min(len(selected) - 1, len(selected) // 2)]
            available_food = [place for place in food if place.sourcePoiId not in used]
            meal = min(
                available_food,
                key=lambda place: self._distance(meal_anchor, place) - self._quality_score(place) * 0.06,
                default=None,
            ) if not full_day else None
            if meal is not None:
                used.add(meal.sourcePoiId)

            sequence: list[PlaceSummary] = []
            start_hotel = self._hotel_for_day_start(day_index, hotel_stays, hotel_by_name)
            end_hotel = self._hotel_for_day_end(day_index, hotel_stays, hotel_by_name)
            if day_index == request.arrivalDay and arrival_anchor is not None:
                sequence.append(arrival_anchor)
                if end_hotel is not None:
                    sequence.append(end_hotel)
            elif start_hotel is not None:
                sequence.append(start_hotel)
            if selected:
                sequence.append(selected[0])
                if meal is not None:
                    sequence.append(meal)
                sequence.extend(selected[1:])
            if end_hotel is not None and (not sequence or sequence[-1].id != end_hotel.id):
                sequence.append(end_hotel)
            if day_index == departure_day and departure_anchor is not None:
                sequence.append(departure_anchor)
            generated_places = self._schedule_places(request, sequence, day_index)
            if not generated_places:
                continue
            area = next(
                (place.districtName for place in selected if place.districtName),
                request.destination,
            )
            days.append(
                AiGeneratedDay(
                    dayIndex=day_index,
                    title=f"DAY {day_index} · {area}",
                    summary=(
                        "全天型景区按园区规则安排，午餐优先园内餐饮或符合规定的便携简餐。"
                        if full_day
                        else "按天气、开放时间、地点质量与通勤成本成组，餐馆位于相邻游览点通勤链上。"
                    ),
                    places=generated_places,
                    weather=weather.text if weather is not None else None,
                    estimatedDistanceKm=self._day_distance(generated_places),
                    intensity=self._intensity_count(len(generated_places)),
                ),
            )
        return days

    async def _apply_actual_routes(
        self,
        request: AiPlanGenerationRequest,
        days: list[AiGeneratedDay],
        weather_forecast: list[AmapWeatherForecastDay],
        progress: ProgressCallback | None,
    ) -> list[AiGeneratedDay]:
        """Re-time every day with door-to-door route durations from AMap.

        Route failures are never presented as verified data.  A conservative
        estimate keeps the draft usable while the warning remains attached to
        the affected leg and visible in the structured progress stream.
        """
        if not days:
            return days
        if self._route_service is None:
            return days

        routed_days: list[AiGeneratedDay] = []
        total_legs = sum(max(0, len(day.places) - 1) for day in days)
        completed_legs = 0
        for day in days:
            weather = weather_forecast[day.dayIndex - 1] if day.dayIndex <= len(weather_forecast) else None
            weather_text = f"{weather.day_weather}{weather.night_weather}" if weather else ""
            allow_cycling = not any(word in weather_text for word in ("雨", "雪", "雷", "冰雹", "大风", "沙尘"))
            trip_date = self._trip_date(request, day.dayIndex)
            retained: list[AiGeneratedPlace] = []
            transfers: list[AiGeneratedTransfer] = []

            for original in day.places:
                if not retained:
                    retained.append(original.model_copy(deep=True))
                    continue

                previous = retained[-1]
                departure_time = previous.suggestedEnd
                warning: str | None = None
                verified = True
                try:
                    segment = await self._route_service.best_segment(
                        origin=self._to_route_place(previous),
                        destination=self._to_route_place(original),
                        preference=request.transportPreference,
                        departure_date=trip_date.strftime("%Y-%m-%d") if trip_date else None,
                        departure_time=departure_time,
                        allow_cycling=allow_cycling,
                    )
                    distance_meters = max(0, segment.distanceMeters)
                    duration_minutes = max(1, math.ceil(segment.durationSeconds / 60))
                    mode = segment.mode
                    warning = segment.warning
                except HTTPException as exc:
                    verified = False
                    direct_km = self._distance_coordinates(
                        previous.latitude,
                        previous.longitude,
                        original.latitude,
                        original.longitude,
                    )
                    distance_meters = max(1, round(direct_km * 1350))
                    duration_minutes = max(15, round(12 + direct_km * 6))
                    mode = "walking" if direct_km <= 1.5 else "driving"
                    warning = f"实时路线不可用，采用保守预留：{exc.detail}"

                earliest = self._time_to_minutes(previous.suggestedEnd) + duration_minutes
                adjusted = self._fit_place_after_route(request, original, day.dayIndex, earliest)
                if adjusted is None:
                    self._notify(
                        progress,
                        min(92, 75 + round(12 * completed_legs / max(total_legs, 1))),
                        f"{original.name} 与营业或离开时间冲突，已从第 {day.dayIndex} 天移除",
                        len(routed_days),
                        partial_days=[*routed_days, day.model_copy(update={"places": retained}, deep=True)],
                        event=self._event(
                            "TIME_WINDOW_CHECK",
                            f"从 {previous.name} 出发后最早 {self._minutes_to_time(earliest)} 到达，{original.name} 无可用参观时段。",
                            day_index=day.dayIndex,
                            place_id=original.id,
                            evidence=[f"通勤 {duration_minutes} 分钟", original.openingHoursWeek or original.openingHoursToday or "开放时间未知"],
                            decision="移除冲突地点，不把闭馆时段包装成可执行行程。",
                        ),
                        active_day_index=day.dayIndex,
                    )
                    continue

                retained.append(adjusted)
                transfers.append(
                    AiGeneratedTransfer(
                        originPlaceId=previous.id,
                        destinationPlaceId=adjusted.id,
                        mode=mode,
                        distanceMeters=distance_meters,
                        durationMinutes=duration_minutes,
                        verified=verified,
                        warning=warning,
                    ),
                )
                completed_legs += 1
                self._notify(
                    progress,
                    min(92, 75 + round(12 * completed_legs / max(total_legs, 1))),
                    f"已核验 {previous.name} → {adjusted.name} 的实际通勤",
                    len(routed_days),
                    event=self._event(
                        "ROUTE_CHECK",
                        f"{previous.name} → {adjusted.name}：{mode}，约 {duration_minutes} 分钟、{distance_meters / 1000:.1f} 公里。",
                        day_index=day.dayIndex,
                        place_id=adjusted.id,
                        evidence=[f"高德路线方式 {mode}" if verified else "实时路线失败后的保守预留", f"{departure_time} 出发"],
                        decision=(
                            f"把 {adjusted.name} 调整到 {adjusted.suggestedStart}-{adjusted.suggestedEnd}。"
                            + (f" {warning}" if warning else "")
                        ),
                    ),
                    active_day_index=day.dayIndex,
                )

            routed_days.append(
                day.model_copy(
                    update={
                        "places": retained,
                        "transfers": transfers,
                        "estimatedDistanceKm": round(sum(item.distanceMeters for item in transfers) / 1000, 1),
                        "intensity": self._intensity(retained),
                    },
                    deep=True,
                ),
            )
        return routed_days

    def _fit_place_after_route(
        self,
        request: AiPlanGenerationRequest,
        place: AiGeneratedPlace,
        day_index: int,
        earliest: int,
    ) -> AiGeneratedPlace | None:
        duration = max(20, self._time_to_minutes(place.suggestedEnd) - self._time_to_minutes(place.suggestedStart))
        departure_day = request.departureDay or request.dayCount
        day_end = self._time_to_minutes(request.dailyEnd)
        if day_index == departure_day and request.departureTime:
            day_end = min(day_end, self._time_to_minutes(request.departureTime))

        summary = self._generated_to_summary(place)
        start = earliest
        if place.category == "transport" and day_index == departure_day and request.departureTime:
            start = self._time_to_minutes(request.departureTime) - duration
            if earliest > start:
                return None
        elif place.category == "scenic":
            if not self._is_open_on_trip_day(summary, request, day_index):
                return None
            ranges = self._opening_ranges_for_day(summary, request, day_index)
            if ranges:
                slot = self._find_open_slot(ranges, earliest, duration)
                if slot is None:
                    return None
                start = slot[0]
            else:
                start = max(earliest, 9 * 60 + 30)
                day_end = min(day_end, 17 * 60 + 30)
        elif place.category in {"food", "drink"}:
            original_start = self._time_to_minutes(place.suggestedStart)
            meal_start = 11 * 60 + 30 if original_start < 15 * 60 else 17 * 60 + 30
            meal_end = 13 * 60 + 30 if meal_start < 15 * 60 else 19 * 60 + 30
            start = max(earliest, meal_start)
            ranges = self._opening_ranges_for_day(summary, request, day_index)
            if ranges:
                slot = self._find_open_slot(ranges, start, duration)
                if slot is None:
                    return None
                start = slot[0]
            if start + duration > meal_end:
                return None

        if start + duration > day_end:
            return None
        return place.model_copy(
            update={
                "suggestedStart": self._minutes_to_time(start),
                "suggestedEnd": self._minutes_to_time(start + duration),
            },
            deep=True,
        )

    def _to_route_place(self, place: AiGeneratedPlace) -> RoutePlace:
        return RoutePlace(
            id=place.id,
            name=place.name,
            latitude=place.latitude,
            longitude=place.longitude,
            address=place.address,
            cityName=place.cityName,
            adCode=place.adCode,
            cityCode=place.cityCode,
        )

    def _generated_to_summary(self, place: AiGeneratedPlace) -> PlaceSummary:
        return PlaceSummary(
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
            latitude=place.latitude,
            longitude=place.longitude,
            phone=place.phone,
            rating=place.rating,
            costAverage=place.costAverage,
            coverImageUrl=place.thumbnailUrl,
            imageUrls=place.imageUrls,
            businessArea=place.businessArea,
            openingHoursToday=place.openingHoursToday,
            openingHoursWeek=place.openingHoursWeek,
        )

    def _normalized_hotel_stays(self, request: AiPlanGenerationRequest) -> list[tuple[str, int, int]]:
        if request.hotelStays:
            return [
                (stay.name.strip(), stay.checkInDay, stay.checkOutDay)
                for stay in request.hotelStays
                if stay.name.strip()
            ]
        if request.hotelName and request.hotelName.strip():
            return [(request.hotelName.strip(), 1, request.dayCount)]
        return []

    def _hotel_for_day_start(
        self,
        day_index: int,
        stays: list[tuple[str, int, int]],
        hotel_by_name: dict[str, PlaceSummary | None],
    ) -> PlaceSummary | None:
        name = next((name for name, check_in, check_out in stays if check_in < day_index <= check_out), None)
        return hotel_by_name.get(name) if name else None

    def _hotel_for_day_end(
        self,
        day_index: int,
        stays: list[tuple[str, int, int]],
        hotel_by_name: dict[str, PlaceSummary | None],
    ) -> PlaceSummary | None:
        name = next((name for name, check_in, check_out in stays if check_in <= day_index < check_out), None)
        return hotel_by_name.get(name) if name else None

    def _weather_place_score(
        self,
        place: PlaceSummary,
        weather: AmapWeatherForecastDay | None,
    ) -> float:
        if weather is None:
            return 0.0
        text = f"{weather.day_weather}{weather.night_weather}"
        adverse = any(word in text for word in ("雨", "雪", "雷", "冰雹", "沙尘", "大风", "雾"))
        try:
            high = float(weather.day_temp or 0)
            low = float(weather.night_temp or 99)
        except ValueError:
            high, low = 0.0, 99.0
        extreme = high >= 33 or low <= 5
        indoor = self._is_indoor_place(place)
        if adverse or extreme:
            return 8.0 if indoor else -7.0
        if any(word in text for word in ("晴", "多云")) and not indoor:
            return 2.0
        return 0.0

    def _is_indoor_place(self, place: PlaceSummary) -> bool:
        text = f"{place.name} {place.typeName or ''}"
        return any(
            word in text
            for word in ("博物馆", "美术馆", "展览馆", "科技馆", "纪念馆", "室内", "剧院", "商场", "书店")
        )

    def _is_full_day_scenic(self, place: PlaceSummary) -> bool:
        text = f"{place.name} {place.typeName or ''}"
        return any(
            word in text
            for word in (
                "迪士尼", "环球影城", "欢乐谷", "长隆", "九寨沟", "黄山", "华山", "泰山", "峨眉山", "武夷山",
            )
        )

    def _local_food_score(self, city_name: str, place: PlaceSummary) -> float:
        city = city_name.rstrip("市")
        characteristic_words = {
            "北京": ("烤鸭", "炸酱面", "涮肉", "北京菜", "老字号", "卤煮"),
            "上海": ("本帮", "生煎", "小笼", "红烧肉"),
            "成都": ("川菜", "火锅", "串串", "担担面", "钟水饺"),
            "重庆": ("重庆火锅", "小面", "江湖菜"),
            "西安": ("肉夹馍", "泡馍", "凉皮", "陕菜"),
            "广州": ("粤菜", "早茶", "烧鹅", "肠粉"),
            "南京": ("盐水鸭", "鸭血粉丝", "金陵"),
            "杭州": ("杭帮菜", "西湖醋鱼", "龙井虾仁"),
        }.get(city, (city, "特色", "老字号"))
        bonus = 6.0 if any(word in place.name or word in (place.typeName or "") for word in characteristic_words) else 0.0
        if any(chain in place.name for chain in ("麦当劳", "肯德基", "星巴克", "汉堡王", "必胜客")):
            bonus -= 12.0
        return bonus

    def _schedule_places(
        self,
        request: AiPlanGenerationRequest,
        places: list[PlaceSummary],
        day_index: int,
    ) -> list[AiGeneratedPlace]:
        current = self._time_to_minutes(request.dailyStart)
        day_end = self._time_to_minutes(request.dailyEnd)
        departure_day = request.departureDay or request.dayCount
        if day_index == request.arrivalDay and request.arrivalTime:
            current = max(current, self._time_to_minutes(request.arrivalTime))
        if day_index == departure_day and request.departureTime:
            day_end = min(day_end, self._time_to_minutes(request.departureTime))
        generated: list[AiGeneratedPlace] = []
        meal_count = 0
        previous: PlaceSummary | None = None

        for position, place in enumerate(places):
            if previous is not None:
                transfer_minutes = min(55, max(15, round(self._distance(previous, place) * 8)))
                current += transfer_minutes
            duration = 360 if self._is_full_day_scenic(place) else self._visit_duration_minutes(place.category, request.pace)
            opening_ranges = self._opening_ranges_for_day(place, request, day_index)
            has_opening_data = bool(opening_ranges)
            if place.category == "scenic" and not self._is_open_on_trip_day(place, request, day_index):
                continue

            if place.category == "scenic":
                if has_opening_data:
                    slot = self._find_open_slot(opening_ranges, current, duration)
                    if slot is None:
                        continue
                    current = slot[0]
                    verified = True
                else:
                    current = max(current, 9 * 60 + 30)
                    if current + duration > 17 * 60 + 30:
                        continue
                    verified = False
            elif place.category in {"food", "drink"}:
                desired = 11 * 60 + 30 if meal_count == 0 else 17 * 60 + 30
                current = max(current, desired)
                if has_opening_data:
                    slot = self._find_open_slot(opening_ranges, current, duration)
                    if slot is None:
                        continue
                    current = slot[0]
                    verified = True
                else:
                    verified = False
                meal_count += 1
            elif place.category == "lodging":
                duration = 45
                verified = False
            elif place.category == "transport":
                duration = 40
                verified = False
                is_arrival = (
                    day_index == request.arrivalDay
                    and request.arrivalStation
                    and self._anchor_name_matches(place.name, request.arrivalStation)
                )
                is_departure = (
                    day_index == departure_day
                    and request.departureStation
                    and self._anchor_name_matches(place.name, request.departureStation)
                )
                if is_arrival and request.arrivalTime:
                    current = max(current, self._time_to_minutes(request.arrivalTime))
                if is_departure and request.departureTime:
                    current = max(current, self._time_to_minutes(request.departureTime) - duration)
            else:
                verified = False

            if current + duration > day_end:
                break
            start = self._minutes_to_time(current)
            end = self._minutes_to_time(current + duration)
            note = self._schedule_note(place, verified)
            generated.append(
                self._to_generated_place(
                    place,
                    position,
                    {"start": start, "end": end, "note": note},
                    request,
                    schedule_verified=verified,
                ),
            )
            current += duration
            previous = place
        return generated

    def _visit_duration_minutes(self, category: str, pace: str) -> int:
        if category in {"food", "drink"}:
            return 75
        if category == "scenic":
            return {"RELAXED": 120, "BALANCED": 105, "INTENSIVE": 90}[pace]
        return 60

    def _anchor_name_matches(self, actual: str, requested: str) -> bool:
        left = re.sub(r"\s+", "", actual)
        right = re.sub(r"\s+", "", requested)
        return bool(left and right and (left in right or right in left))

    def _opening_window(self, place: PlaceSummary) -> tuple[int | None, int | None, bool]:
        ranges = self._opening_ranges(place)
        if ranges:
            start, end = max(ranges, key=lambda item: item[1] - item[0])
            return start, end, True
        return None, None, False

    def _opening_ranges(self, place: PlaceSummary) -> list[tuple[int, int]]:
        today = self._parse_time_ranges(place.openingHoursToday)
        return today or self._parse_time_ranges(place.openingHoursWeek)

    def _find_open_slot(
        self,
        ranges: list[tuple[int, int]],
        earliest: int,
        duration: int,
    ) -> tuple[int, int] | None:
        for open_start, open_end in sorted(ranges):
            start = max(earliest, open_start)
            if start + duration <= open_end:
                return start, start + duration
        return None

    def _opening_ranges_for_day(
        self,
        place: PlaceSummary,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> list[tuple[int, int]]:
        trip_date = self._trip_date(request, day_index)
        week_text = place.openingHoursWeek or ""
        if week_text:
            if trip_date is not None and "周" in week_text:
                day_char = "一二三四五六日"[trip_date.weekday()]
                segments = [part.strip() for part in re.split(r"[；;。]", week_text) if part.strip()]
                explicit_segments = [part for part in segments if "周" in part]
                matching_ranges = [
                    time_range
                    for part in explicit_segments
                    if self._weekday_segment_applies(part, day_char)
                    for time_range in self._parse_time_ranges(part)
                ]
                if matching_ranges:
                    return matching_ranges
                if explicit_segments:
                    return []
            week_ranges = self._parse_time_ranges(week_text)
            if week_ranges:
                return week_ranges
        if trip_date is not None and trip_date.date() == datetime.now().date():
            return self._parse_time_ranges(place.openingHoursToday)
        return []

    def _weekday_segment_applies(self, text: str, day_char: str) -> bool:
        day_chars = "一二三四五六日"
        allowed: set[str] = set()
        for start, end in re.findall(r"周([一二三四五六日])\s*(?:至|-|—)\s*周?([一二三四五六日])", text):
            start_index = day_chars.index(start)
            end_index = day_chars.index(end)
            if start_index <= end_index:
                allowed.update(day_chars[start_index : end_index + 1])
            else:
                allowed.update(day_chars[start_index:] + day_chars[: end_index + 1])
        if not allowed:
            allowed.update(re.findall(r"周([一二三四五六日])", text))
        return not allowed or day_char in allowed

    def _is_open_on_trip_day(
        self,
        place: PlaceSummary,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> bool:
        text = place.openingHoursWeek or ""
        trip_date = self._trip_date(request, day_index)
        if not text or trip_date is None or "周" not in text:
            return True
        day_chars = "一二三四五六日"
        day_char = day_chars[trip_date.weekday()]
        if re.search(rf"周{day_char}[^；;。]*(?:闭馆|休息|不开放)", text):
            return False
        allowed: set[str] = set()
        for start, end in re.findall(r"周([一二三四五六日])\s*至\s*周?([一二三四五六日])", text):
            start_index = day_chars.index(start)
            end_index = day_chars.index(end)
            if start_index <= end_index:
                allowed.update(day_chars[start_index : end_index + 1])
        allowed.update(re.findall(r"周([一二三四五六日])", text))
        return not allowed or day_char in allowed

    def _trip_date(self, request: AiPlanGenerationRequest, day_index: int) -> datetime | None:
        match = re.search(r"(\d{1,2})[.\-/](\d{1,2})", request.dateRange)
        if match is None:
            return None
        try:
            start = datetime(datetime.now().year, int(match.group(1)), int(match.group(2)))
        except ValueError:
            return None
        return start + timedelta(days=max(0, day_index - 1))

    def _parse_time_ranges(self, value: str | None) -> list[tuple[int, int]]:
        if not value:
            return []
        ranges: list[tuple[int, int]] = []
        for start, end in re.findall(
            r"((?:[01]?\d|2[0-3]):[0-5]\d)\s*[-—至]\s*((?:[01]?\d|2[0-3]):[0-5]\d)",
            value,
        ):
            start_minutes = self._time_to_minutes(self._normalize_hour(start))
            end_minutes = self._time_to_minutes(self._normalize_hour(end))
            if end_minutes > start_minutes:
                ranges.append((start_minutes, end_minutes))
        return ranges

    def _normalize_hour(self, value: str) -> str:
        hour, minute = value.split(":", 1)
        return f"{int(hour):02d}:{minute}"

    def _schedule_note(self, place: PlaceSummary, verified: bool) -> str:
        hours = place.openingHoursToday or place.openingHoursWeek
        if place.category == "transport":
            return "抵达后预留约 40 分钟用于出站、取行李和换乘。"
        if place.category == "lodging":
            return "先寄存行李或办理入住；实际入住时间以酒店政策为准。"
        if place.category in {"food", "drink"}:
            return f"安排在正常用餐时段。{f'高德营业信息：{hours}' if verified and hours else '营业时间请在详情页确认。'}"
        if verified and hours:
            return f"游览时间已落在高德开放时段内：{hours}"
        return "开放时间数据暂缺，已保守安排在 09:30-17:30；出发前请在详情页确认。"

    def _to_generated_place(
        self,
        place: PlaceSummary,
        position: int,
        ai: dict[str, Any],
        request: AiPlanGenerationRequest,
        schedule_verified: bool | None = None,
    ) -> AiGeneratedPlace:
        default_start, default_end = self._default_slot(request, position)
        proposed_start = self._clean_time(ai.get("start"), default_start)
        proposed_end = self._clean_time(ai.get("end"), default_end)
        suggested_start, suggested_end, automatically_verified = self._validated_slot(
            place,
            proposed_start,
            proposed_end,
            request,
        )
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
            phone=place.phone,
            rating=place.rating,
            costAverage=place.costAverage,
            businessArea=place.businessArea,
            openingHoursToday=place.openingHoursToday,
            openingHoursWeek=place.openingHoursWeek,
            scheduleVerified=(
                schedule_verified
                if schedule_verified is not None
                else automatically_verified
            ),
            suggestedStart=suggested_start,
            suggestedEnd=suggested_end,
            note=self._clean_text(
                ai.get("note"),
                "根据地点实际开放信息安排停留，出发前建议再次确认。",
                80,
            ),
        )

    def _validated_slot(
        self,
        place: PlaceSummary,
        start: str,
        end: str,
        request: AiPlanGenerationRequest,
    ) -> tuple[str, str, bool]:
        start_minutes = self._time_to_minutes(start)
        end_minutes = self._time_to_minutes(end)
        duration = max(45, end_minutes - start_minutes)
        opening_ranges = self._opening_ranges(place)
        if opening_ranges:
            slot = self._find_open_slot(opening_ranges, start_minutes, duration)
            if slot is None:
                slot = self._find_open_slot(opening_ranges, 0, duration)
            if slot is not None:
                return self._minutes_to_time(slot[0]), self._minutes_to_time(slot[1]), True
        if place.category == "scenic":
            conservative_start = max(start_minutes, 9 * 60 + 30)
            conservative_end = min(conservative_start + duration, 17 * 60 + 30)
            if conservative_end - conservative_start < 45:
                conservative_start = 15 * 60 + 45
                conservative_end = 17 * 60 + 15
            return self._minutes_to_time(conservative_start), self._minutes_to_time(conservative_end), False
        if place.category in {"food", "drink"}:
            meal_start = 11 * 60 + 30 if start_minutes < 15 * 60 else 17 * 60 + 30
            meal_end = min(meal_start + duration, self._time_to_minutes(request.dailyEnd))
            return self._minutes_to_time(meal_start), self._minutes_to_time(meal_end), False
        return start, end, False

    def _slot_is_within_opening_hours(self, place: PlaceSummary, start: str, end: str) -> bool:
        open_start, open_end, verified = self._opening_window(place)
        if not verified or open_start is None or open_end is None:
            return False
        start_minutes = self._time_to_minutes(start)
        end_minutes = self._time_to_minutes(end)
        return open_start <= start_minutes < end_minutes <= open_end

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
        departure_day = request.departureDay or request.dayCount
        if request.arrivalDay > request.dayCount or departure_day > request.dayCount:
            raise HTTPException(status_code=422, detail="到达或离开日期必须位于旅行天数内。")
        if departure_day < request.arrivalDay:
            raise HTTPException(status_code=422, detail="离开日期不能早于到达日期。")
        if (
            departure_day == request.arrivalDay
            and request.arrivalTime
            and request.departureTime
            and self._time_to_minutes(request.departureTime) <= self._time_to_minutes(request.arrivalTime)
        ):
            raise HTTPException(status_code=422, detail="同一天离开时间必须晚于到达时间。")
        for stay in request.hotelStays:
            if stay.checkInDay >= stay.checkOutDay:
                raise HTTPException(status_code=422, detail=f"{stay.name} 的退房日必须晚于入住日。")
            if stay.checkInDay > request.dayCount or stay.checkOutDay > request.dayCount + 1:
                raise HTTPException(status_code=422, detail=f"{stay.name} 的入住区间超出旅行日期。")
        ordered_stays = sorted(request.hotelStays, key=lambda stay: (stay.checkInDay, stay.checkOutDay))
        for previous, current in zip(ordered_stays, ordered_stays[1:]):
            if current.checkInDay < previous.checkOutDay:
                raise HTTPException(status_code=422, detail="酒店入住区间存在重叠，请按退房日衔接下一家酒店。")

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
