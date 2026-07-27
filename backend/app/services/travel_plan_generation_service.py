from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Callable

from fastapi import HTTPException

from app.schemas.ai import (
    AiGeneratedDay,
    AiGeneratedPlace,
    AiGeneratedTransfer,
    AiPlanAlternative,
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
from app.services.deepseek_client import DeepSeekClient
from app.services.itinerary_constraint_solver import (
    CandidateScore,
    DaySolverConfig,
    TimeWindow,
    TravelEdge,
    VisitCandidate,
    improve_day_partition,
    partition_by_geography,
    proximity_score,
    solve_day_with_time_windows,
)
from app.services.popular_poi_catalog import POPULAR_POI_SEEDS
from app.services.visit_unit_service import resolve_visit_units


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

@dataclass(frozen=True)
class PaceProfile:
    request_place_count: int
    scenic_target: int
    minimum_full_day_units: int
    scenic_visit_minutes: int
    minimum_visit_ratio: float
    max_normal_leg_minutes: int
    max_fill_leg_minutes: int
    max_idle_minutes: int
    minimum_underfilled_gain: float


PACE_PROFILES = {
    "RELAXED": PaceProfile(3, 2, 1, 120, 0.25, 30, 30, 55, 0.01),
    "BALANCED": PaceProfile(4, 3, 2, 105, 0.48, 40, 50, 45, -0.85),
    "INTENSIVE": PaceProfile(5, 4, 3, 90, 0.60, 50, 60, 35, -1.10),
}
PACE_PLACE_COUNTS = {
    pace: profile.request_place_count for pace, profile in PACE_PROFILES.items()
}
PACE_SCENIC_TARGETS = {
    pace: profile.scenic_target for pace, profile in PACE_PROFILES.items()
}
PACE_LABELS = {"RELAXED": "轻松", "BALANCED": "适中", "INTENSIVE": "充实"}


class TravelPlanGenerationService:
    def __init__(
        self,
        model_client: DeepSeekClient,
        poi_service: AmapPoiService,
        route_service: AmapRouteService | None = None,
        weather_service: AmapWeatherService | None = None,
        reveal_delay_seconds: float = 0.0,
        place_detail_service: Any | None = None,
    ) -> None:
        self._model_client = model_client
        self._poi_service = poi_service
        self._route_service = route_service
        self._weather_service = weather_service
        self._reveal_delay_seconds = reveal_delay_seconds
        self._place_detail_service = place_detail_service
        self._ai_review_cache: dict[str, dict[str, Any]] = {}

    async def generate(
        self,
        request: AiPlanGenerationRequest,
        progress: ProgressCallback | None = None,
    ) -> AiPlanGenerationResponse:
        generation_started_at = perf_counter()
        self._validate_time_window(request)
        self._notify(progress, 5, "正在理解目的地与旅行约束")
        destination = request.destination.strip()
        cities = await self._poi_service.search_cities(keyword=destination, limit=5)
        if not cities:
            raise HTTPException(status_code=422, detail="没有找到这个目的地，请输入城市名称后重试。")

        city = cities[0]
        self._validate_map_point_cities(request, city.adCode, city.name)
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
        required_place_queries = self._named_constraint_queries(request, required=True)
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
        recall_keywords = [
            f"{city.name.rstrip('市')}热门景点",
            *self._preference_recall_keywords(city.name, request.preferences, request.freeText),
        ]
        for keyword in dict.fromkeys(recall_keywords):
            search_tasks.append(
                self._poi_service.search_pois(
                    keyword=keyword,
                    adcode=city.adCode,
                    category="scenic",
                    page=1,
                    page_size=min(16, max(8, request.dayCount * 4)),
                    city_limit=True,
                ),
            )
        first_visit_seeds = [
            seed
            for seed in POPULAR_POI_SEEDS
            if self._normalized_region(seed.city) == self._normalized_region(city.name)
        ][:8]
        for seed in first_visit_seeds:
            search_tasks.append(
                self._poi_service.search_pois(
                    keyword=seed.name,
                    adcode=city.adCode,
                    category="scenic",
                    page=1,
                    page_size=8,
                    city_limit=True,
                ),
            )
        if any(
            self._weather_needs_indoor_recall(day)
            for day in weather_forecast[: request.dayCount]
        ):
            search_tasks.append(
                self._poi_service.search_pois(
                    keyword=f"{city.name.rstrip('市')}博物馆",
                    adcode=city.adCode,
                    category="museum",
                    page=1,
                    page_size=min(16, max(8, request.dayCount * 4)),
                    city_limit=True,
                ),
            )
        for query in required_place_queries:
            search_tasks.append(
                self._poi_service.search_pois(
                    keyword=query,
                    adcode=city.adCode,
                    category="scenic",
                    page=1,
                    page_size=8,
                    city_limit=True,
                ),
            )
        transport_queries = list(
            dict.fromkeys(
                value.strip()
                for value, point in (
                    (request.arrivalStation, request.arrivalPoint),
                    (request.departureStation, request.departurePoint),
                )
                if value and value.strip() and point is None
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
                    *([request.hotelName.strip()] if request.hotelName and request.hotelName.strip() and request.hotelPoint is None else []),
                    *(stay.name.strip() for stay in request.hotelStays if stay.name.strip() and stay.mapPoint is None),
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
            [
                place.model_copy(update={"category": "scenic", "categoryCode": "scenic"})
                if place.category == "museum"
                else place
                for result in search_results
                for place in result.items
            ],
        )
        candidates = [
            place
            for place in candidates
            if (
                not place.adCode
                or self._adcode_belongs_to_city(place.adCode, city.adCode)
            )
            and (
                not place.cityName
                or self._normalized_region(place.cityName) == self._normalized_region(city.name)
                or self._adcode_belongs_to_city(place.adCode or city.adCode, city.adCode)
            )
        ]
        candidates = self._attach_planning_signals(request, candidates)
        candidates = self._attach_visit_unit_signals(candidates)
        official_candidate_count = sum(
            bool(place.officialScenicGrade or place.officialReservationRequired or place.officialClosedDates)
            for place in candidates
        )
        closure_count = sum(bool(place.officialClosedDates) for place in candidates)
        reservation_count = sum(place.officialReservationRequired for place in candidates)
        self._notify(
            progress,
            34,
            "已核对本地官方来源目录与预约约束",
            event=self._event(
                "TIME_WINDOW_CHECK",
                f"{official_candidate_count} 个候选具有官方规划信号；{closure_count} 个存在行程日期闭园约束，"
                f"{reservation_count} 个需要预约。",
                evidence=["仅带明确生效日期的闭园公告作为硬约束", "无日期旧公告只提示复核"],
                decision="闭园候选直接排除；预约要求保留在地点说明和最终验收中。",
            ),
        )
        selected_map_places = [
            self._map_point_summary(request.arrivalPoint, "transport", city.name, city.adCode),
            self._map_point_summary(request.departurePoint, "transport", city.name, city.adCode),
            self._map_point_summary(request.hotelPoint, "lodging", city.name, city.adCode),
            *[
                self._map_point_summary(stay.mapPoint, "lodging", city.name, city.adCode)
                for stay in request.hotelStays
            ],
        ]
        candidates = self._dedupe_candidates([*candidates, *[place for place in selected_map_places if place is not None]])
        if len(candidates) < request.dayCount * 2:
            raise HTTPException(
                status_code=422,
                detail=f"{destination}当前可用的真实地点数据不足，请稍后重试或缩短行程天数。",
            )

        arrival_anchor = self._map_point_summary(request.arrivalPoint, "transport", city.name, city.adCode) or (
            self._select_station(candidates, request.arrivalStation or "") if request.arrivalStation else None
        )
        departure_anchor = (
            self._map_point_summary(request.departurePoint, "transport", city.name, city.adCode)
            or (self._select_station(candidates, request.departureStation or "") if request.departureStation else None)
        )
        if request.arrivalStation and arrival_anchor is None:
            raise HTTPException(
                status_code=422,
                detail=f"没有在 {city.name} 找到到达点“{request.arrivalStation}”，请从城市联想中选择。",
            )
        if request.departureStation and departure_anchor is None:
            raise HTTPException(
                status_code=422,
                detail=f"没有在 {city.name} 找到离开点“{request.departureStation}”，请从城市联想中选择。",
            )
        hotel_by_name = {query: self._select_hotel(candidates, query, arrival_anchor) for query in hotel_queries}
        missing_hotels = [name for name, place in hotel_by_name.items() if place is None]
        if missing_hotels:
            raise HTTPException(
                status_code=422,
                detail=f"没有在 {city.name} 找到住宿“{missing_hotels[0]}”，请从城市联想中选择或使用地图选点。",
            )
        if request.hotelName and request.hotelPoint is not None:
            hotel_by_name[request.hotelName.strip()] = self._map_point_summary(
                request.hotelPoint, "lodging", city.name, city.adCode,
            )
        for stay in request.hotelStays:
            if stay.mapPoint is not None:
                hotel_by_name[stay.name.strip()] = self._map_point_summary(
                    stay.mapPoint, "lodging", city.name, city.adCode,
                )
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
        self._notify(
            progress,
            45,
            "候选地点已按片区和可用时段分配到每天",
            partial_days=fallback,
            event=self._event(
                "CANDIDATE_SCREENED",
                f"已从 {len(candidates)} 个真实地点中完成偏好评分、天气适配和地理分区。",
                evidence=["先按行政区和距离成组", "再校验开放时间与每日可用时段"],
                decision="跨片区移动只有在地点收益足够高时才保留，优先减少折返。",
            ),
        )
        ai_task: asyncio.Task[dict[str, Any]] | None = None
        buffered_ai_updates: list[tuple[int, str, AiPlanProgressEvent | None, int | None]] = []
        visible_fallback: list[AiGeneratedDay] | None = None

        def forward_ai_progress(
            ai_progress: int,
            ai_stage: str,
            _completed_days: int,
            _partial_days: list[AiGeneratedDay] | None = None,
            event: AiPlanProgressEvent | None = None,
            active_day_index: int | None = None,
        ) -> None:
            if visible_fallback is None:
                buffered_ai_updates.append((ai_progress, ai_stage, event, active_day_index))
                return
            self._notify(
                progress,
                ai_progress,
                ai_stage,
                len(visible_fallback),
                partial_days=visible_fallback,
                event=event,
                active_day_index=active_day_index,
            )

        route_started_at = perf_counter()
        try:
            fallback = await self._apply_actual_routes(
                request,
                fallback,
                weather_forecast,
                progress,
                repair_candidates=candidates,
            )
            fallback = await self._repair_underfilled_days(
                request,
                fallback,
                candidates,
                weather_forecast,
                progress,
            )
            missing_required = self._missing_required_place_queries(request, fallback)
            if missing_required:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "真实地点与路线校验后无法满足必去约束："
                        + "、".join(missing_required)
                        + "。请确认名称、日期和预约时间后重试。"
                    ),
                )
            completeness_violations = self._draft_completeness_violations(request, fallback)
            if completeness_violations:
                raise HTTPException(
                    status_code=422,
                    detail="行程无法形成完整的逐日可执行草案：" + "；".join(completeness_violations),
                )
        except BaseException:
            if ai_task is not None and not ai_task.done():
                ai_task.cancel()
                await asyncio.gather(ai_task, return_exceptions=True)
            raise
        route_elapsed_ms = round((perf_counter() - route_started_at) * 1000)
        visible_fallback = fallback
        # The model reviews only the already-routed executable draft. Starting
        # it earlier would let it optimize estimates that AMap may later prove
        # closed, unreachable or too slow.
        if request.optimizationMode != "FAST":
            ai_task = asyncio.create_task(
                self._generate_with_ai(request, city.name, candidates, fallback, forward_ai_progress),
                name="ai-plan-bounded-patch-review",
            )
        await self._publish_draft(progress, fallback)
        self._notify(
            progress,
            73,
            "可执行草案已完成；高德逐段路线校验已通过",
            len(fallback),
            partial_days=fallback,
            event=self._event(
                "ANALYSIS",
                f"路线与时间草案校验完成，用时 {route_elapsed_ms / 1000:.1f} 秒。",
                evidence=["逐日营业时间与高德路线已完成确定性校验"],
                decision="先冻结可执行草案，再允许 AI 提出局部补丁；所有补丁仍需重新验收。",
            ),
            active_day_index=fallback[-1].dayIndex if fallback else None,
        )
        for buffered_progress, buffered_stage, buffered_event, buffered_day_index in buffered_ai_updates:
            self._notify(
                progress,
                buffered_progress,
                buffered_stage,
                len(fallback),
                partial_days=fallback,
                event=buffered_event,
                active_day_index=buffered_day_index,
            )
        warnings: list[str] = []
        model_name: str | None = None if request.optimizationMode == "FAST" else self._model_client.model_name
        used_fallback = False
        data_sources = ["AMAP"]
        if request.optimizationMode == "FAST":
            days = fallback
            self._notify(
                progress,
                88,
                "已按快速模式完成约束规划，跳过大模型优化",
                len(days),
                partial_days=days,
                event=self._event(
                    "PLAN_REFINED",
                    "用户选择快速生成：保留天气、营业时间和真实路线校验结果，不调用大模型。",
                    decision="直接保存可执行草案。",
                ),
                active_day_index=days[-1].dayIndex if days else None,
            )
        else:
            try:
                self._notify(
                    progress,
                    74,
                    "可执行草案已完成，正在进行智能规划",
                    len(fallback),
                    partial_days=fallback,
                    event=self._event(
                        "ANALYSIS",
                        "天气、开放时间和逐段路线草案已经可用；AI 正在审阅体验并准备局部调整。",
                        decision="保持草案可见并持续推送模型事件，不伪造百分比进度。",
                    ),
                    active_day_index=fallback[-1].dayIndex if fallback else None,
                )
                ai_payload = await self._optimize_with_heartbeat(
                    request,
                    city.name,
                    candidates,
                    fallback,
                    progress,
                    task=ai_task,
                )
                traveler_explanation = str(ai_payload.get("travelerExplanation") or "").strip()[:160]
                self._notify(progress, 86, "AI 局部调整已返回，正在复核开放时间与真实路线", len(fallback))
                ai_days = (
                    self._merge_ai_result(request, ai_payload, candidates, fallback)
                    if isinstance(ai_payload.get("days"), list)
                    else self._apply_ai_proposal(request, ai_payload, candidates, fallback)
                )
                ai_days = await self._apply_actual_routes(
                    request,
                    ai_days,
                    weather_forecast,
                    progress,
                    repair_candidates=candidates,
                )
                days, accepted_day_count, review_notes = self._select_ai_optimized_days(
                    request,
                    fallback,
                    ai_days,
                )
                used_fallback = accepted_day_count < len(fallback)
                if accepted_day_count == 0:
                    model_name = None
                no_change_result = accepted_day_count == 0
                self._notify(
                    progress,
                    90,
                    (
                        "AI 未提出可采纳调整，保留可执行草案"
                        if no_change_result
                        else f"AI 建议复核完成，采纳 {accepted_day_count}/{len(fallback)} 天"
                    ),
                    len(days),
                    partial_days=days,
                    event=self._event(
                        "AI_REVIEW",
                        (
                            "AI 未提出通过复核的局部调整，现有规则草案保持不变。"
                            if no_change_result
                            else f"已按营业时间、餐期、锚点、真实通勤和地点质量复核 AI 建议；采纳 {accepted_day_count} 天。"
                        ),
                        evidence=[
                            "已确认闭馆、用户锚点和真实不可达不可违反",
                            "允许为热门程度、偏好和早中晚体验接受合理通勤变化",
                            "不使用固定百分比或单一通勤阈值决定是否采纳",
                            *([f"AI体验说明：{traveler_explanation}"] if traveler_explanation and accepted_day_count else []),
                        ],
                        decision="；".join(review_notes[:3]) or "现有草案已可执行，无需为使用 AI 而强行改动。",
                    ),
                    active_day_index=days[-1].dayIndex if days else None,
                )
                if accepted_day_count > 0:
                    data_sources.append("DEEPSEEK")
            except (ValueError, json.JSONDecodeError, TypeError) as exc:
                days = fallback
                used_fallback = True
                model_name = None
                self._notify(
                    progress,
                    90,
                    "AI 建议未通过复核，已保留可执行草案",
                    len(days),
                    partial_days=days,
                    event=self._event(
                        "AI_REVIEW",
                        "模型已返回，但建议未通过结构、用户锚点或已确认时段校验。",
                        decision="拒绝不可靠建议，采用已完成的规则草案。",
                    ),
                    active_day_index=days[-1].dayIndex if days else None,
                )
            except (HTTPException, asyncio.TimeoutError) as exc:
                days = fallback
                model_name = None
                used_fallback = True
                self._notify(
                    progress,
                    90,
                    "AI 建议未完成，已采用可执行草案",
                    len(days),
                    partial_days=days,
                    event=self._event(
                        "AI_REVIEW",
                        "模型建议没有形成可用正文，规则草案不受影响。",
                        evidence=["AI 编辑层未形成可验证补丁；路线与时段草案已在调用 AI 前完成"],
                        decision="保留已完成的热门地点、偏好、时间窗与真实路线结果。",
                    ),
                    active_day_index=days[-1].dayIndex if days else None,
                )
            except Exception as exc:
                # The executable AMap draft is already complete at this
                # boundary. An unexpected model/merge failure must not turn a
                # usable itinerary into a failed planning task.
                days = fallback
                model_name = None
                used_fallback = True
                self._notify(
                    progress,
                    90,
                    "智能规划的 AI 调整未完成，已采用可执行草案",
                    len(days),
                    partial_days=days,
                    event=self._event(
                        "AI_REVIEW",
                        "AI 调整层发生异常，规则草案不受影响。",
                        evidence=["异常仅发生在可选编辑层，未改变已经验收的地点、时间和交通结果"],
                        decision="保留已完成的热门地点、偏好、时间窗与真实路线结果。",
                    ),
                    active_day_index=days[-1].dayIndex if days else None,
                )

        days = self._attach_day_alternatives(request, days, candidates, weather_forecast)
        alternative_count = sum(len(day.alternatives) for day in days)
        self._notify(
            progress,
            92,
            f"已准备 {alternative_count} 个同片区天气备选地点",
            len(days),
            partial_days=days,
            event=self._event(
                "PLAN_REFINED",
                f"已为可用日期准备 {alternative_count} 个未进入主路线的同片区备选。",
                evidence=["备选地点当日未闭馆", "极端天气硬约束已过滤", "距当天片区约 4 公里内"],
                decision="临时替换后必须重新刷新高德路线，不能沿用生成时交通结果。",
            ),
            active_day_index=days[-1].dayIndex if days else None,
        )
        unverified_transfer_count = sum(
            not transfer.verified
            for day in days
            for transfer in day.transfers
        )
        if unverified_transfer_count:
            warnings.append(
                f"{unverified_transfer_count} 段交通因高德服务未返回可用结果而采用保守预留；"
                "这不等同于地点不可达，请在出发前刷新路线。",
            )
        self._notify(
            progress,
            94,
            "正在生成质量报告并保存结果",
            len(days),
            partial_days=days,
            event=self._event(
                "PLAN_REFINED",
                (
                    f"地点、时间和每日主题已完成校验；{unverified_transfer_count} 段交通待出发前刷新。"
                    if unverified_transfer_count
                    else "地点、时间、真实交通和每日主题均已完成校验。"
                )
                + f" 当前总耗时 {(perf_counter() - generation_started_at):.1f} 秒，正在保存最终版本。",
            ),
            active_day_index=days[-1].dayIndex if days else None,
        )
        all_places = [place for day in days for place in day.places]
        duplicate_count = len(all_places) - len({place.sourcePoiId for place in all_places})
        quality = self._evaluate_plan_quality(request, days, used_fallback, data_sources)
        if quality.longestLegMinutes > PACE_PROFILES[request.pace].max_normal_leg_minutes:
            warnings.append(
                f"最长单段通勤约 {quality.longestLegMinutes} 分钟；这是当前热门地点与时段约束下的保留结果，"
                "可在详情中改用同片区备选。"
            )
        if quality.longIdleGapCount:
            warnings.append(
                f"发现 {quality.longIdleGapCount} 处较长空档，主要由开放时间或夜间活动时段造成；"
                "已作为休息/候场时间保留，请勿按连续游览理解。"
            )
        if quality.minimumClosingMarginMinutes is not None and quality.minimumClosingMarginMinutes < 20:
            warnings.append(
                f"最紧张景点距离闭馆仅余约 {quality.minimumClosingMarginMinutes} 分钟，建议出发前再次确认停止入场时间。"
            )
        if quality.underfilledDayIndexes:
            warnings.append(
                "第 "
                + "、".join(str(index) for index in quality.underfilledDayIndexes)
                + " 天在开放时间、天气和顺路通勤约束下仍低于所选节奏；"
                "系统没有用远距离或不可执行地点强行凑数，可从同片区备选中继续调整。"
            )
        enrichment_batch_id: str | None = None
        if self._place_detail_service is not None and all_places:
            try:
                final_places = [
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
                        officialScenicGrade=place.officialScenicGrade,
                        experienceEvidenceCount=place.experienceEvidenceCount,
                        officialReservationRequired=place.officialReservationRequired,
                        officialReservationNote=place.officialReservationNote,
                        officialClosedDates=place.officialClosedDates,
                        officialClosureWarning=place.officialClosureWarning,
                        officialOpeningHoursByDate=place.officialOpeningHoursByDate,
                        officialAccessNote=place.officialAccessNote,
                        officialMaxDailyCapacity=place.officialMaxDailyCapacity,
                        officialCapacityNote=place.officialCapacityNote,
                        officialTicketNote=place.officialTicketNote,
                        crowdRisk=place.crowdRisk,
                        contentUpdatedAt=place.contentUpdatedAt,
                        visitUnitId=place.visitUnitId,
                        visitUnitName=place.visitUnitName,
                        visitUnitPolicy=place.visitUnitPolicy,
                        visitUnitMemberOrder=place.visitUnitMemberOrder,
                        visitUnitTransferMinutes=place.visitUnitTransferMinutes,
                        visitUnitSourceUrl=place.visitUnitSourceUrl,
                        recommendedVisitMinutes=place.recommendedVisitMinutes,
                    )
                    for place in all_places
                ]
                enrichment = await self._place_detail_service.ensure_batch(final_places)
                enrichment_batch_id = enrichment.batchId
            except Exception:
                # UGC enrichment is optional and must never invalidate a plan
                # whose AMap facts, opening windows and routes already passed.
                enrichment_batch_id = None

        return AiPlanGenerationResponse(
            requestId=str(uuid.uuid4()),
            title=f"{city.name.rstrip('市')} {request.dayCount} 日智能行程",
            destination=city.name,
            dateRange=request.dateRange.strip(),
            dayCount=request.dayCount,
            transportPreference=request.transportPreference,
            preferences=self._clean_preferences(request.preferences),
            days=days,
            warnings=warnings,
            generatedAt=datetime.now(timezone.utc).isoformat(),
            model=model_name,
            enrichmentBatchId=enrichment_batch_id,
            quality=quality.model_copy(
                update={
                    "duplicatePlaceCount": duplicate_count,
                    "totalPlaceCount": len(all_places),
                },
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
            duplicate_index = next(
                (
                    index
                    for index, existing in enumerate(result)
                    if self._same_real_world_place(place, existing)
                ),
                None,
            )
            if duplicate_index is not None:
                existing = result[duplicate_index]
                if self._dedupe_preference_score(place) > self._dedupe_preference_score(existing):
                    result[duplicate_index] = place
                    seen.add(place.sourcePoiId)
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
        left_complex = self._attraction_complex_key(left_name)
        right_complex = self._attraction_complex_key(right_name)
        if left_complex and left_complex == right_complex and distance <= 1.8:
            return True
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

    @staticmethod
    def _normalized_place_name(name: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]", "", name).lower()

    @staticmethod
    def _attraction_complex_key(normalized_name: str) -> str:
        if "天安门" in normalized_name and not any(
            word in normalized_name
            for word in ("地铁", "公交", "停车", "派出所", "街道办", "医院", "饭店", "宾馆")
        ):
            return "天安门核心游览区"
        if "故宫博物院" in normalized_name or normalized_name in {"故宫", "北京故宫"}:
            return "故宫博物院"
        return ""

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

    def _preference_recall_keywords(
        self,
        city_name: str,
        preferences: list[str],
        free_text: str | None,
    ) -> list[str]:
        """Recall well-known attractions that match the user's stated interests."""
        city = city_name.rstrip("市")
        text = " ".join([*preferences, free_text or ""])
        mappings = (
            (("历史", "古建", "文化"), "历史古迹"),
            (("文艺", "展览", "博物馆", "美术馆"), "博物馆展览"),
            (("自然", "风光", "亲子"), "公园自然风光"),
            (("拍照", "出片", "夜景"), "摄影夜景"),
            (("citywalk", "散步", "街区"), "历史街区"),
            (("小众", "冷门", "人少", "安静", "清静"), "小众景点"),
        )
        return [f"{city}{keyword}" for matches, keyword in mappings if any(item in text for item in matches)]

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
        matched = [
            place
            for place in stations
            if clean_query and (
                clean_query in re.sub(r"\s+", "", place.name)
                or re.sub(r"\s+", "", place.name) in clean_query
            )
        ]
        if not matched:
            return None
        return max(
            matched,
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
            return None
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

    def _popular_place_score(self, place: PlaceSummary) -> float:
        """Popularity is an explainable blend, never a synonym for AMap rating alone."""
        try:
            rating = min(5.0, max(0.0, float(place.rating or 0.0)))
        except ValueError:
            rating = 0.0
        rating_signal = min(1.0, max(0.0, (rating - 3.8) / 1.2))
        landmark_hint = any(
            word in f"{place.name} {place.typeName or ''}"
            for word in ("博物馆", "风景名胜", "世界遗产", "古城", "名胜", "故宫", "国家")
        )
        return (
            rating_signal
            + (0.35 if place.officialScenicGrade else 0.0)
            + (0.18 if landmark_hint else 0.0)
            + (0.10 if place.coverImageUrl else 0.0)
            + min(0.25, math.log1p(place.experienceEvidenceCount) / 14.0)
            + self._first_visit_landmark_score(place) * 0.70
        )

    def _first_visit_landmark_score(self, place: PlaceSummary) -> float:
        name = re.sub(r"[^\w\u4e00-\u9fff]", "", place.name).lower()
        aliases = {
            "故宫": "故宫博物院",
            "天安门": "天安门广场",
            "兵马俑": "秦始皇帝陵博物院",
            "熊猫基地": "成都大熊猫繁育研究基地",
            "西湖": "杭州西湖风景名胜区",
        }
        priorities: list[float] = []
        for seed in POPULAR_POI_SEEDS:
            seed_name = re.sub(r"[^\w\u4e00-\u9fff]", "", seed.name).lower()
            matched = name == seed_name or (
                min(len(name), len(seed_name)) >= 4 and (name in seed_name or seed_name in name)
            )
            if not matched:
                matched = any(
                    alias in name and canonical == seed.name
                    for alias, canonical in aliases.items()
                )
            if matched:
                priorities.append(seed.priority / 100.0)
        return max(priorities, default=0.0)

    def _is_first_visit_core_landmark(self, place: PlaceSummary) -> bool:
        return self._first_visit_landmark_score(place) >= 0.99

    def _prefers_low_crowd_exploration(self, request: AiPlanGenerationRequest) -> bool:
        instructions = " ".join([*request.preferences, request.freeText or ""]).lower()
        return any(
            phrase in instructions
            for phrase in (
                "小众", "冷门", "人少", "清静", "安静",
                "避开人群", "避开游客", "避开热门", "不要热门", "不去热门",
                "不想去人太多", "不想人挤人", "不排队",
            )
        )

    def _prefers_classic_landmarks(self, request: AiPlanGenerationRequest) -> bool:
        instructions = " ".join([*request.preferences, request.freeText or ""]).lower()
        return any(
            phrase in instructions
            for phrase in ("经典", "必玩", "热门", "地标", "第一次去", "首次")
        )

    def _should_protect_core_landmark(
        self,
        request: AiPlanGenerationRequest,
        place: PlaceSummary,
    ) -> bool:
        if self._is_user_mandatory(request, place):
            return True
        priority = self._first_visit_landmark_score(place)
        if priority < 0.99:
            return False
        if not self._prefers_low_crowd_exploration(request):
            return True
        return self._prefers_classic_landmarks(request) and priority >= 1.0

    def _opening_time_confidence(self, place: PlaceSummary, request: AiPlanGenerationRequest) -> str:
        trip_dates = [
            self._trip_date(request, day_index)
            for day_index in range(1, request.dayCount + 1)
        ]
        if any(
            trip_date is not None and trip_date.date().isoformat() in place.officialOpeningHoursByDate
            for trip_date in trip_dates
        ):
            return "OFFICIAL_DATE"
        if place.openingHoursWeek:
            return "REFERENCE"
        if place.openingHoursToday:
            return "REFERENCE"
        return "UNKNOWN"

    def _is_low_value_commercial_scenic(self, place: PlaceSummary) -> bool:
        text = f"{place.name} {place.typeName or ''}"
        return any(
            word in text
            for word in (
                "快闪店", "旗舰店", "体验店", "售楼处", "商业装置", "品牌展", "巨轮",
                "购物中心", "家居卖场", "汽车销售", "公司企业",
            )
        )
    def _candidate_score(
        self,
        request: AiPlanGenerationRequest,
        place: PlaceSummary,
        weather: AmapWeatherForecastDay | None,
        anchor: PlaceSummary | None,
    ) -> CandidateScore:
        """Score only available evidence; unavailable commercial signals stay neutral."""
        try:
            rating = min(5.0, max(0.0, float(place.rating or 0)))
        except ValueError:
            rating = 0.0
        text = f"{place.name} {place.typeName or ''}"
        preference_raw = self._preference_place_score(request, place)
        has_preferences = bool(self._clean_preferences(request.preferences) or (request.freeText or "").strip())
        recognition = min(1.0, self._popular_place_score(place) / 1.45)
        preference = min(1.0, preference_raw / 6.0) if has_preferences else 0.35 + recognition * 0.65
        review_confidence = min(
            1.0,
            (0.48 if rating > 0 else 0.20)
            + (0.16 if place.coverImageUrl else 0.0)
            + (0.12 if place.address else 0.0)
            + min(0.24, math.log1p(place.experienceEvidenceCount) / 18.0),
        )
        weather_raw = self._weather_place_score(place, weather)
        weather_fit = min(1.0, max(0.0, (weather_raw + 7.0) / 15.0)) if weather is not None else 0.5
        explicitly_requested = self._is_user_mandatory(request, place)
        core_landmark = self._should_protect_core_landmark(request, place)
        anchor_distance = self._distance(anchor, place) if anchor is not None else 0.0
        route_convenience = proximity_score(anchor_distance) if anchor is not None else 0.5
        has_hours = bool(place.openingHoursToday or place.openingHoursWeek)
        freshness = 0.85 if place.contentUpdatedAt else 0.75 if has_hours else 0.40
        uncertainty_penalty = 0.0 if has_hours else 0.04
        if place.officialClosureWarning:
            uncertainty_penalty += 0.06
        if place.officialReservationRequired:
            uncertainty_penalty += 0.02
        if place.officialAccessNote:
            uncertainty_penalty += 0.04
        commute_penalty = min(0.12, anchor_distance / 80.0) if anchor is not None else 0.0
        return CandidateScore(
            preference=preference,
            recognition=recognition,
            review_confidence=review_confidence,
            weather=weather_fit,
            season=self._season_place_score(request, place),
            mandatory_affinity=1.0 if explicitly_requested or core_landmark else 0.5,
            route_convenience=route_convenience,
            freshness=freshness,
            commute_penalty=commute_penalty,
            crowd_penalty=(
                place.crowdRisk * (0.22 if self._prefers_low_crowd_exploration(request) else 0.10)
                + (
                    self._first_visit_landmark_score(place) * 0.32
                    if self._prefers_low_crowd_exploration(request)
                    and not self._is_user_mandatory(request, place)
                    else 0.0
                )
            ),
            uncertainty_penalty=uncertainty_penalty,
        )

    def _attach_planning_signals(
        self,
        request: AiPlanGenerationRequest,
        candidates: list[PlaceSummary],
    ) -> list[PlaceSummary]:
        if self._place_detail_service is None or not hasattr(
            self._place_detail_service, "get_planning_signals",
        ):
            return candidates
        trip_dates = [
            trip_date
            for day_index in range(1, request.dayCount + 1)
            if (trip_date := self._trip_date(request, day_index)) is not None
        ]
        if not trip_dates:
            return candidates
        enriched: list[PlaceSummary] = []
        for place in candidates:
            try:
                signals = self._place_detail_service.get_planning_signals(place, trip_dates)
                enriched.append(place.model_copy(update=signals))
            except Exception:
                enriched.append(place)
        return enriched

    def _attach_visit_unit_signals(self, candidates: list[PlaceSummary]) -> list[PlaceSummary]:
        scenic = [place for place in candidates if place.category == "scenic"]
        normalized_scenic, _ = resolve_visit_units(scenic, distance=self._distance)
        by_id = {place.sourcePoiId: place for place in normalized_scenic}
        return [
            by_id.get(place.sourcePoiId, place)
            for place in candidates
            if place.category != "scenic" or place.sourcePoiId in by_id
        ]

    async def _optimize_with_heartbeat(
        self,
        request: AiPlanGenerationRequest,
        city_name: str,
        candidates: list[PlaceSummary],
        fallback: list[AiGeneratedDay],
        progress: ProgressCallback | None,
        task: asyncio.Task[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        task = task or asyncio.create_task(self._generate_with_ai(request, city_name, candidates, fallback, progress))
        loop = asyncio.get_running_loop()
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=5.0)
                if task in done:
                    return task.result()
                self._notify(
                    progress,
                    74,
                    "正在进行智能规划，AI 审稿与局部调整仍在继续",
                    len(fallback),
                    partial_days=fallback,
                    active_day_index=fallback[-1].dayIndex if fallback else None,
                )
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
        assessment = await self._review_draft_with_ai(request, city_name, fallback, progress)
        ordered_candidates = sorted(
            candidates,
            key=lambda place: (
                0 if place.category in {"transport", "lodging"} else 1,
                -self._quality_score(place),
            ),
        )
        fallback_ids = {
            place.sourcePoiId
            for day in fallback
            for place in day.places
        }
        fallback_candidates = [place for place in ordered_candidates if place.sourcePoiId in fallback_ids]
        draft_summaries = [
            self._generated_to_summary(place)
            for day in fallback
            for place in day.places
            if place.category not in {"transport", "lodging"}
        ]
        draft_districts = {place.districtName for place in draft_summaries if place.districtName}
        alternatives = [
            place
            for place in ordered_candidates
            if place.sourcePoiId not in fallback_ids
            and (
                place.districtName in draft_districts
                or not draft_summaries
                or min(self._distance(place, draft) for draft in draft_summaries) <= 6.0
                or self._is_user_mandatory(request, place)
            )
        ]
        candidate_limit = min(len(ordered_candidates), max(10, request.dayCount * 4))
        prompt_candidates = (fallback_candidates + alternatives)[:candidate_limit]
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
                "openingTimeConfidence": self._opening_time_confidence(place, request),
                "officialScenicGrade": place.officialScenicGrade,
                "officialReservationRequired": place.officialReservationRequired,
                "officialClosedDates": place.officialClosedDates,
                "officialAccessNote": place.officialAccessNote,
                "officialMaxDailyCapacity": place.officialMaxDailyCapacity,
                "officialTicketNote": place.officialTicketNote,
            }
            for place in prompt_candidates
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
            "optimizationMode": request.optimizationMode,
            "pace": request.pace,
            "transportPreference": request.transportPreference,
            "dailyTimeWindow": f"{request.dailyStart}-{request.dailyEnd}",
            "ruleDraft": [
                {
                    "dayIndex": day.dayIndex,
                    "places": [
                        {
                            "sourcePoiId": place.sourcePoiId,
                            "start": place.suggestedStart,
                            "end": place.suggestedEnd,
                            "mealType": place.mealType,
                        }
                        for place in day.places
                    ],
                }
                for day in fallback
            ],
            "assessment": assessment,
            "candidatePlaces": compact_candidates,
        }
        max_changes = 5 if request.optimizationMode == "REQUIRED" else 3
        messages = [
            {
                "role": "system",
                "content": (
                    "你是面向中国境内旅行的结构化行程优化器。只能使用 candidatePlaces 中真实存在的 sourcePoiId，"
                    "不得虚构地点、开放时间、预约、票价、交通管制、天气或小红书评价。优化目标按优先级依次是："
                    "硬约束可执行、少折返和少绕行、符合天气、用户偏好、地点特色与行程丰富度。"
                    "车站、机场和酒店只有用户明确填写时才可加入交通/住宿锚点；若其本身以 scenic 类候选出现，"
                    "才可按景点处理。到达站必须是到达日第一锚点，离开站必须是离开日最后锚点。"
                    "hotelStays 的每段酒店分别作为对应住宿日前一日终点和次日起点，不得默认所有天同住一家。"
                    "必须考虑每两个相邻地点的实际通勤成本；交通方式可以混合使用，并优先服从 transportPreference。"
                    "景区明确限定接驳车、索道、步行或实施交通管控时必须服从；公交非运营时间无结果时，"
                    "不能当成零分钟或可步行，必须换成可执行方式或调整时间。"
                    "已确认的闭馆日和官方日期开放区间不可违反，并预留入园、安检和换乘时间。"
                    "openingTimeConfidence=REFERENCE 或 UNKNOWN 的时间可作为体验优化线索，不视为已确认事实；"
                    "可以据此提出更符合游玩习惯的时间建议，但必须在 note 明确写明出发前复核。"
                    "依据逐日天气调整室内外权重：雨雪、高温、大风或空气状况不佳时减少长时间户外和骑行，"
                    "但不得把天气预报范围外的日期当作已验证天气。"
                    "可在07:30-11:00安排特色早餐、11:30-14:00安排午餐、17:30-21:00安排特色晚餐，"
                    "并用 mealType 标记 BREAKFAST/LUNCH/DINNER。餐馆必须在前后游览点的顺路通勤链上；"
                    "不允许为了吃饭明显折返，若没有足够近且有特色的候选餐馆，宁可不推荐。"
                    "全天型景区优先园内餐饮、景区允许携带的便携餐或入口附近餐馆，并在 note 中提示核实景区规则。"
                    "小红书等公开内容若出现在输入证据中，只能作为灵感和时效性线索，必须与地点、日期和官方/高德数据交叉核验；"
                    "没有输入证据时不得生成所谓真实评价或小众消息。"
                    f"旅行节奏为 {request.pace}，每天目标地点数为 {PACE_PLACE_COUNTS[request.pace]}，"
                    f"每日活动必须处于 {request.dailyStart}-{request.dailyEnd}，交通偏好为 {request.transportPreference}。"
                    "同一地点不可重复；相邻地点很远时应减少当天地点数或重新分组，不能压缩参观和通勤时间硬塞。"
                    "ruleDraft 是规则引擎生成的基线，优先做最小必要调整，不要无理由从零重排；最终仍由服务端复核路线。"
                    "常规完整游览日可参考特色早餐→上午景点→特色午餐→下午景点→特色晚餐，"
                    "但这只是默认节奏，不是固定模板；用户偏好、freeText 补充要求、到离站时间、住宿锚点、"
                    "景区自身游览方式和当天可用时段优先。"
                    "晚餐后只有在候选地点明确适合夜游且开放时间允许时，才可再安排至多一个夜间地点。"
                    "你提出的每项调整会与 ruleDraft 比较。优先改善热门景点覆盖、用户偏好、早中晚体验、"
                    "游览主题和体力节奏；不要求每项变化都达到固定百分比收益，但不得删除用户锚点、"
                    "安排已确认闭馆地点、引用候选池外 POI 或制造真实不可达的路线。"
                    "如果 preferences 或 freeText 明确要求小众、冷门、人少或避开热门，不以热门覆盖为目标；"
                    "应优先同片区低拥挤且符合兴趣的候选，只有用户明确写必去时才保留对应热门地标。"
                    "assessment 是上一阶段对草案的短审稿；只修复其中明确问题，不要重新审稿或从零生成。"
                    "输出 NDJSON，每一物理行必须是独立 JSON，不能输出 Markdown。先输出至多1条总体事件和每日至多1条可审计的简短决策事件："
                    "{\"kind\":\"event\",\"type\":\"MODEL_REASON\",\"message\":\"不超过120字\","
                    "\"dayIndex\":1,\"evidence\":[\"输入或候选数据事实\"],\"decision\":\"采取的可见决策\"}。"
                    "事件必须引用可见输入事实，只给结论和依据摘要，不要声称或输出隐藏思维链。"
                    "最后仅输出一行局部变更提案，不得重写整份行程："
                    "{\"kind\":\"result\",\"proposal\":{\"changes\":["
                    "{\"type\":\"REPLACE_PLACE\",\"dayIndex\":2,\"oldPoiId\":\"\",\"newPoiId\":\"\",\"reason\":\"\"},"
                    "{\"type\":\"REORDER_DAY\",\"dayIndex\":1,\"orderedPoiIds\":[\"\"],\"reason\":\"\"},"
                    "{\"type\":\"UPDATE_NOTE\",\"dayIndex\":1,\"poiId\":\"\",\"note\":\"不超过35字\",\"reason\":\"\"}"
                    "],\"travelerExplanation\":\"不超过100字\"}}。changes 最多"
                    + str(max_changes)
                    + "项；没有明确改进时返回空数组。"
                    "如果约束不可同时满足，减少地点并在 summary 说明，不得伪造可执行性。"
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
            if item.get("kind") == "result" and isinstance(item.get("proposal"), dict):
                final_payload = item["proposal"]
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
                74,
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

        def on_timing(phase: str, _elapsed_ms: int) -> None:
            if phase == "connected":
                message = "已连接 AI 服务，正在等待模型生成完整方案"
                evidence = ["前后端连接和请求上传已完成"]
            elif phase == "reasoning":
                message = "AI 正在比较热门程度、偏好、开放时间线索与路线节奏"
                evidence = ["仅展示可核对的规划依据，不展示模型原始隐藏思维链"]
            elif phase == "first_token":
                message = "AI 正在提出局部调整"
                evidence = ["模型已经开始输出局部调整建议"]
            else:
                message = "AI 调整建议已完整接收"
                evidence = ["模型输出已完整接收，下一步执行硬约束复核"]
            self._notify(
                progress,
                74,
                message,
                len(fallback),
                partial_days=fallback,
                event=self._event(
                    "ANALYSIS",
                    message,
                    evidence=evidence,
                    decision="继续显示当前可执行草案，不阻塞用户浏览。",
                ),
                active_day_index=fallback[-1].dayIndex if fallback else None,
            )

        if hasattr(self._model_client, "chat_stream"):
            raw = await self._model_client.chat_stream(
                messages,
                on_delta=on_delta,
                max_tokens=min(4200, max(1400, request.dayCount * 420)),
                temperature=0.25,
                disable_read_timeout=True,
                on_timing=on_timing,
                thinking_enabled=False,
            )
            consume_line(line_buffer)
        else:
            raw = await self._model_client.chat(
                messages,
                max_tokens=min(4200, max(1400, request.dayCount * 420)),
                temperature=0.25,
                disable_read_timeout=True,
                thinking_enabled=False,
            )
        if final_payload is not None:
            return final_payload
        parsed = json.loads(self._extract_json(raw))
        if not isinstance(parsed, dict):
            raise ValueError("AI 未返回结构化补丁")
        if isinstance(parsed.get("proposal"), dict):
            parsed = parsed["proposal"]
        if not isinstance(parsed.get("changes"), list):
            if isinstance(parsed.get("days"), list):
                return parsed
            raise ValueError("AI 只能返回 proposal.changes 或 days 结构化建议")
        return parsed

    async def _review_draft_with_ai(
        self,
        request: AiPlanGenerationRequest,
        city_name: str,
        fallback: list[AiGeneratedDay],
        progress: ProgressCallback | None,
    ) -> dict[str, Any]:
        """Run a short cached editorial review before deep-mode patch generation."""
        if request.optimizationMode != "REQUIRED" or not hasattr(self._model_client, "chat"):
            return {"strengths": [], "problems": []}
        review_input = {
            "destination": city_name,
            "preferences": self._clean_preferences(request.preferences),
            "freeText": (request.freeText or "").strip(),
            "pace": request.pace,
            "days": [
                {
                    "dayIndex": day.dayIndex,
                    "places": [
                        {
                            "id": place.sourcePoiId,
                            "name": place.name,
                            "category": self._experience_category(self._generated_to_summary(place)),
                            "district": place.districtName,
                            "start": place.suggestedStart,
                            "end": place.suggestedEnd,
                            "mealType": place.mealType,
                        }
                        for place in day.places
                    ],
                    "commuteMinutes": sum(item.durationMinutes for item in day.transfers),
                    "longestLegMinutes": max((item.durationMinutes for item in day.transfers), default=0),
                }
                for day in fallback
            ],
        }
        serialized = json.dumps(review_input, ensure_ascii=False, sort_keys=True)
        cache_key = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        cached = self._ai_review_cache.get(cache_key)
        if cached is not None:
            return cached
        messages = [
            {
                "role": "system",
                "content": (
                    "你是旅行行程审稿人，只诊断草案是否符合真实游客需求，不生成新行程。"
                    "重点检查同类体验重复、热门与偏好平衡、早中晚节奏、餐期、超长通勤、跨区、"
                    "体力负担和夜间体验。不得推测开放时间或路线事实。"
                    "仅输出JSON：{\"strengths\":[\"...\"],\"problems\":[{\"dayIndex\":1,"
                    "\"type\":\"...\",\"message\":\"...\",\"evidence\":[\"...\"]}]}。"
                    "strengths最多3项，problems最多5项，每条不超过60字。"
                ),
            },
            {"role": "user", "content": serialized},
        ]
        self._notify(
            progress,
            74,
            "AI 正在深度审阅行程体验与节奏",
            len(fallback),
            partial_days=fallback,
            event=self._event(
                "ANALYSIS",
                "AI 正在审阅热门与偏好平衡、同类体验、早中晚节奏和体力负担。",
                evidence=["思考模式只用于形成审稿结论，原始隐藏推理不会作为行程事实"],
                decision="审稿完成后只允许提出有限的局部调整。",
            ),
            active_day_index=fallback[-1].dayIndex if fallback else None,
        )
        try:
            try:
                raw = await self._model_client.chat(
                    messages,
                    max_tokens=getattr(self._model_client, "reasoning_max_output_tokens", 16000),
                    disable_read_timeout=True,
                    thinking_enabled=True,
                    reasoning_effort=getattr(self._model_client, "reasoning_effort", "high"),
                    json_mode=True,
                )
                parsed = json.loads(self._extract_json(raw))
            except (HTTPException, ValueError, TypeError, json.JSONDecodeError):
                self._notify(
                    progress,
                    74,
                    "AI 深度审稿未形成最终 JSON，正在生成紧凑审稿结论",
                    len(fallback),
                    partial_days=fallback,
                    active_day_index=fallback[-1].dayIndex if fallback else None,
                )
                raw = await self._model_client.chat(
                    messages,
                    max_tokens=1800,
                    temperature=0.15,
                    disable_read_timeout=True,
                    model=getattr(self._model_client, "fallback_model_name", None),
                    thinking_enabled=False,
                    json_mode=True,
                )
                parsed = json.loads(self._extract_json(raw))
            strengths = parsed.get("strengths") if isinstance(parsed, dict) else []
            problems = parsed.get("problems") if isinstance(parsed, dict) else []
            cleaned_problems = []
            for item in problems:
                if not isinstance(item, dict):
                    continue
                raw_day = self._safe_int(item.get("dayIndex"))
                cleaned_problems.append(
                    {
                        "dayIndex": raw_day if raw_day and 1 <= raw_day <= request.dayCount else None,
                        "type": self._clean_text(item.get("type"), "EXPERIENCE", 32),
                        "message": self._clean_text(item.get("message"), "行程体验可进一步优化。", 100),
                        "evidence": [str(value)[:100] for value in item.get("evidence", [])][:4]
                        if isinstance(item.get("evidence"), list)
                        else [],
                    },
                )
            result = {
                "strengths": [str(item)[:80] for item in strengths if str(item).strip()][:3],
                "problems": cleaned_problems[:5],
            }
        except (HTTPException, ValueError, TypeError, json.JSONDecodeError):
            result = {"strengths": [], "problems": []}
        if len(self._ai_review_cache) >= 128:
            self._ai_review_cache.pop(next(iter(self._ai_review_cache)))
        self._ai_review_cache[cache_key] = result
        if result["problems"]:
            first = result["problems"][0]
            self._notify(
                progress,
                74,
                f"AI 审稿发现 {len(result['problems'])} 个可优化问题",
                len(fallback),
                partial_days=fallback,
                event=self._event(
                    "MODEL_REASON",
                    self._clean_text(first.get("message"), "AI 已完成行程审稿。", 120),
                    day_index=self._safe_int(first.get("dayIndex")),
                    evidence=[str(value)[:120] for value in first.get("evidence", [])][:5]
                    if isinstance(first.get("evidence"), list)
                    else [],
                    decision="第二阶段只针对已识别问题提出有限局部修改。",
                ),
            )
        return result

    def _dedupe_preference_score(self, place: PlaceSummary) -> float:
        normalized_name = self._normalized_place_name(place.name)
        exact_seed = any(
            normalized_name == self._normalized_place_name(seed.name)
            for seed in POPULAR_POI_SEEDS
        )
        return (
            self._quality_score(place)
            + self._first_visit_landmark_score(place) * 4.0
            + (3.0 if exact_seed else 0.0)
            + (1.0 if place.openingHoursWeek or place.openingHoursToday else 0.0)
            + min(1.0, len(place.imageUrls) * 0.2)
        )

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
            if not raw_day:
                continue
            raw_places = raw_day.get("places") if isinstance(raw_day, dict) else []
            raw_places = raw_places if isinstance(raw_places, list) else []
            generated_places: list[AiGeneratedPlace] = []
            for position, raw_place in enumerate(raw_places[:8]):
                if not isinstance(raw_place, dict):
                    continue
                source_id = str(raw_place.get("sourcePoiId") or "").strip()
                place = by_id.get(source_id)
                if place is None or source_id in used or place.category in {"transport", "lodging"}:
                    continue
                used.add(source_id)
                generated_places.append(self._to_generated_place(place, position, raw_place, request))

            fallback_day = fallback_by_day[day_index]
            movable_target = sum(place.category not in {"transport", "lodging"} for place in fallback_day.places)
            generated_places = generated_places[:movable_target]
            for place in fallback_day.places:
                if len(generated_places) >= movable_target:
                    break
                if place.category in {"transport", "lodging"}:
                    continue
                if place.sourcePoiId not in {item.sourcePoiId for item in generated_places}:
                    generated_places.append(place)

            movable = iter(generated_places)
            restored: list[AiGeneratedPlace] = []
            for baseline_place in fallback_day.places:
                if baseline_place.category in {"transport", "lodging"}:
                    # Preserve every anchor occurrence, including the same
                    # hotel used once for luggage drop and again overnight.
                    restored.append(baseline_place)
                else:
                    replacement = next(movable, None)
                    if replacement is not None:
                        restored.append(replacement)
            generated_places = restored

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

    def _apply_ai_proposal(
        self,
        request: AiPlanGenerationRequest,
        payload: dict[str, Any],
        candidates: list[PlaceSummary],
        fallback: list[AiGeneratedDay],
    ) -> list[AiGeneratedDay]:
        """Apply bounded model patches without allowing anchors or facts to mutate."""
        by_id = {place.sourcePoiId: place for place in candidates}
        days = {day.dayIndex: day.model_copy(deep=True) for day in fallback}
        used_ids = {
            place.sourcePoiId
            for day in fallback
            for place in day.places
            if place.category not in {"transport", "lodging"}
        }
        changes = payload.get("changes") if isinstance(payload.get("changes"), list) else []
        max_changes = 5 if request.optimizationMode == "REQUIRED" else 3
        for change in changes[:max_changes]:
            if not isinstance(change, dict):
                continue
            day_index = self._safe_int(change.get("dayIndex"))
            day = days.get(day_index or -1)
            if day is None:
                continue
            change_type = str(change.get("type") or "").upper()
            places = list(day.places)
            replaced_ids: tuple[str, str] | None = None
            if change_type == "REPLACE_PLACE":
                old_id = str(change.get("oldPoiId") or "").strip()
                new_id = str(change.get("newPoiId") or "").strip()
                old_index = next((index for index, place in enumerate(places) if place.sourcePoiId == old_id), None)
                replacement = by_id.get(new_id)
                if old_index is None or replacement is None:
                    continue
                old = places[old_index]
                if old.category in {"transport", "lodging"} or replacement.category in {"transport", "lodging"}:
                    continue
                if (
                    self._is_user_mandatory(request, self._generated_to_summary(old))
                    or self._should_protect_core_landmark(request, self._generated_to_summary(old))
                    or old.visitUnitPolicy == "BUNDLE"
                ):
                    continue
                if new_id != old_id and new_id in used_ids:
                    continue
                if old.mealType and replacement.category not in {"food", "drink"}:
                    continue
                places[old_index] = self._to_generated_place(
                    replacement,
                    old_index,
                    {
                        "start": old.suggestedStart,
                        "end": old.suggestedEnd,
                        "mealType": old.mealType,
                        "note": self._clean_text(change.get("reason"), old.note, 80),
                    },
                    request,
                )
                replaced_ids = (old_id, new_id)
            elif change_type == "REORDER_DAY":
                ordered_ids = [str(value) for value in change.get("orderedPoiIds", []) if str(value).strip()]
                movable = [place for place in places if place.category not in {"transport", "lodging"}]
                if len(ordered_ids) != len(movable) or set(ordered_ids) != {place.sourcePoiId for place in movable}:
                    continue
                movable_by_id = {place.sourcePoiId: place for place in movable}
                replacements = iter(movable_by_id[source_id] for source_id in ordered_ids)
                places = [place if place.category in {"transport", "lodging"} else next(replacements) for place in places]
            elif change_type == "UPDATE_NOTE":
                poi_id = str(change.get("poiId") or "").strip()
                place_index = next((index for index, place in enumerate(places) if place.sourcePoiId == poi_id), None)
                if place_index is None:
                    continue
                note = self._clean_text(change.get("note"), places[place_index].note, 80)
                places[place_index] = places[place_index].model_copy(update={"note": note}, deep=True)
                days[day.dayIndex] = day.model_copy(update={"places": places}, deep=True)
                continue
            else:
                continue

            rescheduled = self._reschedule_generated_sequence(request, places, day.dayIndex)
            if len(rescheduled) != len(places):
                continue
            if replaced_ids is not None:
                used_ids.discard(replaced_ids[0])
                used_ids.add(replaced_ids[1])
            days[day.dayIndex] = day.model_copy(
                update={
                    "places": rescheduled,
                    "estimatedDistanceKm": self._day_distance(rescheduled),
                    "intensity": self._intensity(rescheduled),
                },
                deep=True,
            )
        return [days[index] for index in sorted(days)]

    def _select_ai_optimized_days(
        self,
        request: AiPlanGenerationRequest,
        fallback: list[AiGeneratedDay],
        candidates: list[AiGeneratedDay],
    ) -> tuple[list[AiGeneratedDay], int, list[str]]:
        """Accept useful model changes after known facts and user anchors remain valid.

        The rule-generated, AMap-routed draft is the safe baseline. AI is a
        bounded proposal layer: each day is independently accepted so one bad
        suggestion cannot invalidate otherwise useful model improvements.
        """
        candidate_by_day = {day.dayIndex: day for day in candidates}
        selected: list[AiGeneratedDay] = []
        notes: list[str] = []
        accepted = 0
        for baseline in fallback:
            candidate = candidate_by_day.get(baseline.dayIndex)
            if candidate is None:
                selected.append(baseline)
                notes.append(f"第{baseline.dayIndex}天缺少完整建议，保留草案")
                continue
            violations = self._ai_day_violations(request, baseline, candidate)
            if violations:
                selected.append(baseline)
                notes.append(f"第{baseline.dayIndex}天未采纳：{violations[0]}")
                continue

            baseline_ids = [place.sourcePoiId for place in baseline.places]
            candidate_ids = [place.sourcePoiId for place in candidate.places]
            if candidate_ids == baseline_ids:
                content_changed = (
                    candidate.title != baseline.title
                    or candidate.summary != baseline.summary
                    or any(
                        left.note != right.note
                        for left, right in zip(baseline.places, candidate.places)
                    )
                )
                if content_changed:
                    selected.append(candidate)
                    accepted += 1
                    notes.append(f"第{baseline.dayIndex}天采纳：顺序不变、路线不变，仅更新有依据的游玩说明")
                else:
                    selected.append(baseline)
                    notes.append(f"第{baseline.dayIndex}天未采纳：AI 未提出有效调整")
                continue

            baseline_commute = sum(item.durationMinutes for item in baseline.transfers)
            candidate_commute = sum(item.durationMinutes for item in candidate.transfers)
            baseline_quality = self._generated_day_quality(baseline)
            candidate_quality = self._generated_day_quality(candidate)
            commute_gain = baseline_commute - candidate_commute
            distance_gain = baseline.estimatedDistanceKm - candidate.estimatedDistanceKm
            quality_gain = candidate_quality - baseline_quality
            baseline_objective = self._generated_day_objective(request, baseline)
            candidate_objective = self._generated_day_objective(request, candidate)
            objective_gain = (candidate_objective - baseline_objective) / max(abs(baseline_objective), 1.0)
            experience_gain = self._generated_day_experience_score(request, candidate) - self._generated_day_experience_score(request, baseline)
            clearly_worse = (
                candidate_commute > max(baseline_commute + 45, round(baseline_commute * 1.50))
                and experience_gain <= 0
                and quality_gain <= 0
            )
            if not clearly_worse and (
                objective_gain >= -0.05
                or experience_gain > 0
                or quality_gain > 0
                or commute_gain > 0
                or distance_gain > 0
            ):
                selected.append(candidate)
                accepted += 1
                if experience_gain > 0:
                    benefit = "热门程度或用户偏好更匹配"
                elif commute_gain > 0:
                    benefit = f"通勤减少约 {commute_gain} 分钟"
                elif distance_gain > 0:
                    benefit = f"路线缩短约 {distance_gain:.1f} 公里"
                else:
                    benefit = "早中晚体验与游览说明更连贯"
                notes.append(f"第{baseline.dayIndex}天采纳：{benefit}，未使用固定百分比门槛")
            else:
                selected.append(baseline)
                notes.append(
                    f"第{baseline.dayIndex}天未采纳：通勤明显增加且没有带来偏好或地点质量收益",
                )
        fallback_bundle_days = {
            place.visitUnitId: day.dayIndex
            for day in fallback
            for place in day.places
            if place.visitUnitPolicy == "BUNDLE" and place.visitUnitId
        }
        fallback_bundle_members = {
            unit_id: {
                place.sourcePoiId
                for day in fallback
                for place in day.places
                if place.visitUnitId == unit_id
            }
            for unit_id in fallback_bundle_days
        }
        invalid_bundle_days: set[int] = set()
        for unit_id, expected_day in fallback_bundle_days.items():
            occurrences = {
                day.dayIndex: {
                    place.sourcePoiId
                    for place in day.places
                    if place.visitUnitId == unit_id
                }
                for day in selected
                if any(place.visitUnitId == unit_id for place in day.places)
            }
            if occurrences != {expected_day: fallback_bundle_members[unit_id]}:
                invalid_bundle_days.update(occurrences)
                invalid_bundle_days.add(expected_day)
        if invalid_bundle_days:
            fallback_by_day = {day.dayIndex: day for day in fallback}
            for index, day in enumerate(selected):
                if day.dayIndex not in invalid_bundle_days:
                    continue
                if day != fallback_by_day[day.dayIndex]:
                    accepted = max(0, accepted - 1)
                selected[index] = fallback_by_day[day.dayIndex]
                notes[day.dayIndex - 1] = f"第{day.dayIndex}天未采纳：建议会拆分或重复同一景区游览单元"
        return selected, accepted, notes

    def _ai_day_violations(
        self,
        request: AiPlanGenerationRequest,
        baseline: AiGeneratedDay,
        candidate: AiGeneratedDay,
    ) -> list[str]:
        violations: list[str] = []
        day_start, day_end = self._effective_day_bounds(request, candidate.dayIndex)
        previous_end = day_start
        for place in candidate.places:
            start = self._time_to_minutes(place.suggestedStart)
            end = self._time_to_minutes(place.suggestedEnd)
            if start < day_start or end > day_end or end <= start:
                violations.append(f"{place.name} 超出每日可用时间")
                continue
            if start < previous_end:
                violations.append(f"{place.name} 与前一地点时间重叠")
            previous_end = max(previous_end, end)
            meal_window = {
                "BREAKFAST": (7 * 60 + 30, 11 * 60),
                "LUNCH": (11 * 60 + 30, 14 * 60),
                "DINNER": (17 * 60 + 30, 21 * 60),
            }.get(place.mealType)
            if meal_window is not None and not (meal_window[0] <= start < end <= meal_window[1]):
                violations.append(f"{place.name} 不在对应餐期内")
            if place.category == "scenic":
                summary = self._generated_to_summary(place)
                if not self._is_open_on_trip_day(summary, request, candidate.dayIndex):
                    violations.append(f"{place.name} 当日闭馆")
                windows = self._opening_windows_for_day(summary, request, candidate.dayIndex)
                if windows and not self._slot_within_open_window(windows, start, end):
                    violations.append(f"{place.name} 超出开放或停止入场时间")
                reserved_window = self._user_visit_window(
                    request,
                    summary,
                    candidate.dayIndex,
                    end - start,
                )
                if reserved_window is not None and not (
                    reserved_window.start <= start < end <= reserved_window.end
                ):
                    violations.append(f"{place.name} 未满足用户预约时段")

        baseline_anchor_ids = [
            place.sourcePoiId for place in baseline.places if place.category in {"transport", "lodging"}
        ]
        candidate_ids = [place.sourcePoiId for place in candidate.places]
        if any(anchor_id not in candidate_ids for anchor_id in baseline_anchor_ids):
            violations.append("缺少用户设置的车站、机场或住宿锚点")
        mandatory_ids = {
            place.sourcePoiId
            for place in baseline.places
            if (
                self._is_user_mandatory(request, self._generated_to_summary(place))
                or self._should_protect_core_landmark(request, self._generated_to_summary(place))
            )
        }
        if not mandatory_ids.issubset(set(candidate_ids)):
            violations.append("缺少用户必去地点或城市核心热门地标")
        baseline_bundle_ids = {
            place.sourcePoiId
            for place in baseline.places
            if place.visitUnitPolicy == "BUNDLE"
        }
        if not baseline_bundle_ids.issubset(set(candidate_ids)):
            violations.append("拆分了应在同一次游览中完成的景区组成部分")
        if baseline.places and candidate.places:
            if baseline.places[0].category in {"transport", "lodging"} and (
                candidate.places[0].sourcePoiId != baseline.places[0].sourcePoiId
            ):
                violations.append("行程起点锚点位置错误")
            if baseline.places[-1].category in {"transport", "lodging"} and (
                candidate.places[-1].sourcePoiId != baseline.places[-1].sourcePoiId
            ):
                violations.append("行程终点锚点位置错误")

        baseline_unverified = sum(not transfer.verified for transfer in baseline.transfers)
        candidate_unverified = sum(not transfer.verified for transfer in candidate.transfers)
        if candidate_unverified > baseline_unverified:
            violations.append("新增了无法由高德确认的交通路段")
        expected_transfer_count = max(0, len(candidate.places) - 1)
        if len(candidate.transfers) != expected_transfer_count:
            violations.append("相邻地点缺少完整交通校验")
        if (
            self._underfilled_day_reason(request, baseline) is None
            and self._underfilled_day_reason(request, candidate) is not None
        ):
            violations.append("AI 调整会让完整日低于所选旅行节奏的合理负载")
        return violations

    def _generated_day_quality(self, day: AiGeneratedDay) -> float:
        ratings: list[float] = []
        for place in day.places:
            try:
                ratings.append(float(place.rating or 0))
            except ValueError:
                continue
        return sum(ratings) / len(ratings) if ratings else 0.0

    def _generated_day_objective(self, request: AiPlanGenerationRequest, day: AiGeneratedDay) -> float:
        place_value = 0.0
        for place in day.places:
            if place.category in {"transport", "lodging"}:
                continue
            summary = self._generated_to_summary(place)
            place_value += self._quality_score(summary) * 0.18
            place_value += self._preference_place_score(request, summary) * 0.35
            if place.category == "scenic":
                place_value += 0.8
                if self._should_protect_core_landmark(request, summary):
                    place_value += self._first_visit_landmark_score(summary) * 3.0
                elif self._prefers_low_crowd_exploration(request):
                    place_value -= self._first_visit_landmark_score(summary) * 1.5
            if place.mealType:
                place_value += 0.35
            if not place.scheduleVerified and place.category == "scenic":
                place_value -= 0.25
        commute_minutes = sum(transfer.durationMinutes for transfer in day.transfers)
        unverified_routes = sum(not transfer.verified for transfer in day.transfers)
        return place_value - commute_minutes * 0.025 - day.estimatedDistanceKm * 0.04 - unverified_routes * 0.4

    def _generated_day_experience_score(self, request: AiPlanGenerationRequest, day: AiGeneratedDay) -> float:
        score = 0.0
        for place in day.places:
            if place.category in {"transport", "lodging"}:
                continue
            summary = self._generated_to_summary(place)
            score += self._preference_place_score(request, summary)
            score += self._popular_place_score(summary) * 0.7
            if self._should_protect_core_landmark(request, summary):
                score += self._first_visit_landmark_score(summary) * 2.0
            elif self._prefers_low_crowd_exploration(request):
                score -= self._first_visit_landmark_score(summary) * 1.5
            if place.mealType:
                score += 0.4
        return score

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
                officialScenicGrade=place.officialScenicGrade,
                experienceEvidenceCount=place.experienceEvidenceCount,
                officialReservationRequired=place.officialReservationRequired,
                officialReservationNote=place.officialReservationNote,
                officialClosedDates=place.officialClosedDates,
                officialClosureWarning=place.officialClosureWarning,
                officialOpeningHoursByDate=place.officialOpeningHoursByDate,
                officialAccessNote=place.officialAccessNote,
                officialMaxDailyCapacity=place.officialMaxDailyCapacity,
                officialCapacityNote=place.officialCapacityNote,
                officialTicketNote=place.officialTicketNote,
                crowdRisk=place.crowdRisk,
                contentUpdatedAt=place.contentUpdatedAt,
                visitUnitId=place.visitUnitId,
                visitUnitName=place.visitUnitName,
                visitUnitPolicy=place.visitUnitPolicy,
                visitUnitMemberOrder=place.visitUnitMemberOrder,
                visitUnitTransferMinutes=place.visitUnitTransferMinutes,
                visitUnitSourceUrl=place.visitUnitSourceUrl,
                recommendedVisitMinutes=place.recommendedVisitMinutes,
            )
            for place in places
        ]
        return self._schedule_places(
            request,
            summaries,
            day_index,
            meal_roles={place.sourcePoiId: place.mealType for place in places if place.mealType},
        )

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
        scenic = [
            place
            for place in candidates
            if place.category == "scenic"
            and not self._is_explicitly_excluded(request, place)
            and (
                self._is_user_mandatory(request, place)
                or not self._is_low_value_commercial_scenic(place)
            )
        ]
        scenic, visit_units = resolve_visit_units(scenic, distance=self._distance)
        food = sorted(
            (
                place
                for place in candidates
                if place.category in {"food", "drink"} and not self._is_explicitly_excluded(request, place)
            ),
            key=lambda place: self._quality_score(place) + self._local_food_score(city_name or request.destination, place),
            reverse=True,
        )
        used: set[str] = set()
        days: list[AiGeneratedDay] = []
        scenic_target = self._scenic_target_for_request(request)
        hotel_by_name = hotel_by_name or {}
        weather_forecast = weather_forecast or []
        hotel_stays = self._normalized_hotel_stays(request)
        departure_day = request.departureDay or request.dayCount
        scenic_capacity = max(4, scenic_target * 2)
        base_anchor = arrival_anchor or next((place for place in hotel_by_name.values() if place), None)
        visit_regions = partition_by_geography(
            visit_units,
            request.dayCount,
            score=lambda unit: sum(
                self._candidate_score(request, place, None, base_anchor).total
                + (100.0 if self._is_user_mandatory(request, place) else 0.0)
                for place in unit.places
            ),
            distance=self._distance,
            capacity=scenic_capacity,
            weight=lambda unit: unit.weight,
        )
        visit_regions = improve_day_partition(
            visit_regions,
            day_score=lambda unit, day_index: sum(
                (
                    self._candidate_score(
                        request,
                        place,
                        weather_forecast[day_index - 1] if day_index <= len(weather_forecast) else None,
                        base_anchor,
                    ).total
                    + (120.0 if self._requested_day_for_place(request, place) == day_index else 0.0)
                    - (
                        120.0
                        if self._requested_day_for_place(request, place) not in {None, day_index}
                        else 0.0
                    )
                )
                for place in unit.places
            ),
            distance=self._distance,
            capacity=scenic_capacity,
            weight=lambda unit: unit.weight,
        )
        assigned_day_by_place_id = {
            place.sourcePoiId: day_index
            for day_index, region in enumerate(visit_regions, start=1)
            for unit in region
            for place in unit.places
        }

        for day_index in range(1, request.dayCount + 1):
            weather = weather_forecast[day_index - 1] if day_index <= len(weather_forecast) else None
            unit_region = visit_regions[day_index - 1] if day_index <= len(visit_regions) else []
            region = [place for unit in unit_region for place in unit.places]
            ranked_region = sorted(
                (place for place in region if place.sourcePoiId not in used),
                key=lambda place: self._candidate_score(request, place, weather, base_anchor).total,
                reverse=True,
            )
            region_ids = {place.sourcePoiId for place in ranked_region}
            supplemental = sorted(
                (
                    place
                    for place in scenic
                    if place.sourcePoiId not in used and place.sourcePoiId not in region_ids
                    and self._assigned_candidate_available_on_day(
                        request,
                        place,
                        day_index,
                        assigned_day_by_place_id,
                    )
                ),
                key=lambda place: self._candidate_score(request, place, weather, base_anchor).total,
                reverse=True,
            )
            core_landmarks = sorted(
                (
                    place
                    for place in scenic
                    if place.sourcePoiId not in used
                    and self._assigned_candidate_available_on_day(
                        request,
                        place,
                        day_index,
                        assigned_day_by_place_id,
                    )
                    and self._should_protect_core_landmark(request, place)
                ),
                key=self._first_visit_landmark_score,
                reverse=True,
            )
            ranked_scenic = self._dedupe_candidates(
                [*core_landmarks, *ranked_region, *supplemental[: max(6, scenic_capacity)]],
            )
            instructions = " ".join([*request.preferences, request.freeText or ""])
            night_requested = any(
                keyword in instructions
                for keyword in ("夜景", "夜游", "晚上", "夜间", "灯光秀", "夜市")
            )
            _, effective_end = self._effective_day_bounds(request, day_index)
            if night_requested and effective_end >= 20 * 60:
                night_recall = sorted(
                    (
                        place
                        for place in scenic
                        if place.sourcePoiId not in used
                        and self._assigned_candidate_available_on_day(
                            request,
                            place,
                            day_index,
                            assigned_day_by_place_id,
                        )
                        and self._is_night_experience_candidate(place, request, day_index)
                    ),
                    key=lambda place: (
                        self._night_experience_score(place),
                        self._candidate_score(request, place, weather, base_anchor).total,
                    ),
                    reverse=True,
                )
                ranked_ids = {place.sourcePoiId for place in ranked_scenic}
                ranked_scenic.extend(
                    place
                    for place in night_recall[:8]
                    if place.sourcePoiId not in ranked_ids
                )
            seed = ranked_scenic[0] if ranked_scenic else None
            full_day = self._is_full_day_scenic(seed) if seed is not None else False
            bundled_extra_members = sum(
                max(0, len(unit.places) - 1)
                for unit in unit_region
                if unit.policy == "BUNDLE"
            )
            # A bundle's child areas consume real time but represent one main
            # visit unit. Do not let those child POIs crowd out the rest of the
            # day's pace budget merely because the official complex has more
            # than one executable entrance/area.
            target = 1 if full_day else scenic_target + bundled_extra_members
            required_visit_unit_ids = {
                unit.unit_id
                for unit in unit_region
                if unit.policy == "BUNDLE"
            }
            required_member_count = sum(
                len(unit.places)
                for unit in unit_region
                if unit.policy == "BUNDLE"
            )
            target = max(target, required_member_count)

            meal_roles: dict[str, str] = {}
            meals: dict[str, PlaceSummary | None] = {"BREAKFAST": None, "LUNCH": None, "DINNER": None}
            start_hotel = self._hotel_for_day_start(day_index, hotel_stays, hotel_by_name)
            end_hotel = self._hotel_for_day_end(day_index, hotel_stays, hotel_by_name)
            day_start_anchor = (
                end_hotel
                if day_index == request.arrivalDay and arrival_anchor is not None and end_hotel is not None
                else arrival_anchor
                if day_index == request.arrivalDay and arrival_anchor is not None
                else start_hotel
            )
            day_end_anchor = (
                departure_anchor
                if day_index == departure_day and departure_anchor is not None
                else end_hotel
            )
            selected = (
                self._select_time_window_scenic(
                    request,
                    ranked_scenic,
                    day_index,
                    target,
                    weather,
                    day_start_anchor,
                    day_end_anchor,
                    required_visit_unit_ids=required_visit_unit_ids,
                )
                if ranked_scenic
                else []
            )
            if not selected:
                anchor_sequence: list[PlaceSummary] = []
                if day_index == request.arrivalDay and arrival_anchor is not None:
                    anchor_sequence.append(arrival_anchor)
                    if end_hotel is not None:
                        anchor_sequence.append(end_hotel)
                elif start_hotel is not None:
                    anchor_sequence.append(start_hotel)
                if end_hotel is not None and all(place.id != end_hotel.id for place in anchor_sequence):
                    anchor_sequence.append(end_hotel)
                if day_index == departure_day and departure_anchor is not None and all(
                    place.id != departure_anchor.id for place in anchor_sequence
                ):
                    anchor_sequence.append(departure_anchor)
                generated_anchors = self._schedule_places(request, anchor_sequence, day_index)
                days.append(
                    AiGeneratedDay(
                        dayIndex=day_index,
                        title=f"DAY {day_index} · {request.destination}",
                        summary="当天没有满足开放时间、天气和通勤约束的景点；仅保留用户明确设置的交通或住宿安排。",
                        places=generated_anchors,
                        weather=weather.text if weather is not None else None,
                        estimatedDistanceKm=self._day_distance(generated_anchors),
                        intensity="轻松",
                    ),
                )
                continue
            used.update(place.sourcePoiId for place in selected)
            effective_start, _ = self._effective_day_bounds(request, day_index)
            night_candidates = [
                place
                for place in selected
                if self._is_night_experience_candidate(place, request, day_index)
            ]
            night_scenic = (
                max(
                    night_candidates,
                    key=lambda place: (self._night_experience_score(place), self._quality_score(place)),
                )
                if len(selected) > 1 and night_candidates
                else None
            )
            daytime_scenic = [
                place
                for place in selected
                if night_scenic is None or place.sourcePoiId != night_scenic.sourcePoiId
            ]
            meal_scenic = daytime_scenic or selected
            requested_roles = self._requested_meal_roles(request, day_index, full_day)
            dinner_after_night = False
            for role in requested_roles:
                if role == "BREAKFAST":
                    previous, following = day_start_anchor or meal_scenic[0], meal_scenic[0]
                elif role == "LUNCH":
                    if effective_start >= 11 * 60:
                        previous, following = day_start_anchor or meal_scenic[0], meal_scenic[0]
                    else:
                        previous = meal_scenic[0]
                        following = (
                            meal_scenic[1]
                            if len(meal_scenic) > 1
                            else night_scenic or day_end_anchor or meal_scenic[0]
                        )
                else:
                    previous = meal_scenic[-1]
                    following = night_scenic or day_end_anchor or previous
                meal = self._pick_meal(
                    food,
                    used,
                    previous,
                    following,
                    role,
                    city_name or request.destination,
                    request.transportPreference,
                )
                if role == "DINNER" and night_scenic is not None:
                    after_following = day_end_anchor or night_scenic
                    after_meal = self._pick_meal(
                        food,
                        used,
                        night_scenic,
                        after_following,
                        role,
                        city_name or request.destination,
                        request.transportPreference,
                    )
                    _, effective_end = self._effective_day_bounds(request, day_index)
                    night_duration = min(90, self._visit_duration_minutes("scenic", request.pace))
                    after_is_time_feasible = effective_end >= 20 * 60 + 15 and (
                        17 * 60 + 30 + night_duration + self._visit_duration_minutes("food", request.pace)
                        <= effective_end
                    )
                    instructions = " ".join([*request.preferences, request.freeText or ""])
                    explicitly_after = any(
                        phrase in instructions
                        for phrase in ("夜游后吃", "夜景后吃", "先夜游后晚餐", "看完夜景吃饭")
                    )
                    before_cost = self._meal_path_cost(previous, meal, night_scenic)
                    after_cost = self._meal_path_cost(night_scenic, after_meal, after_following)
                    if after_meal is not None and after_is_time_feasible and (
                        explicitly_after or meal is None or after_cost + 0.3 < before_cost
                    ):
                        meal = after_meal
                        dinner_after_night = True
                if meal is not None:
                    meals[role] = meal
                    meal_roles[meal.sourcePoiId] = role
                    used.add(meal.sourcePoiId)

            sequence: list[PlaceSummary] = []
            lunch_before_scenic = "LUNCH" in requested_roles and effective_start >= 11 * 60
            if day_index == request.arrivalDay and arrival_anchor is not None:
                sequence.append(arrival_anchor)
                if end_hotel is not None:
                    sequence.append(end_hotel)
            elif start_hotel is not None:
                sequence.append(start_hotel)
            if meals["BREAKFAST"] is not None:
                sequence.append(meals["BREAKFAST"])
            if lunch_before_scenic and meals["LUNCH"] is not None:
                sequence.append(meals["LUNCH"])
            if daytime_scenic:
                sequence.append(daytime_scenic[0])
                if not lunch_before_scenic and meals["LUNCH"] is not None:
                    sequence.append(meals["LUNCH"])
                sequence.extend(daytime_scenic[1:])
            if meals["DINNER"] is not None and not dinner_after_night:
                sequence.append(meals["DINNER"])
            if night_scenic is not None:
                sequence.append(night_scenic)
            if meals["DINNER"] is not None and dinner_after_night:
                sequence.append(meals["DINNER"])
            if end_hotel is not None and (not sequence or sequence[-1].id != end_hotel.id):
                sequence.append(end_hotel)
            if day_index == departure_day and departure_anchor is not None:
                sequence.append(departure_anchor)
            generated_places = self._schedule_places(
                request,
                sequence,
                day_index,
                meal_roles=meal_roles,
                night_place_ids={night_scenic.sourcePoiId} if night_scenic is not None else set(),
                weather=weather,
            )
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
                    intensity=self._intensity(generated_places),
                ),
            )
        return days

    def _assigned_candidate_available_on_day(
        self,
        request: AiPlanGenerationRequest,
        place: PlaceSummary,
        day_index: int,
        assigned_day_by_place_id: dict[str, int],
    ) -> bool:
        requested_day = self._requested_day_for_place(request, place)
        if requested_day is not None:
            return requested_day == day_index
        assigned_day = assigned_day_by_place_id.get(place.sourcePoiId)
        if assigned_day is None:
            return True
        if place.visitUnitPolicy == "BUNDLE":
            return assigned_day == day_index
        # A day may reuse an unselected candidate from an earlier region, but
        # must not consume a future day's geographic seed or compact cluster.
        return assigned_day <= day_index

    def _select_time_window_scenic(
        self,
        request: AiPlanGenerationRequest,
        candidates: list[PlaceSummary],
        day_index: int,
        target: int,
        weather: AmapWeatherForecastDay | None,
        start_anchor: PlaceSummary | None,
        end_anchor: PlaceSummary | None,
        required_visit_unit_ids: set[str] | None = None,
    ) -> list[PlaceSummary]:
        """Solve a compact day before any restaurant is inserted.

        Candidate ordering is decided against visit duration, per-day opening
        intervals, daily anchors and conservative travel edges. AMap replaces
        those estimated edges immediately afterwards; the same windows are
        then replayed with the actual route duration.
        """
        if not candidates or target <= 0:
            return []
        required_visit_unit_ids = required_visit_unit_ids or set()
        expected_bundle_members = {
            unit_id: {
                place.sourcePoiId
                for place in candidates
                if place.visitUnitId == unit_id and place.visitUnitPolicy == "BUNDLE"
            }
            for unit_id in required_visit_unit_ids
        }
        start_minute, end_minute = self._effective_day_bounds(request, day_index)
        available: list[PlaceSummary] = []
        solver_candidates: list[VisitCandidate] = []
        for place in candidates:
            requested_day = self._requested_day_for_place(request, place)
            if requested_day is not None and requested_day != day_index:
                continue
            if not self._is_open_on_trip_day(place, request, day_index):
                continue
            if self._weather_hard_blocked(place, weather):
                continue
            windows = self._opening_windows_for_day(place, request, day_index)
            if not windows:
                if self._is_evening_public_place(place) and end_minute >= 19 * 60 + 30:
                    windows = [TimeWindow(17 * 60 + 30, min(end_minute, 21 * 60 + 30), 20 * 60 + 30)]
                else:
                    windows = [TimeWindow(9 * 60 + 30, min(end_minute, 17 * 60 + 30))]
            duration = self._visit_duration_for_place(place, request.pace)
            windows = self._weather_adjusted_windows(place, windows, weather, duration)
            reserved_window = self._user_visit_window(request, place, day_index, duration)
            if reserved_window is not None:
                windows = [
                    TimeWindow(
                        start=max(window.start, reserved_window.start),
                        end=min(window.end, reserved_window.end),
                        latest_start=min(
                            window.latest_start if window.latest_start is not None else window.end,
                            reserved_window.end - duration,
                        ),
                    )
                    for window in windows
                    if min(window.end, reserved_window.end) - max(window.start, reserved_window.start) >= duration
                ]
            valid_ranges = tuple(
                TimeWindow(
                    start=max(start_minute, window.start),
                    end=min(end_minute, window.end),
                    latest_start=min(
                        window.latest_start if window.latest_start is not None else window.end,
                        end_minute - duration,
                    ),
                )
                for window in windows
                if min(end_minute, window.end) - max(start_minute, window.start) >= duration
            )
            if not valid_ranges:
                continue
            score = self._candidate_score(request, place, weather, start_anchor)
            available.append(place)
            solver_candidates.append(
                VisitCandidate(
                    place_id=place.sourcePoiId,
                    value=max(
                        0.05,
                        score.total * 3.0
                        + self._night_experience_score(place) * 0.012
                        + self._first_visit_landmark_score(place) * 0.75,
                    ),
                    duration_minutes=duration,
                    windows=valid_ranges,
                    mandatory=(
                        self._is_user_mandatory(request, place)
                        or self._should_protect_core_landmark(request, place)
                        or place.visitUnitId in required_visit_unit_ids
                    ),
                    uncertainty_penalty=0.10 if not (place.openingHoursToday or place.openingHoursWeek) else 0.0,
                    category=self._experience_category(place),
                    region=place.districtName or place.businessArea or "",
                ),
            )
        if not solver_candidates:
            return []

        eligible_ids = {candidate.place_id for candidate in solver_candidates}
        incomplete_units = {
            unit_id
            for unit_id, member_ids in expected_bundle_members.items()
            if member_ids and not member_ids.issubset(eligible_ids)
        }
        if incomplete_units:
            blocked_ids = {
                place.sourcePoiId
                for place in available
                if place.visitUnitId in incomplete_units
            }
            available = [place for place in available if place.sourcePoiId not in blocked_ids]
            solver_candidates = [
                candidate for candidate in solver_candidates if candidate.place_id not in blocked_ids
            ]
        if not solver_candidates:
            return []

        all_places = [*available]
        if start_anchor is not None:
            all_places.append(start_anchor)
        if end_anchor is not None and all(place.sourcePoiId != end_anchor.sourcePoiId for place in all_places):
            all_places.append(end_anchor)
        edges: dict[tuple[str, str], TravelEdge] = {}
        for origin in all_places:
            for destination in all_places:
                if origin.sourcePoiId == destination.sourcePoiId:
                    continue
                direct_km = self._distance(origin, destination)
                internal_minutes = self._internal_transfer_minutes(origin, destination)
                edges[(origin.sourcePoiId, destination.sourcePoiId)] = TravelEdge(
                    origin_id=origin.sourcePoiId,
                    destination_id=destination.sourcePoiId,
                    duration_minutes=(
                        internal_minutes
                        if internal_minutes is not None
                        else max(10, round(8 + direct_km * 6))
                        + self._exit_buffer_minutes(origin)
                        + self._entry_buffer_minutes(destination)
                    ),
                    distance_meters=max(1, round(direct_km * (1000 if internal_minutes is not None else 1350))),
                    mode="official_internal" if internal_minutes is not None else "estimated",
                    verified=internal_minutes is not None,
                )
        solution = solve_day_with_time_windows(
            solver_candidates,
            edges,
            self._day_solver_config(request, start_minute, end_minute, target),
            start_id=start_anchor.sourcePoiId if start_anchor is not None else None,
            end_id=end_anchor.sourcePoiId if end_anchor is not None else None,
        )
        if not solution.feasible and required_visit_unit_ids:
            blocked_ids = {
                place.sourcePoiId
                for place in available
                if place.visitUnitId in required_visit_unit_ids
            }
            fallback_candidates = [
                candidate for candidate in solver_candidates if candidate.place_id not in blocked_ids
            ]
            solution = solve_day_with_time_windows(
                fallback_candidates,
                edges,
                self._day_solver_config(request, start_minute, end_minute, target),
                start_id=start_anchor.sourcePoiId if start_anchor is not None else None,
                end_id=end_anchor.sourcePoiId if end_anchor is not None else None,
            )
        by_id = {place.sourcePoiId: place for place in available}
        selected = [by_id[place_id] for place_id in solution.ordered_place_ids if place_id in by_id]

        # A night-view candidate has a disjoint useful time window and should
        # not lose its slot merely because daytime landmarks have a slightly
        # higher generic score. Reserve one evening place when the user asks
        # for it; the real-route replay below can still reject it if travel or
        # confirmed opening hours make the visit infeasible.
        instructions = " ".join([*request.preferences, request.freeText or ""])
        night_requested = any(
            keyword in instructions
            for keyword in ("夜景", "夜游", "晚上", "夜间", "灯光秀", "夜市")
        )
        region_references = [
            place
            for place in selected
            if not self._is_night_experience_candidate(place, request, day_index)
        ]
        if not region_references:
            region_references = selected
        elif region_references:
            selected = [
                place
                for place in selected
                if self._is_user_mandatory(request, place)
                or not self._is_night_experience_candidate(place, request, day_index)
                or min(self._distance(place, reference) for reference in region_references) <= 5.5
            ]
        night_options = [
            place
            for place in available
            if self._is_night_experience_candidate(place, request, day_index)
            and (
                not region_references
                or min(self._distance(place, reference) for reference in region_references) <= 5.5
            )
        ]
        if end_minute >= 20 * 60 and night_options and (
            night_requested or max(self._night_experience_score(place) for place in night_options) >= 42.0
        ):
            best_night = max(
                night_options,
                key=lambda place: (
                    self._night_experience_score(place),
                    self._candidate_score(request, place, weather, start_anchor).total,
                ),
            )
            if best_night.sourcePoiId not in {place.sourcePoiId for place in selected}:
                if len(selected) < target:
                    selected.append(best_night)
                else:
                    replaceable_indices = [
                        index
                        for index, place in enumerate(selected)
                        if not self._is_user_mandatory(request, place)
                        and not self._is_night_experience_candidate(place, request, day_index)
                    ]
                    if replaceable_indices:
                        replace_index = min(
                            replaceable_indices,
                            key=lambda index: self._candidate_score(
                                request,
                                selected[index],
                                weather,
                                start_anchor,
                            ).total,
                        )
                        selected[replace_index] = best_night
        return selected

    def _effective_day_bounds(
        self,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> tuple[int, int]:
        start = self._time_to_minutes(request.dailyStart)
        end = self._time_to_minutes(request.dailyEnd)
        if day_index == request.arrivalDay and request.arrivalTime:
            start = max(start, self._time_to_minutes(request.arrivalTime))
        if day_index == (request.departureDay or request.dayCount) and request.departureTime:
            end = min(end, self._time_to_minutes(request.departureTime))
        return start, end

    def _requested_meal_roles(
        self,
        request: AiPlanGenerationRequest,
        day_index: int,
        full_day: bool,
    ) -> list[str]:
        start, end = self._effective_day_bounds(request, day_index)
        instructions = " ".join([*request.preferences, request.freeText or ""])
        if any(word in instructions for word in ("不安排餐饮", "不考虑吃饭", "自备餐食", "不需要餐馆")):
            return []

        skip_breakfast = any(
            word in instructions
            for word in ("不吃早餐", "不要早餐", "不安排早餐", "跳过早餐", "睡到自然醒", "晚起", "早午餐")
        )
        skip_lunch = full_day or any(
            word in instructions
            for word in ("不吃午餐", "不要午餐", "不安排午餐", "跳过午餐", "自带午餐", "便携午餐", "园内用餐")
        )
        skip_dinner = any(
            word in instructions
            for word in ("不吃晚餐", "不要晚餐", "不安排晚餐", "跳过晚餐")
        )
        roles: list[str] = []
        explicit_breakfast = any(word in instructions for word in ("早餐", "早茶", "早点"))
        if not skip_breakfast and (start <= 8 * 60 + 30 or explicit_breakfast) and end >= 8 * 60 + 15:
            roles.append("BREAKFAST")
        if not skip_lunch and start <= 13 * 60 and end >= 12 * 60 + 15:
            roles.append("LUNCH")
        if not skip_dinner and start <= 19 * 60 + 30 and end >= 18 * 60 + 15:
            roles.append("DINNER")
        return roles

    def _scenic_target_for_request(self, request: AiPlanGenerationRequest) -> int:
        target = PACE_PROFILES[request.pace].scenic_target
        instructions = " ".join([*request.preferences, request.freeText or ""])
        if any(word in instructions for word in ("少安排", "不要太累", "慢慢逛", "休闲", "带老人", "带小孩")):
            target -= 1
        if any(word in instructions for word in ("多安排", "尽可能多", "特种兵", "打卡更多")):
            target += 1
        return min(5, max(1, target))

    def _preference_place_score(
        self,
        request: AiPlanGenerationRequest,
        place: PlaceSummary,
    ) -> float:
        preferences = " ".join([*request.preferences, request.freeText or ""]).lower()
        place_text = f"{place.name} {place.typeName or ''}"
        score = 0.0
        preference_keywords = (
            (("拍照", "出片"), ("摄影", "观景", "花园", "古镇", "街区", "城墙")),
            (("自然", "风光"), ("山", "湖", "公园", "湿地", "森林", "峡谷", "海滨")),
            (("文艺", "展览"), ("博物馆", "美术馆", "艺术", "展览", "剧院")),
            (("历史", "古建"), ("古城", "故居", "寺", "庙", "宫", "遗址", "城墙", "博物馆")),
            (("citywalk", "散步", "街区"), ("街", "巷", "步行街", "街区", "历史文化")),
            (("小众", "人少"), ("社区", "巷", "旧址", "遗迹", "公园")),
        )
        for preference_words, place_words in preference_keywords:
            if any(word in preferences for word in preference_words) and any(word in place_text for word in place_words):
                score += 3.0
        if any(word in preferences for word in ("经典", "必玩", "热门", "地标", "第一次去")):
            score += min(4.0, self._popular_place_score(place) * 2.4)
        return score

    def _is_user_mandatory(self, request: AiPlanGenerationRequest, place: PlaceSummary) -> bool:
        return any(
            self._constraint_query_matches(query, place.name)
            for query in self._named_constraint_queries(request, required=True)
        )

    def _named_constraint_queries(
        self,
        request: AiPlanGenerationRequest,
        *,
        required: bool,
    ) -> list[str]:
        text = request.freeText or ""
        if not text.strip():
            return []
        suffix_terms = (
            ("必须去", "一定去", "必去", "不能错过", "已预约", "预约了", "预约")
            if required
            else ("不要去", "不去", "排除", "避开", "不安排")
        )
        prefix_pattern = (
            r"(?:必去|必须去|一定去|不能错过|已预约|预约)[：:]?(.+)"
            if required
            else r"(?:不要去|不去|排除|避开|不安排)[：:]?(.+)"
        )
        queries: list[str] = []
        for clause in re.split(r"[，,。；;\n]", text):
            clause = clause.strip()
            if not clause:
                continue
            prefix_match = re.search(prefix_pattern, clause)
            raw_values: list[str] = []
            if prefix_match is not None:
                raw_values.append(prefix_match.group(1))
            for term in suffix_terms:
                if term in clause:
                    if term == "预约" and any(
                        negative in clause for negative in ("不预约", "无需预约", "不需要预约")
                    ):
                        continue
                    raw_values.append(clause.split(term, 1)[0])
            for raw in raw_values:
                cleaned = re.sub(
                    r"^(?:第\d+天|我(?:们)?|请|想去|希望去|安排|保留|已经|还想去)+",
                    "",
                    raw.strip(),
                )
                cleaned = re.split(r"(?:预约|门票|入场)?\d{1,2}:[0-5]\d", cleaned, maxsplit=1)[0]
                for value in re.split(r"[、/]|和", cleaned):
                    normalized = value.strip(" ：:的地点景点")
                    if 2 <= len(normalized) <= 30 and normalized not in {"早餐", "午餐", "晚餐", "酒店"}:
                        queries.append(normalized)
        return list(dict.fromkeys(queries))[:8]

    @staticmethod
    def _constraint_query_matches(query: str, place_name: str) -> bool:
        left = re.sub(r"[^\w\u4e00-\u9fff]", "", query).lower()
        right = re.sub(r"[^\w\u4e00-\u9fff]", "", place_name).lower()
        return bool(left and right and (left in right or right in left))

    def _constraint_text_token(
        self,
        request: AiPlanGenerationRequest,
        place: PlaceSummary,
    ) -> str | None:
        text = re.sub(r"\s+", "", request.freeText or "")
        candidates = [place.name, *self._named_constraint_queries(request, required=True)]
        return next(
            (
                token
                for token in candidates
                if token
                and self._constraint_query_matches(token, place.name)
                and re.sub(r"\s+", "", token) in text
            ),
            None,
        )

    def _missing_required_place_queries(
        self,
        request: AiPlanGenerationRequest,
        days: list[AiGeneratedDay],
    ) -> list[str]:
        names = [place.name for day in days for place in day.places]
        return [
            query
            for query in self._named_constraint_queries(request, required=True)
            if not any(self._constraint_query_matches(query, name) for name in names)
        ]

    def _draft_completeness_violations(
        self,
        request: AiPlanGenerationRequest,
        days: list[AiGeneratedDay],
    ) -> list[str]:
        by_index = {day.dayIndex: day for day in days}
        violations: list[str] = []
        for day_index in range(1, request.dayCount + 1):
            day = by_index.get(day_index)
            if day is None:
                violations.append(f"缺少第{day_index}天")
                continue
            if not day.places:
                violations.append(f"第{day_index}天没有可执行地点或用户锚点")
                continue
            if any(place.category == "scenic" for place in day.places):
                continue
            start, end = self._effective_day_bounds(request, day_index)
            has_transport = any(place.category == "transport" for place in day.places)
            arrival_or_departure_day = day_index in {
                request.arrivalDay,
                request.departureDay or request.dayCount,
            }
            if not (arrival_or_departure_day and (has_transport or end - start <= 210)):
                violations.append(f"第{day_index}天没有通过时间窗和真实路线校验的景点")
        return violations

    def _requested_day_for_place(
        self,
        request: AiPlanGenerationRequest,
        place: PlaceSummary,
    ) -> int | None:
        text = re.sub(r"\s+", "", request.freeText or "")
        token = self._constraint_text_token(request, place)
        name = re.sub(r"\s+", "", token or "")
        if not text or not name or name not in text:
            return None
        position = text.find(name)
        context = text[max(0, position - 12) : position + len(name) + 20]
        match = re.search(r"第(\d{1,2})天", context)
        if match is None:
            return None
        day_index = int(match.group(1))
        return day_index if 1 <= day_index <= request.dayCount else None

    def _user_visit_window(
        self,
        request: AiPlanGenerationRequest,
        place: PlaceSummary,
        day_index: int,
        duration: int,
    ) -> TimeWindow | None:
        text = re.sub(r"\s+", "", request.freeText or "")
        token = self._constraint_text_token(request, place)
        name = re.sub(r"\s+", "", token or "")
        if not text or not name or name not in text:
            return None
        requested_day = self._requested_day_for_place(request, place)
        if requested_day is not None and requested_day != day_index:
            return None
        position = text.find(name)
        context = text[max(0, position - 12) : position + len(name) + 32]
        if not any(word in context for word in ("预约", "入场", "入园", "门票")):
            return None
        range_match = re.search(
            r"((?:[01]?\d|2[0-3]):[0-5]\d)[-—至]((?:[01]?\d|2[0-3]):[0-5]\d)",
            context,
        )
        if range_match is not None:
            start = self._time_to_minutes(self._normalize_hour(range_match.group(1)))
            end = self._time_to_minutes(self._normalize_hour(range_match.group(2)))
            return TimeWindow(start, end) if end - start >= duration else None
        time_match = re.search(r"((?:[01]?\d|2[0-3]):[0-5]\d)", context)
        if time_match is None:
            return None
        start = self._time_to_minutes(self._normalize_hour(time_match.group(1)))
        # A timed ticket normally defines entry time, not the visit's end.
        # Allow a 30-minute entry tolerance while retaining full visit duration.
        return TimeWindow(start, start + duration + 30)

    def _is_explicitly_excluded(self, request: AiPlanGenerationRequest, place: PlaceSummary) -> bool:
        return any(
            self._constraint_query_matches(query, place.name)
            for query in self._named_constraint_queries(request, required=False)
        )

    def _supports_evening_visit(
        self,
        place: PlaceSummary,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> bool:
        windows = self._opening_windows_for_day(place, request, day_index)
        night_duration = min(90, self._visit_duration_minutes("scenic", request.pace))
        if any(
            max(window.start, 17 * 60 + 30) + night_duration <= window.end
            and (
                window.latest_start if window.latest_start is not None else window.end - night_duration
            ) >= max(window.start, 17 * 60 + 30)
            for window in windows
        ):
            return True
        if windows or self._is_indoor_place(place):
            return False
        hours_text = f"{place.openingHoursToday or ''} {place.openingHoursWeek or ''}"
        return (
            "24小时" in hours_text
            or self._has_explicit_night_signal(place)
            or (self._night_requested(request) and self._is_evening_public_place(place))
        )

    def _night_requested(self, request: AiPlanGenerationRequest) -> bool:
        instructions = " ".join([*request.preferences, request.freeText or ""])
        return any(
            keyword in instructions
            for keyword in ("夜景", "夜游", "晚上", "夜间", "灯光秀", "夜市", "看夜景")
        )

    def _has_explicit_night_signal(self, place: PlaceSummary) -> bool:
        text = f"{place.name} {place.typeName or ''}"
        return any(
            keyword in text
            for keyword in (
                "夜游", "夜景", "夜市", "灯光秀", "不夜城", "外滩", "江滩",
                "滨江夜景", "滨河夜景", "夜间观光",
            )
        )

    def _is_night_experience_candidate(
        self,
        place: PlaceSummary,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> bool:
        if not self._supports_evening_visit(place, request, day_index):
            return False
        if self._has_explicit_night_signal(place):
            return True
        if self._is_first_visit_core_landmark(place) and not self._night_requested(request):
            return False
        return self._night_requested(request) and self._is_evening_public_place(place)

    def _is_evening_public_place(self, place: PlaceSummary) -> bool:
        text = f"{place.name} {place.typeName or ''}"
        return any(
            keyword in text
            for keyword in (
                "夜游", "夜景", "夜市", "步行街", "商业街", "历史街区", "广场",
                "外滩", "江滩", "滨江", "滨河", "河畔", "码头", "灯光秀",
                "胡同", "巷", "古镇", "水镇",
            )
        )

    def _night_experience_score(self, place: PlaceSummary) -> float:
        text = f"{place.name} {place.typeName or ''}"
        score = 0.0
        if any(word in text for word in ("夜游", "夜景", "灯光秀", "夜市")):
            score += 42.0
        landmark_words = (
            ("塔", "观光厅")
            if self._is_indoor_place(place)
            else ("外滩", "江滩", "江景", "塔", "城墙", "广场", "步行街", "古城")
        )
        if any(word in text for word in landmark_words):
            score += 24.0
        if place.officialScenicGrade in {"5A", "4A"}:
            score += 12.0
        try:
            score += max(0.0, float(place.rating or 0) - 4.0) * 12.0
        except ValueError:
            pass
        score += min(10.0, math.log1p(max(0, place.experienceEvidenceCount)) * 2.5)
        return score
    async def _reorder_day_with_road_matrix(
        self,
        request: AiPlanGenerationRequest,
        day_index: int,
        places: list[AiGeneratedPlace],
        weather: AmapWeatherForecastDay | None,
    ) -> list[AiGeneratedPlace]:
        """Re-solve a day against AMap road-network costs before final routing."""
        matrix_method = getattr(self._route_service, "road_time_matrix", None)
        scenic_indices = [index for index, place in enumerate(places) if place.category == "scenic"]
        if not callable(matrix_method) or len(scenic_indices) < 2:
            return places

        first_scenic = scenic_indices[0]
        last_scenic = scenic_indices[-1]
        prefix = [place for place in places[:first_scenic] if place.category not in {"food", "drink"}]
        suffix = [place for place in places[last_scenic + 1 :] if place.category not in {"food", "drink"}]
        scenic = [place for place in places if place.category == "scenic"]
        start_anchor = prefix[-1] if prefix else None
        end_anchor = suffix[0] if suffix else None
        relevant: list[AiGeneratedPlace] = []
        seen_ids: set[str] = set()
        for place in [*scenic, *([start_anchor] if start_anchor else []), *([end_anchor] if end_anchor else [])]:
            if place.sourcePoiId in seen_ids:
                continue
            seen_ids.add(place.sourcePoiId)
            relevant.append(place)
        matrix_places = [
            self._to_route_place(place).model_copy(update={"id": place.sourcePoiId})
            for place in relevant
        ]
        try:
            matrix = await matrix_method(matrix_places)
        except (HTTPException, TypeError, ValueError):
            return places
        if not matrix:
            return places

        day_start, day_end = self._effective_day_bounds(request, day_index)
        candidates: list[VisitCandidate] = []
        opening_verified: dict[str, bool] = {}
        for place in scenic:
            summary = self._generated_to_summary(place)
            duration = max(
                45,
                self._time_to_minutes(place.suggestedEnd) - self._time_to_minutes(place.suggestedStart),
            )
            windows = self._opening_windows_for_day(summary, request, day_index)
            opening_verified[place.sourcePoiId] = bool(windows)
            scheduled_as_night = (
                self._time_to_minutes(place.suggestedStart) >= 17 * 60 + 30
                and self._night_experience_score(summary) >= 24.0
                and self._supports_evening_visit(summary, request, day_index)
            )
            if not windows:
                if self._is_evening_public_place(summary) and scheduled_as_night:
                    windows = [TimeWindow(17 * 60 + 30, min(day_end, 21 * 60 + 30), 20 * 60 + 30)]
                else:
                    windows = [TimeWindow(9 * 60 + 30, min(day_end, 17 * 60 + 30))]
            if scheduled_as_night:
                night_start = 17 * 60 + 30
                windows = [
                    TimeWindow(
                        max(window.start, night_start),
                        window.end,
                        window.latest_start,
                    )
                    for window in windows
                    if window.end - max(window.start, night_start) >= duration
                    and (
                        window.latest_start is None
                        or window.latest_start >= max(window.start, night_start)
                    )
                ]
            windows = self._weather_adjusted_windows(summary, windows, weather, duration)
            reserved = self._user_visit_window(request, summary, day_index, duration)
            if reserved is not None:
                windows = [
                    TimeWindow(
                        max(window.start, reserved.start),
                        min(window.end, reserved.end),
                        min(
                            window.latest_start if window.latest_start is not None else window.end,
                            reserved.end - duration,
                        ),
                    )
                    for window in windows
                    if min(window.end, reserved.end) - max(window.start, reserved.start) >= duration
                ]
            clipped = tuple(
                TimeWindow(
                    max(day_start, window.start),
                    min(day_end, window.end),
                    min(
                        window.latest_start if window.latest_start is not None else window.end,
                        day_end - duration,
                    ),
                )
                for window in windows
                if min(day_end, window.end) - max(day_start, window.start) >= duration
            )
            if not clipped:
                continue
            score = self._candidate_score(request, summary, weather, self._generated_to_summary(start_anchor) if start_anchor else None)
            candidates.append(
                VisitCandidate(
                    place_id=place.sourcePoiId,
                    value=max(0.05, score.total * 3.0 + self._first_visit_landmark_score(summary) * 0.75),
                    duration_minutes=duration,
                    windows=clipped,
                    mandatory=(
                        self._is_user_mandatory(request, summary)
                        or self._should_protect_core_landmark(request, summary)
                        or summary.visitUnitPolicy == "BUNDLE"
                    ),
                    uncertainty_penalty=0.12 if not opening_verified[place.sourcePoiId] else 0.0,
                    category=self._experience_category(summary),
                    region=summary.districtName or summary.businessArea or "",
                ),
            )
        if not candidates:
            return places

        edges: dict[tuple[str, str], TravelEdge] = {}
        summaries = {place.sourcePoiId: self._generated_to_summary(place) for place in relevant}
        for origin in relevant:
            for destination in relevant:
                if origin.sourcePoiId == destination.sourcePoiId:
                    continue
                internal_minutes = self._internal_transfer_minutes(origin, destination)
                if internal_minutes is not None:
                    direct_km = self._distance(
                        summaries[origin.sourcePoiId], summaries[destination.sourcePoiId],
                    )
                    edges[(origin.sourcePoiId, destination.sourcePoiId)] = TravelEdge(
                        origin.sourcePoiId,
                        destination.sourcePoiId,
                        internal_minutes,
                        max(1, round(direct_km * 1000)),
                        mode="official_internal",
                        verified=True,
                    )
                    continue
                matrix_value = matrix.get((origin.sourcePoiId, destination.sourcePoiId))
                if matrix_value is not None:
                    road_minutes, road_distance = matrix_value
                    if request.transportPreference == "WALK":
                        duration = max(1, math.ceil(road_distance / 75))
                    elif request.transportPreference == "TRANSIT":
                        duration = max(8, math.ceil(road_minutes * 1.35))
                    elif request.transportPreference == "MIXED" and road_distance <= 1200:
                        duration = max(1, math.ceil(road_distance / 80))
                    elif request.transportPreference == "MIXED":
                        duration = max(8, math.ceil(road_minutes * 1.15))
                    else:
                        duration = road_minutes
                    edges[(origin.sourcePoiId, destination.sourcePoiId)] = TravelEdge(
                        origin.sourcePoiId,
                        destination.sourcePoiId,
                        duration
                        + self._exit_buffer_minutes(summaries[origin.sourcePoiId])
                        + self._entry_buffer_minutes(summaries[destination.sourcePoiId]),
                        road_distance,
                        mode="road_matrix",
                        verified=True,
                    )
                    continue
                direct_km = self._distance(summaries[origin.sourcePoiId], summaries[destination.sourcePoiId])
                edges[(origin.sourcePoiId, destination.sourcePoiId)] = TravelEdge(
                    origin.sourcePoiId,
                    destination.sourcePoiId,
                    max(12, round(10 + direct_km * 7))
                    + self._exit_buffer_minutes(summaries[origin.sourcePoiId])
                    + self._entry_buffer_minutes(summaries[destination.sourcePoiId]),
                    max(1, round(direct_km * 1350)),
                    mode="estimated",
                    verified=False,
                )

        solution = solve_day_with_time_windows(
            candidates,
            edges,
            self._day_solver_config(
                request,
                day_start,
                day_end,
                len(scenic),
                replay=True,
            ),
            start_id=start_anchor.sourcePoiId if start_anchor else None,
            end_id=end_anchor.sourcePoiId if end_anchor else None,
        )
        if not solution.feasible or not solution.ordered_place_ids:
            return places
        by_id = {place.sourcePoiId: place for place in scenic}
        visits = {visit.place_id: visit for visit in solution.visits}
        ordered: list[AiGeneratedPlace] = []
        for place_id in solution.ordered_place_ids:
            place = by_id.get(place_id)
            visit = visits.get(place_id)
            if place is None or visit is None:
                continue
            ordered.append(
                place.model_copy(
                    update={
                        "suggestedStart": self._minutes_to_time(visit.start),
                        "suggestedEnd": self._minutes_to_time(visit.end),
                        "scheduleVerified": opening_verified.get(place_id, False),
                    },
                    deep=True,
                ),
            )
        return [*prefix, *ordered, *suffix] if ordered else places
    def _day_scenic_load(
        self,
        request: AiPlanGenerationRequest,
        day: AiGeneratedDay,
    ) -> tuple[int, int, float, bool]:
        scenic = [place for place in day.places if place.category == "scenic"]
        unit_ids = {
            place.visitUnitId
            if place.visitUnitPolicy == "BUNDLE" and place.visitUnitId
            else place.sourcePoiId
            for place in scenic
        }
        visit_minutes = sum(
            max(
                0,
                self._time_to_minutes(place.suggestedEnd)
                - self._time_to_minutes(place.suggestedStart),
            )
            for place in scenic
        )
        start, end = self._effective_day_bounds(request, day.dayIndex)
        occupancy = visit_minutes / max(1, end - start)
        full_day = any(
            self._is_full_day_scenic(self._generated_to_summary(place))
            for place in scenic
        )
        return len(unit_ids), visit_minutes, round(occupancy, 3), full_day

    def _underfilled_day_reason(
        self,
        request: AiPlanGenerationRequest,
        day: AiGeneratedDay,
    ) -> str | None:
        start, end = self._effective_day_bounds(request, day.dayIndex)
        available_minutes = end - start
        unit_count, visit_minutes, _, full_day = self._day_scenic_load(request, day)
        if available_minutes <= 5 * 60 or full_day:
            return None
        target = self._scenic_target_for_request(request)
        minimum_minutes = self._minimum_scenic_minutes(request, start, end, target)
        if unit_count >= target or visit_minutes >= minimum_minutes:
            return None
        return (
            f"仅安排 {unit_count} 个主要游览单元、约 {visit_minutes} 分钟游览，"
            f"低于{PACE_LABELS[request.pace]}完整日的 {target} 个或约 {minimum_minutes} 分钟参考负载"
        )

    def _density_insertion_indexes(
        self,
        places: list[AiGeneratedPlace],
        candidate: PlaceSummary,
    ) -> list[int]:
        if not places:
            return [0]
        first = 1 if places[0].category in {"transport", "lodging"} else 0
        last = len(places) - 1 if places[-1].category in {"transport", "lodging"} else len(places)
        indexes = list(range(first, last + 1))

        def insertion_cost(index: int) -> float:
            previous = self._generated_to_summary(places[index - 1]) if index > 0 else None
            following = self._generated_to_summary(places[index]) if index < len(places) else None
            cost = 0.0
            if previous is not None:
                cost += self._distance(previous, candidate)
            if following is not None:
                cost += self._distance(candidate, following)
            if previous is not None and following is not None:
                cost -= self._distance(previous, following)
            return cost

        return sorted(indexes, key=lambda index: (insertion_cost(index), index))

    async def _repair_underfilled_days(
        self,
        request: AiPlanGenerationRequest,
        days: list[AiGeneratedDay],
        candidates: list[PlaceSummary],
        weather_forecast: list[AmapWeatherForecastDay],
        progress: ProgressCallback | None,
    ) -> list[AiGeneratedDay]:
        """Fill clearly sparse complete days without weakening route constraints."""
        if not days:
            return days
        used_ids = {place.sourcePoiId for day in days for place in day.places}
        repaired_days: list[AiGeneratedDay] = []
        profile = PACE_PROFILES[request.pace]

        for original_day in days:
            day = original_day
            additions = 0
            while additions < profile.scenic_target:
                reason = self._underfilled_day_reason(request, day)
                if reason is None:
                    break
                weather = (
                    weather_forecast[day.dayIndex - 1]
                    if day.dayIndex <= len(weather_forecast)
                    else None
                )
                scenic = [place for place in day.places if place.category == "scenic"]
                scenic_summaries = [self._generated_to_summary(place) for place in scenic]
                districts = {place.districtName for place in scenic if place.districtName}

                def nearby_distance(place: PlaceSummary) -> float:
                    return min(
                        (self._distance(place, anchor) for anchor in scenic_summaries),
                        default=0.0,
                    )

                pool = [
                    place
                    for place in candidates
                    if place.category == "scenic"
                    and place.sourcePoiId not in used_ids
                    and not self._is_explicitly_excluded(request, place)
                    and not self._is_full_day_scenic(place)
                    and self._is_open_on_trip_day(place, request, day.dayIndex)
                    and not self._weather_hard_blocked(place, weather)
                    and self._requested_day_for_place(request, place) in {None, day.dayIndex}
                    and (
                        not scenic_summaries
                        or (place.districtName and place.districtName in districts)
                        or nearby_distance(place) <= 4.0
                    )
                ]
                ranked = sorted(
                    pool,
                    key=lambda place: (
                        -self._candidate_score(
                            request,
                            place,
                            weather,
                            scenic_summaries[0] if scenic_summaries else None,
                        ).total,
                        nearby_distance(place),
                        place.sourcePoiId,
                    ),
                )[:6]
                protected_ids = {
                    place.sourcePoiId
                    for place in day.places
                    if place.category in {"scenic", "transport", "lodging"}
                }
                previous_load = self._day_scenic_load(request, day)
                accepted: AiGeneratedDay | None = None
                accepted_name = ""
                accepted_id = ""

                for candidate in ranked:
                    for insertion_index in self._density_insertion_indexes(day.places, candidate):
                        slot_start, slot_end = self._default_slot(request, insertion_index)
                        generated_candidate = self._to_generated_place(
                            candidate,
                            insertion_index,
                            {
                                "start": slot_start,
                                "end": slot_end,
                                "note": "完整日负载复核后加入的同片区顺路地点。",
                            },
                            request,
                        )
                        sequence = [
                            *day.places[:insertion_index],
                            generated_candidate,
                            *day.places[insertion_index:],
                        ]
                        scheduled = self._reschedule_generated_sequence(
                            request,
                            sequence,
                            day.dayIndex,
                        )
                        scheduled_ids = {place.sourcePoiId for place in scheduled}
                        if candidate.sourcePoiId not in scheduled_ids or not protected_ids.issubset(scheduled_ids):
                            continue
                        proposed = day.model_copy(
                            update={"places": scheduled, "transfers": []},
                            deep=True,
                        )
                        if self._route_service is not None:
                            try:
                                routed = await self._apply_actual_routes(
                                    request,
                                    [proposed],
                                    weather_forecast,
                                    None,
                                    repair_candidates=[
                                        place
                                        for place in candidates
                                        if place.sourcePoiId not in used_ids
                                        or place.sourcePoiId in scheduled_ids
                                    ],
                                )
                            except HTTPException:
                                continue
                            if not routed:
                                continue
                            proposed = routed[0]
                        proposed_ids = {place.sourcePoiId for place in proposed.places}
                        if candidate.sourcePoiId not in proposed_ids or not protected_ids.issubset(proposed_ids):
                            continue
                        longest_leg = max(
                            (transfer.durationMinutes for transfer in proposed.transfers),
                            default=0,
                        )
                        previous_longest = max(
                            (transfer.durationMinutes for transfer in day.transfers),
                            default=0,
                        )
                        if longest_leg > max(profile.max_fill_leg_minutes, previous_longest):
                            continue
                        new_load = self._day_scenic_load(request, proposed)
                        if new_load[0] <= previous_load[0] and new_load[1] <= previous_load[1]:
                            continue
                        accepted = proposed.model_copy(
                            update={
                                "estimatedDistanceKm": round(
                                    sum(item.distanceMeters for item in proposed.transfers) / 1000,
                                    1,
                                ),
                                "intensity": self._intensity(proposed.places),
                            },
                            deep=True,
                        )
                        accepted_name = candidate.name
                        accepted_id = candidate.sourcePoiId
                        break
                    if accepted is not None:
                        break

                if accepted is None:
                    break
                day = accepted
                used_ids.update(place.sourcePoiId for place in day.places)
                used_ids.add(accepted_id)
                additions += 1
                self._notify(
                    progress,
                    72,
                    f"第 {day.dayIndex} 天偏空，已补充同片区的 {accepted_name}",
                    len(repaired_days),
                    partial_days=[*repaired_days, day],
                    event=self._event(
                        "PLAN_REFINED",
                        f"第 {day.dayIndex} 天原计划{reason}；已加入 {accepted_name}。",
                        day_index=day.dayIndex,
                        evidence=["候选当日开放", "原有主要地点全部保留", "补点后真实路线仍通过"],
                        decision="只补充同片区且不会引入超长通勤的地点。",
                    ),
                    active_day_index=day.dayIndex,
                )
            repaired_days.append(day)
        return repaired_days

    async def _apply_actual_routes(
        self,
        request: AiPlanGenerationRequest,
        days: list[AiGeneratedDay],
        weather_forecast: list[AmapWeatherForecastDay],
        progress: ProgressCallback | None,
        repair_candidates: list[PlaceSummary] | None = None,
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
        repair_candidates = repair_candidates or []
        planned_ids = {place.sourcePoiId for day in days for place in day.places}
        repair_used_ids = set(planned_ids)
        total_legs = sum(max(0, len(day.places) - 1) for day in days)
        completed_legs = 0
        for day in days:
            weather = weather_forecast[day.dayIndex - 1] if day.dayIndex <= len(weather_forecast) else None
            route_places = list(day.places)
            existing_meals = [place.name for place in route_places if place.category in {"food", "drink"}]
            if repair_candidates and any(place.category in {"food", "drink"} for place in repair_candidates):
                removed_meal_ids = {
                    place.sourcePoiId for place in route_places if place.category in {"food", "drink"}
                }
                repair_used_ids.difference_update(removed_meal_ids)
                route_places = [place for place in route_places if place.category not in {"food", "drink"}]
            route_places = await self._reorder_day_with_road_matrix(
                request,
                day.dayIndex,
                route_places,
                weather,
            )
            route_places, removed_meals = self._filter_meal_detours(request, route_places)
            removed_meals = list(dict.fromkeys([*existing_meals, *removed_meals]))
            weather_text = f"{weather.day_weather}{weather.night_weather}" if weather else ""
            try:
                too_hot_to_cycle = weather is not None and float(weather.day_temp or 0) >= 32
            except ValueError:
                too_hot_to_cycle = False
            allow_cycling = not too_hot_to_cycle and not any(
                word in weather_text for word in ("雨", "雪", "雷", "冰雹", "大风", "沙尘")
            )
            trip_date = self._trip_date(request, day.dayIndex)
            reinserted_meals: list[str] = []
            if removed_meals and repair_candidates:
                route_places, reinserted_meals = await self._reinsert_missing_meals(
                    request,
                    day.dayIndex,
                    route_places,
                    repair_candidates,
                    repair_used_ids,
                    trip_date.strftime("%Y-%m-%d") if trip_date else None,
                    allow_cycling,
                )
            route_places, actual_detour_meals = await self._filter_meal_actual_detours(
                request,
                route_places,
                trip_date.strftime("%Y-%m-%d") if trip_date else None,
                allow_cycling,
            )
            if actual_detour_meals and repair_candidates:
                route_places, actual_reinserted = await self._reinsert_missing_meals(
                    request,
                    day.dayIndex,
                    route_places,
                    repair_candidates,
                    repair_used_ids,
                    trip_date.strftime("%Y-%m-%d") if trip_date else None,
                    allow_cycling,
                )
                reinserted_meals.extend(
                    name for name in actual_reinserted if name not in reinserted_meals
                )
                route_places, second_pass_removed = await self._filter_meal_actual_detours(
                    request,
                    route_places,
                    trip_date.strftime("%Y-%m-%d") if trip_date else None,
                    allow_cycling,
                )
                actual_detour_meals.extend(
                    name for name in second_pass_removed if name not in actual_detour_meals
                )
            removed_meals.extend(name for name in actual_detour_meals if name not in removed_meals)
            removed_meals = [name for name in removed_meals if name not in reinserted_meals]
            if reinserted_meals:
                self._notify(
                    progress,
                    75,
                    f"已重新插入 {len(reinserted_meals)} 个顺路餐馆",
                    len(routed_days),
                    partial_days=[*routed_days, day.model_copy(update={"places": route_places}, deep=True)],
                    event=self._event(
                        "MEAL_PLACED",
                        f"原餐馆绕行超限后，已改为：{', '.join(reinserted_meals)}。",
                        day_index=day.dayIndex,
                        evidence=["新餐馆位于同一游览走廊", "高德实际绕行重新通过阈值校验"],
                        decision="保留餐期，但不保留不顺路的原餐馆。",
                    ),
                    active_day_index=day.dayIndex,
                )
            if removed_meals:
                self._notify(
                    progress,
                    75,
                    f"已移除 {len(removed_meals)} 个绕行过远的餐馆",
                    len(routed_days),
                    partial_days=[*routed_days, day.model_copy(update={"places": route_places}, deep=True)],
                    event=self._event(
                        "MEAL_PLACED",
                        f"{', '.join(removed_meals)} 不在相邻地点的顺路通勤范围内，已移除。",
                        day_index=day.dayIndex,
                        evidence=["餐馆的几何走廊或高德实际路线绕行超过当前阈值"],
                        decision="宁可不推荐餐馆，也不让用户为用餐明显折返。",
                    ),
                    active_day_index=day.dayIndex,
                )
            retained: list[AiGeneratedPlace] = []
            transfers: list[AiGeneratedTransfer] = []

            for original in route_places:
                if not retained:
                    retained.append(original.model_copy(deep=True))
                    continue

                previous = retained[-1]
                departure_time = previous.suggestedEnd
                warning: str | None = None
                verified = True
                internal_minutes = self._internal_transfer_minutes(previous, original)
                if internal_minutes is not None:
                    direct_km = self._distance_coordinates(
                        previous.latitude,
                        previous.longitude,
                        original.latitude,
                        original.longitude,
                    )
                    distance_meters = max(1, round(direct_km * 1000))
                    duration_minutes = internal_minutes
                    mode = "driving"
                    mode_label = "景区接驳"
                    polyline = [
                        {"latitude": previous.latitude, "longitude": previous.longitude},
                        {"latitude": original.latitude, "longitude": original.longitude},
                    ]
                else:
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
                        mode_label = self._route_mode_label(segment.mode, segment.steps)
                        warning = segment.warning
                        polyline = segment.polyline
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
                        mode_label = self._route_mode_label(mode, [])
                        warning = f"实时路线不可用，采用保守预留：{exc.detail}"
                        polyline = [
                            {"latitude": previous.latitude, "longitude": previous.longitude},
                            {"latitude": original.latitude, "longitude": original.longitude},
                        ]

                previous_summary = self._generated_to_summary(previous)
                original_summary = self._generated_to_summary(original)
                entrance_buffer = 0 if internal_minutes is not None else self._entry_buffer_minutes(original_summary)
                exit_buffer = 0 if internal_minutes is not None else self._exit_buffer_minutes(previous_summary)
                earliest = (
                    self._time_to_minutes(previous.suggestedEnd)
                    + exit_buffer
                    + duration_minutes
                    + entrance_buffer
                )
                adjusted = self._fit_place_after_route(
                    request, original, day.dayIndex, earliest, weather=weather,
                )
                if adjusted is None:
                    repaired = None
                    if (
                        original.category == "scenic"
                        and repair_candidates
                        and original.visitUnitPolicy != "BUNDLE"
                        and not self._should_protect_core_landmark(request, original_summary)
                    ):
                        repaired = await self._try_actual_route_replacement(
                            request,
                            day.dayIndex,
                            previous,
                            original,
                            repair_candidates,
                            repair_used_ids,
                            trip_date.strftime("%Y-%m-%d") if trip_date else None,
                            allow_cycling,
                            weather,
                        )
                    if repaired is not None:
                        adjusted, repaired_transfer = repaired
                        repair_used_ids.add(adjusted.sourcePoiId)
                        mode = repaired_transfer.mode
                        mode_label = repaired_transfer.modeLabel or self._route_mode_label(mode, [])
                        distance_meters = repaired_transfer.distanceMeters
                        duration_minutes = repaired_transfer.durationMinutes
                        verified = repaired_transfer.verified
                        warning = repaired_transfer.warning
                        polyline = repaired_transfer.polyline
                        self._notify(
                            progress,
                            min(92, 75 + round(12 * completed_legs / max(total_legs, 1))),
                            f"{original.name} 时间冲突，已替换为同片区的 {adjusted.name}",
                            len(routed_days),
                            event=self._event(
                                "TIME_WINDOW_CHECK",
                                f"{original.name} 按真实通勤到达后已无可用时段；{adjusted.name} 可按 "
                                f"{adjusted.suggestedStart}-{adjusted.suggestedEnd} 游览。",
                                day_index=day.dayIndex,
                                place_id=adjusted.id,
                                evidence=[f"高德通勤 {duration_minutes} 分钟", "替代点当日开放且位于同片区"],
                                decision=f"用 {adjusted.name} 替换 {original.name}，并重新计算后续路线。",
                            ),
                            active_day_index=day.dayIndex,
                        )
                    elif (
                        original.category in {"transport", "lodging"}
                        or self._is_user_mandatory(request, original_summary)
                        or original.visitUnitPolicy == "BUNDLE"
                    ):
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                f"真实路线校验后无法同时满足硬约束：从 {previous.name} 出发最早 "
                                f"{self._minutes_to_time(earliest)} 到达 {original.name}，已超出可用时段。"
                            ),
                        )
                    else:
                        self._notify(
                            progress,
                            min(92, 75 + round(12 * completed_legs / max(total_legs, 1))),
                            f"{original.name} 与营业或离开时间冲突，且无合格同区替代",
                            len(routed_days),
                            partial_days=[*routed_days, day.model_copy(update={"places": retained}, deep=True)],
                            event=self._event(
                                "TIME_WINDOW_CHECK",
                                f"从 {previous.name} 出发后最早 {self._minutes_to_time(earliest)} 到达，{original.name} 无可用参观时段。",
                                day_index=day.dayIndex,
                                place_id=original.id,
                                evidence=[f"通勤 {duration_minutes} 分钟", original.openingHoursWeek or original.openingHoursToday or "开放时间未知"],
                                decision="同片区候选也未通过真实路线与开放时间校验，因此移除该可选地点。",
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
                        modeLabel=mode_label,
                        distanceMeters=distance_meters,
                        durationMinutes=duration_minutes,
                        verified=verified,
                        warning=warning,
                        polyline=polyline,
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
                        f"{previous.name} → {adjusted.name}：{mode_label}，约 {duration_minutes} 分钟、{distance_meters / 1000:.1f} 公里。",
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

    async def _try_actual_route_replacement(
        self,
        request: AiPlanGenerationRequest,
        day_index: int,
        previous: AiGeneratedPlace,
        original: AiGeneratedPlace,
        candidates: list[PlaceSummary],
        used_ids: set[str],
        departure_date: str | None,
        allow_cycling: bool,
        weather: AmapWeatherForecastDay | None,
    ) -> tuple[AiGeneratedPlace, AiGeneratedTransfer] | None:
        original_summary = self._generated_to_summary(original)
        pool = [
            place
            for place in candidates
            if place.category == original.category
            and place.sourcePoiId not in used_ids
            and not self._is_explicitly_excluded(request, place)
            and self._is_open_on_trip_day(place, request, day_index)
            and not self._weather_hard_blocked(place, weather)
            and self._requested_day_for_place(request, place) in {None, day_index}
            and (
                bool(place.districtName and place.districtName == original.districtName)
                or self._distance(place, original_summary) <= 4.0
            )
        ]
        ranked = sorted(
            pool,
            key=lambda place: (
                -self._candidate_score(request, place, weather, original_summary).total,
                self._distance(place, original_summary),
                place.sourcePoiId,
            ),
        )[:6]
        for candidate in ranked:
            proposed = self._to_generated_place(
                candidate,
                0,
                {
                    "start": original.suggestedStart,
                    "end": original.suggestedEnd,
                    "note": f"真实路线复核后替换原计划中的 {original.name}。",
                },
                request,
            )
            try:
                segment = await self._route_service.best_segment(
                    origin=self._to_route_place(previous),
                    destination=self._to_route_place(proposed),
                    preference=request.transportPreference,
                    departure_date=departure_date,
                    departure_time=previous.suggestedEnd,
                    allow_cycling=allow_cycling,
                )
            except HTTPException:
                continue
            duration_minutes = max(1, math.ceil(segment.durationSeconds / 60))
            earliest = (
                self._time_to_minutes(previous.suggestedEnd)
                + self._exit_buffer_minutes(self._generated_to_summary(previous))
                + duration_minutes
                + self._entry_buffer_minutes(candidate)
            )
            adjusted = self._fit_place_after_route(
                request, proposed, day_index, earliest, weather=weather,
            )
            if adjusted is None:
                continue
            return adjusted, AiGeneratedTransfer(
                originPlaceId=previous.id,
                destinationPlaceId=adjusted.id,
                mode=segment.mode,
                modeLabel=self._route_mode_label(segment.mode, segment.steps),
                distanceMeters=max(0, segment.distanceMeters),
                durationMinutes=duration_minutes,
                verified=True,
                warning=segment.warning,
                polyline=segment.polyline,
            )
        return None

    async def _nearby_meal_candidates(
        self,
        previous: AiGeneratedPlace,
        following: AiGeneratedPlace,
        role: str,
        city_name: str,
    ) -> list[PlaceSummary]:
        search_nearby = getattr(self._poi_service, "search_nearby_pois", None)
        adcode = previous.adCode or following.adCode
        if not callable(search_nearby) or not adcode:
            return []
        radius = {"BREAKFAST": 1200, "LUNCH": 2200, "DINNER": 2800}.get(role, 2200)
        common = {
            "latitude": (previous.latitude + following.latitude) / 2,
            "longitude": (previous.longitude + following.longitude) / 2,
            "adcode": adcode,
            "category": "food",
            "radius_meters": radius,
            "page_size": 20,
        }
        local_keyword = self._category_search_keyword(city_name, "food")
        try:
            local = await search_nearby(keyword=local_keyword, **common)
            if local:
                return local
            return await search_nearby(keyword=None, **common)
        except HTTPException:
            return []
    async def _reinsert_missing_meals(
        self,
        request: AiPlanGenerationRequest,
        day_index: int,
        places: list[AiGeneratedPlace],
        candidates: list[PlaceSummary],
        used_ids: set[str],
        departure_date: str | None,
        allow_cycling: bool,
    ) -> tuple[list[AiGeneratedPlace], list[str]]:
        scenic_places = [place for place in places if place.category == "scenic"]
        if not scenic_places:
            return places, []
        full_day = any(self._is_full_day_scenic(self._generated_to_summary(place)) for place in scenic_places)
        requested_roles = self._requested_meal_roles(request, day_index, full_day)
        present_roles = {place.mealType for place in places if place.mealType}
        food_pool = [
            place
            for place in candidates
            if place.category in {"food", "drink"}
            and place.sourcePoiId not in used_ids
            and not self._is_explicitly_excluded(request, place)
        ]
        working = list(places)
        inserted_names: list[str] = []
        attempted_ids = set(used_ids)
        for role in requested_roles:
            if role in present_roles:
                continue
            scenic_indices = [index for index, place in enumerate(working) if place.category == "scenic"]
            if not scenic_indices:
                continue
            if role == "BREAKFAST":
                insert_at = scenic_indices[0]
                previous = working[insert_at - 1] if insert_at > 0 else working[insert_at]
                following = working[insert_at]
            elif role == "LUNCH":
                first_scenic_index = scenic_indices[0]
                if self._time_to_minutes(working[first_scenic_index].suggestedStart) >= 13 * 60 + 30:
                    insert_at = first_scenic_index
                    previous = working[insert_at - 1] if insert_at > 0 else working[insert_at]
                    following = working[insert_at]
                else:
                    insert_at = scenic_indices[1] if len(scenic_indices) > 1 else scenic_indices[0] + 1
                    previous = working[insert_at - 1]
                    following = working[insert_at] if insert_at < len(working) else previous
            else:
                night_index = next(
                    (
                        index
                        for index in scenic_indices
                        if self._time_to_minutes(working[index].suggestedStart) >= 17 * 60 + 30
                    ),
                    None,
                )
                if night_index is not None and night_index > 0:
                    insert_at = night_index
                    previous = working[insert_at - 1]
                    following = working[insert_at]
                else:
                    insert_at = scenic_indices[-1] + 1
                    previous = working[scenic_indices[-1]]
                    following = working[insert_at] if insert_at < len(working) else previous

            nearby_food = await self._nearby_meal_candidates(previous, following, role, request.destination)
            if nearby_food:
                food_pool = self._dedupe_candidates([*nearby_food, *food_pool])
            for _ in range(8):
                meal = self._pick_meal(
                    food_pool,
                    attempted_ids,
                    self._generated_to_summary(previous),
                    self._generated_to_summary(following),
                    role,
                    request.destination,
                    request.transportPreference,
                )
                if meal is None:
                    break
                attempted_ids.add(meal.sourcePoiId)
                generated = self._schedule_places(
                    request,
                    [meal],
                    day_index,
                    meal_roles={meal.sourcePoiId: role},
                )
                if not generated:
                    continue
                proposed = [*working[:insert_at], generated[0], *working[insert_at:]]
                filtered, removed = await self._filter_meal_actual_detours(
                    request,
                    proposed,
                    departure_date,
                    allow_cycling,
                )
                if meal.id in {place.id for place in filtered} and meal.name not in removed:
                    working = proposed
                    used_ids.add(meal.sourcePoiId)
                    present_roles.add(role)
                    inserted_names.append(meal.name)
                    break
        return working, inserted_names

    async def _filter_meal_actual_detours(
        self,
        request: AiPlanGenerationRequest,
        places: list[AiGeneratedPlace],
        departure_date: str | None,
        allow_cycling: bool,
    ) -> tuple[list[AiGeneratedPlace], list[str]]:
        """Use routed rather than straight-line detours for middle-of-day meals.

        A route-service failure is inconclusive and therefore does not mark a
        restaurant unreachable. The retained leg is later shown as unverified
        if all transport modes still fail.
        """
        if self._route_service is None or len(places) < 3:
            return places, []
        removed_ids: set[str] = set()
        removed_names: list[str] = []
        for index in range(1, len(places) - 1):
            meal = places[index]
            if meal.category not in {"food", "drink"}:
                continue
            previous = places[index - 1]
            following = places[index + 1]
            try:
                first, second, direct = await asyncio.gather(
                    self._route_service.best_segment(
                        origin=self._to_route_place(previous),
                        destination=self._to_route_place(meal),
                        preference=request.transportPreference,
                        departure_date=departure_date,
                        departure_time=previous.suggestedEnd,
                        allow_cycling=allow_cycling,
                    ),
                    self._route_service.best_segment(
                        origin=self._to_route_place(meal),
                        destination=self._to_route_place(following),
                        preference=request.transportPreference,
                        departure_date=departure_date,
                        departure_time=meal.suggestedEnd,
                        allow_cycling=allow_cycling,
                    ),
                    self._route_service.best_segment(
                        origin=self._to_route_place(previous),
                        destination=self._to_route_place(following),
                        preference=request.transportPreference,
                        departure_date=departure_date,
                        departure_time=previous.suggestedEnd,
                        allow_cycling=allow_cycling,
                    ),
                )
            except HTTPException:
                continue
            detour_minutes = max(
                0,
                math.ceil((first.durationSeconds + second.durationSeconds - direct.durationSeconds) / 60),
            )
            detour_meters = max(0, first.distanceMeters + second.distanceMeters - direct.distanceMeters)
            role = meal.mealType or "LUNCH"
            unreasonable = detour_minutes > (20 if role == "DINNER" else 15) or detour_meters > (
                1000 if role == "BREAKFAST" else 2000
            )
            if role == "BREAKFAST" and first.distanceMeters > 1000:
                unreasonable = True
            if role == "DINNER" and math.ceil(first.durationSeconds / 60) > 20:
                unreasonable = True
            if unreasonable:
                removed_ids.add(meal.id)
                removed_names.append(meal.name)
        return [place for place in places if place.id not in removed_ids], removed_names

    @staticmethod
    def _route_mode_label(mode: str, steps: list[object]) -> str:
        if mode != "transit":
            return {
                "walking": "步行",
                "driving": "驾车",
                "cycling": "骑行",
            }.get(mode, "交通")

        instructions = " ".join(
            str(getattr(step, "instruction", "") or "")
            for step in steps
        )
        labels: list[str] = []
        keyword_groups = (
            ("地铁", ("地铁", "轨道交通", "轻轨")),
            ("有轨电车", ("有轨电车",)),
            ("公交", ("公交", "公共汽车", "巴士", "BRT", "快速公交")),
            ("轮渡", ("轮渡", "渡船", "客轮")),
            ("索道", ("索道", "缆车")),
        )
        for label, keywords in keyword_groups:
            if any(keyword.lower() in instructions.lower() for keyword in keywords):
                labels.append(label)
        return " + ".join(labels) if labels else "公共交通"

    def _fit_place_after_route(
        self,
        request: AiPlanGenerationRequest,
        place: AiGeneratedPlace,
        day_index: int,
        earliest: int,
        weather: AmapWeatherForecastDay | None = None,
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
            scheduled_as_night = (
                self._time_to_minutes(place.suggestedStart) >= 17 * 60 + 30
                and self._supports_evening_visit(summary, request, day_index)
                and (
                    self._has_explicit_night_signal(summary)
                    or self._is_evening_public_place(summary)
                )
            )
            if scheduled_as_night:
                earliest = max(earliest, 17 * 60 + 30)
            windows = self._opening_windows_for_day(summary, request, day_index)
            windows = self._weather_adjusted_windows(summary, windows, weather, duration)
            reserved_window = self._user_visit_window(request, summary, day_index, duration)
            if reserved_window is not None:
                windows = [
                    TimeWindow(
                        start=max(window.start, reserved_window.start),
                        end=min(window.end, reserved_window.end),
                        latest_start=min(
                            window.latest_start if window.latest_start is not None else window.end,
                            reserved_window.end - duration,
                        ),
                    )
                    for window in windows or [reserved_window]
                    if min(window.end, reserved_window.end) - max(window.start, reserved_window.start) >= duration
                ]
            if windows:
                slot = self._find_open_slot(windows, earliest, duration)
                if slot is None:
                    return None
                start = slot[0]
            else:
                if self._is_evening_public_place(summary) and scheduled_as_night:
                    duration = min(duration, 90)
                    start = max(earliest, 17 * 60 + 30)
                    day_end = min(day_end, 21 * 60 + 30)
                else:
                    start = max(earliest, 9 * 60 + 30)
                    day_end = min(day_end, 17 * 60 + 30)
        elif place.category in {"food", "drink"}:
            original_start = self._time_to_minutes(place.suggestedStart)
            meal_type = place.mealType or ("BREAKFAST" if original_start < 10 * 60 else "LUNCH" if original_start < 15 * 60 else "DINNER")
            meal_start, meal_end = {
                "BREAKFAST": (7 * 60 + 30, 11 * 60),
                "LUNCH": (11 * 60 + 30, 14 * 60),
                "DINNER": (17 * 60 + 30, 21 * 60),
            }[meal_type]
            start = max(earliest, meal_start)
            windows = self._opening_windows_for_day(summary, request, day_index)
            if windows:
                slot = self._find_open_slot(windows, start, duration)
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

    def _map_point_summary(
        self,
        point: Any | None,
        category: str,
        city_name: str,
        ad_code: str,
    ) -> PlaceSummary | None:
        if point is None:
            return None
        coordinate_id = f"{point.latitude:.6f}-{point.longitude:.6f}"
        return PlaceSummary(
            id=f"map-{category}-{coordinate_id}",
            source="MAP_SELECTED",
            sourcePoiId=f"map-{coordinate_id}",
            name=point.name.strip(),
            category=category,
            categoryCode="MAP_SELECTED",
            typeName="地图选点",
            address=point.address,
            provinceName=point.provinceName,
            cityName=point.cityName or city_name,
            districtName=point.districtName,
            adCode=point.adCode or ad_code,
            latitude=point.latitude,
            longitude=point.longitude,
        )

    def _validate_map_point_cities(
        self,
        request: AiPlanGenerationRequest,
        destination_ad_code: str,
        destination_name: str,
    ) -> None:
        points = [
            ("到达点", request.arrivalPoint),
            ("离开点", request.departurePoint),
            ("住宿点", request.hotelPoint),
            *[(f"第{stay.checkInDay}天住宿点", stay.mapPoint) for stay in request.hotelStays],
        ]
        for role, point in points:
            if point is None or not point.adCode:
                continue
            if not self._adcode_belongs_to_city(point.adCode, destination_ad_code):
                raise HTTPException(
                    status_code=422,
                    detail=f"{role}“{point.name}”不在目的城市 {destination_name} 范围内，请重新选择。",
                )

    @staticmethod
    def _adcode_belongs_to_city(candidate: str, selected: str) -> bool:
        candidate = candidate.strip()
        selected = selected.strip()
        if selected.endswith("0000"):
            return candidate[:2] == selected[:2]
        if selected.endswith("00"):
            return candidate[:4] == selected[:4]
        return candidate == selected

    @staticmethod
    def _normalized_region(value: str) -> str:
        return value.strip().removesuffix("特别行政区").removesuffix("自治区").removesuffix("省").removesuffix("市")

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
            officialScenicGrade=place.officialScenicGrade,
            experienceEvidenceCount=place.experienceEvidenceCount,
            officialReservationRequired=place.officialReservationRequired,
            officialReservationNote=place.officialReservationNote,
            officialClosedDates=place.officialClosedDates,
            officialClosureWarning=place.officialClosureWarning,
            officialOpeningHoursByDate=place.officialOpeningHoursByDate,
            officialAccessNote=place.officialAccessNote,
            officialMaxDailyCapacity=place.officialMaxDailyCapacity,
            officialCapacityNote=place.officialCapacityNote,
            officialTicketNote=place.officialTicketNote,
            crowdRisk=place.crowdRisk,
            contentUpdatedAt=place.contentUpdatedAt,
            visitUnitId=place.visitUnitId,
            visitUnitName=place.visitUnitName,
            visitUnitPolicy=place.visitUnitPolicy,
            visitUnitMemberOrder=place.visitUnitMemberOrder,
            visitUnitTransferMinutes=place.visitUnitTransferMinutes,
            visitUnitSourceUrl=place.visitUnitSourceUrl,
            recommendedVisitMinutes=place.recommendedVisitMinutes,
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

    def _attach_day_alternatives(
        self,
        request: AiPlanGenerationRequest,
        days: list[AiGeneratedDay],
        candidates: list[PlaceSummary],
        weather_forecast: list[AmapWeatherForecastDay],
    ) -> list[AiGeneratedDay]:
        used_ids = {place.sourcePoiId for day in days for place in day.places}
        reserved_alternative_ids: set[str] = set()
        scenic_pool = [
            place
            for place in candidates
            if place.category == "scenic"
            and place.sourcePoiId not in used_ids
            and not self._is_explicitly_excluded(request, place)
        ]
        result: list[AiGeneratedDay] = []
        for day in days:
            weather = weather_forecast[day.dayIndex - 1] if day.dayIndex <= len(weather_forecast) else None
            anchors = [place for place in day.places if place.category == "scenic"]
            anchor_summaries = [self._generated_to_summary(place) for place in anchors]
            district_names = {place.districtName for place in anchors if place.districtName}

            def nearby_distance(place: PlaceSummary) -> float:
                return min((self._distance(place, anchor) for anchor in anchor_summaries), default=999.0)

            viable = [
                place
                for place in scenic_pool
                if place.sourcePoiId not in reserved_alternative_ids
                and self._is_open_on_trip_day(place, request, day.dayIndex)
                and not self._weather_hard_blocked(place, weather)
                and self._requested_day_for_place(request, place) in {None, day.dayIndex}
                and (
                    (place.districtName and place.districtName in district_names)
                    or nearby_distance(place) <= 4.0
                )
            ]
            ranked = sorted(
                viable,
                key=lambda place: (
                    -self._candidate_score(request, place, weather, anchor_summaries[0] if anchor_summaries else None).total,
                    nearby_distance(place),
                    place.sourcePoiId,
                ),
            )[:2]
            alternatives: list[AiPlanAlternative] = []
            for place in ranked:
                reserved_alternative_ids.add(place.sourcePoiId)
                distance_km = nearby_distance(place)
                weather_reason = (
                    "恶劣天气下可替换为室内地点；"
                    if weather is not None and self._is_indoor_place(place)
                    and any(word in f"{weather.day_weather}{weather.night_weather}" for word in ("雨", "雪", "风", "高温"))
                    else ""
                )
                alternatives.append(
                    AiPlanAlternative(
                        id=place.id,
                        sourcePoiId=place.sourcePoiId,
                        name=place.name,
                        category=place.category,
                        latitude=place.latitude or 0.0,
                        longitude=place.longitude or 0.0,
                        districtName=place.districtName,
                        openingHoursWeek=place.openingHoursWeek,
                        officialReservationRequired=place.officialReservationRequired,
                        reason=f"{weather_reason}与当天游览片区最近约 {distance_km:.1f} 公里，替换后需刷新路线。",
                    ),
                )
            summary = day.summary
            if alternatives:
                summary = f"{summary} 同片区备选：{'、'.join(item.name for item in alternatives)}。"
            result.append(day.model_copy(update={"alternatives": alternatives, "summary": summary}, deep=True))
        return result

    def _weather_needs_indoor_recall(self, weather: AmapWeatherForecastDay) -> bool:
        text = f"{weather.day_weather}{weather.night_weather}"
        try:
            high = float(weather.day_temp or 0)
        except ValueError:
            high = 0.0
        return high >= 33 or any(
            word in text
            for word in ("雨", "雪", "雷", "冰雹", "沙尘", "大风", "雾")
        )

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

    def _weather_adjusted_windows(
        self,
        place: PlaceSummary,
        windows: list[TimeWindow],
        weather: AmapWeatherForecastDay | None,
        duration: int,
    ) -> list[TimeWindow]:
        if weather is None or self._is_indoor_place(place):
            return windows
        try:
            high = float(weather.day_temp or 0)
        except ValueError:
            high = 0.0
        if high < 33:
            return windows
        comfortable_periods = ((7 * 60, 11 * 60 + 30), (16 * 60 + 30, 21 * 60 + 30))
        adjusted: list[TimeWindow] = []
        for window in windows:
            for period_start, period_end in comfortable_periods:
                start = max(window.start, period_start)
                end = min(window.end, period_end)
                latest_start = min(
                    window.latest_start if window.latest_start is not None else window.end,
                    end - duration,
                )
                if end - start >= duration and latest_start >= start:
                    adjusted.append(TimeWindow(start, end, latest_start))
        return adjusted
    def _weather_hard_blocked(
        self,
        place: PlaceSummary,
        weather: AmapWeatherForecastDay | None,
    ) -> bool:
        if weather is None or self._is_indoor_place(place):
            return False
        weather_text = f"{weather.day_weather}{weather.night_weather}"
        extreme = any(
            word in weather_text
            for word in ("台风", "暴雨", "雷暴", "冰雹", "大雪", "暴雪", "沙尘暴", "强风")
        )
        if extreme:
            return True
        sensitive = any(
            word in f"{place.name} {place.typeName or ''}"
            for word in ("山顶", "索道", "缆车", "漂流", "游船", "轮渡", "观景台", "水上")
        )
        return sensitive and any(word in weather_text for word in ("雷", "大风", "雾", "雨", "雪"))

    def _season_place_score(self, request: AiPlanGenerationRequest, place: PlaceSummary) -> float:
        trip_date = self._trip_date(request, 1)
        if trip_date is None:
            return 0.5
        month = trip_date.month
        text = f"{place.name} {place.typeName or ''}"
        seasonal_rules = (
            (("滑雪", "冰雪", "冰雕", "雾凇"), {12, 1, 2}),
            (("樱花", "花海", "赏花", "桃花"), {3, 4, 5}),
            (("海滨", "海滩", "水上乐园", "漂流"), {6, 7, 8}),
            (("红叶", "银杏", "赏秋"), {9, 10, 11}),
        )
        for keywords, suitable_months in seasonal_rules:
            if any(keyword in text for keyword in keywords):
                return 1.0 if month in suitable_months else 0.2
        return 0.6

    def _is_indoor_place(self, place: PlaceSummary) -> bool:
        text = f"{place.name} {place.typeName or ''}"
        return any(
            word in text
            for word in ("博物馆", "美术馆", "展览馆", "科技馆", "纪念馆", "电视塔", "观光厅", "室内", "剧院", "商场", "书店")
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
        local_terms = {
            "北京": ("烤鸭", "炸酱面", "涮肉", "北京菜", "京菜", "老字号", "卤煮"),
            "上海": (
                "本帮", "沪菜", "海派", "生煎", "小笼", "红烧肉",
                "排骨年糕", "葱油拌面",
            ),
            "成都": ("川菜", "火锅", "串串", "担担面", "钟水饺"),
            "重庆": ("重庆火锅", "小面", "江湖菜"),
            "西安": ("肉夹馍", "泡馍", "凉皮", "陕菜"),
            "广州": ("粤菜", "早茶", "烧鹅", "肠粉"),
            "南京": ("盐水鸭", "鸭血粉丝", "金陵"),
            "杭州": ("杭帮菜", "西湖醋鱼", "龙井虾仁"),
        }.get(city, ("特色", "老字号"))
        characteristic_words = (city, *local_terms)
        bonus = 6.0 if any(word in place.name or word in (place.typeName or "") for word in characteristic_words) else 0.0
        if any(chain in place.name for chain in ("麦当劳", "肯德基", "星巴克", "汉堡王", "必胜客")):
            bonus -= 12.0
        return bonus

    def _pick_meal(
        self,
        food: list[PlaceSummary],
        used: set[str],
        previous: PlaceSummary,
        following: PlaceSummary,
        role: str,
        city_name: str,
        transport_preference: str,
    ) -> PlaceSummary | None:
        available = [
            place
            for place in food
            if place.sourcePoiId not in used
            and not self._is_generic_chain_food(place)
            and self._meal_role_compatible(place, role)
        ]
        if not available:
            return None

        def route_metrics(place: PlaceSummary) -> tuple[float, float, float]:
            first_leg = self._distance(previous, place)
            second_leg = self._distance(place, following)
            # Without a hotel/station anchor, breakfast is an endpoint visit
            # before the first attraction. Treating the same first attraction
            # as both corridor endpoints doubles its detour and rejects valid
            # breakfast places that are still within the 1 km limit.
            if role == "BREAKFAST" and previous.sourcePoiId == following.sourcePoiId:
                return first_leg, 0.0, first_leg
            direct = self._distance(previous, following)
            return first_leg, second_leg, max(0.0, first_leg + second_leg - direct)

        viable = [
            place
            for place in available
            if self._meal_corridor_is_reasonable(transport_preference, role, *route_metrics(place))
        ]
        if not viable:
            return None
        return min(
            viable,
            key=lambda place: (
                route_metrics(place)[2] * 1.8
                + max(route_metrics(place)[0], route_metrics(place)[1]) * 0.12
                - self._quality_score(place) * 0.06
                - self._local_food_score(city_name, place) * 0.16
                - self._meal_role_score(place, role)
            ),
        )

    def _meal_path_cost(
        self,
        previous: PlaceSummary,
        meal: PlaceSummary | None,
        following: PlaceSummary,
    ) -> float:
        if meal is None:
            return float("inf")
        direct = self._distance(previous, following)
        first = self._distance(previous, meal)
        second = self._distance(meal, following)
        return max(0.0, first + second - direct) * 1.8 + max(first, second) * 0.12

    def _meal_role_compatible(self, place: PlaceSummary, role: str) -> bool:
        text = f"{place.name} {place.typeName or ''}"
        dessert_only = any(
            word in text
            for word in (
                "冰淇淋", "冰激凌", "Gelato", "哈根达斯", "DQ", "雪糕", "冰品",
                "甜品", "糖水", "奶茶", "茶饮", "果茶", "饮品", "冷饮", "咖啡",
                "蛋糕", "奶昔",
            )
        )
        if role == "BREAKFAST":
            return not dessert_only and any(
                word in text
                for word in (
                    "早餐", "早茶", "包子", "生煎", "汤包", "豆浆", "粥", "烧饼",
                    "肠粉", "面馆", "粉店", "馄饨", "小吃",
                )
            )
        return not dessert_only
    def _is_generic_chain_food(self, place: PlaceSummary) -> bool:
        return any(
            chain in place.name
            for chain in (
                "麦当劳", "肯德基", "星巴克", "汉堡王", "必胜客", "蜜雪冰城",
                "瑞幸", "库迪", "CoCo", "一点点", "茶百道", "霸王茶姬",
            )
        )
    def _meal_role_score(self, place: PlaceSummary, role: str) -> float:
        text = f"{place.name} {place.typeName or ''}"
        words = {
            "BREAKFAST": ("早餐", "早茶", "包子", "生煎", "汤包", "豆浆", "粥", "粉", "面", "肠粉", "烧饼"),
            "LUNCH": ("小吃", "面", "粉", "简餐", "老字号", "特色"),
            "DINNER": ("本帮", "地方菜", "老字号", "火锅", "烤鸭", "粤菜", "川菜", "陕菜", "杭帮菜", "烧鹅"),
        }.get(role, ())
        return 8.0 if any(word in text for word in words) else 0.0

    def _filter_meal_detours(
        self,
        request: AiPlanGenerationRequest,
        places: list[AiGeneratedPlace],
    ) -> tuple[list[AiGeneratedPlace], list[str]]:
        """Reject meals that create a noticeable geographic detour.

        AMap still verifies every retained leg afterwards.  This geometric
        guard runs first so both heuristic and model-produced meals must stay
        near the path between their neighboring itinerary anchors.
        """
        retained: list[AiGeneratedPlace] = []
        removed: list[str] = []
        for index, place in enumerate(places):
            if place.category not in {"food", "drink"}:
                retained.append(place)
                continue
            previous = places[index - 1] if index > 0 else None
            following = places[index + 1] if index + 1 < len(places) else None
            reasonable = True
            if previous is not None and following is not None:
                first_leg = self._distance_coordinates(
                    previous.latitude, previous.longitude, place.latitude, place.longitude,
                )
                second_leg = self._distance_coordinates(
                    place.latitude, place.longitude, following.latitude, following.longitude,
                )
                direct = self._distance_coordinates(
                    previous.latitude, previous.longitude, following.latitude, following.longitude,
                )
                reasonable = self._meal_corridor_is_reasonable(
                    request.transportPreference,
                    place.mealType or "LUNCH",
                    first_leg,
                    second_leg,
                    max(0.0, first_leg + second_leg - direct),
                )
            else:
                neighbor = previous or following
                if neighbor is not None:
                    endpoint_distance = self._distance_coordinates(
                        neighbor.latitude, neighbor.longitude, place.latitude, place.longitude,
                    )
                    reasonable = self._meal_corridor_is_reasonable(
                        request.transportPreference,
                        place.mealType or "LUNCH",
                        endpoint_distance,
                        0.0,
                        endpoint_distance,
                    )
            if reasonable:
                retained.append(place)
            else:
                removed.append(place.name)
        return retained, removed

    def _meal_corridor_is_reasonable(
        self,
        transport_preference: str,
        role: str,
        first_leg_km: float,
        second_leg_km: float,
        detour_km: float,
    ) -> bool:
        minutes_per_km = {"WALK": 12.0, "MIXED": 5.0, "TRANSIT": 4.5, "DRIVE": 2.5}.get(
            transport_preference,
            5.0,
        )
        detour_limit_km = {
            "BREAKFAST": 1.0,
            "LUNCH": 2.0,
            "DINNER": 2.5,
        }.get(role, 2.0)
        detour_limit_km = min(
            detour_limit_km,
            {"WALK": 1.2, "MIXED": 1.8, "TRANSIT": 2.0, "DRIVE": 2.5}.get(
                transport_preference,
                1.8,
            ),
        )
        if detour_km > detour_limit_km or detour_km * minutes_per_km > 15.0:
            return False
        if role == "BREAKFAST" and first_leg_km > 1.0:
            return False
        if role == "DINNER" and first_leg_km * minutes_per_km > 20.0:
            return False
        return True

    def _schedule_places(
        self,
        request: AiPlanGenerationRequest,
        places: list[PlaceSummary],
        day_index: int,
        meal_roles: dict[str, str] | None = None,
        night_place_ids: set[str] | None = None,
        weather: AmapWeatherForecastDay | None = None,
    ) -> list[AiGeneratedPlace]:
        current = self._time_to_minutes(request.dailyStart)
        day_end = self._time_to_minutes(request.dailyEnd)
        departure_day = request.departureDay or request.dayCount
        if day_index == request.arrivalDay and request.arrivalTime:
            current = max(current, self._time_to_minutes(request.arrivalTime))
        if day_index == departure_day and request.departureTime:
            day_end = min(day_end, self._time_to_minutes(request.departureTime))
        generated: list[AiGeneratedPlace] = []
        meal_roles = meal_roles or {}
        night_place_ids = night_place_ids or set()
        previous: PlaceSummary | None = None

        for position, place in enumerate(places):
            if previous is not None:
                internal_minutes = self._internal_transfer_minutes(previous, place)
                if internal_minutes is not None:
                    current += internal_minutes
                else:
                    transfer_minutes = min(55, max(15, round(self._distance(previous, place) * 8)))
                    current += self._exit_buffer_minutes(previous) + transfer_minutes
            duration = self._visit_duration_for_place(place, request.pace)
            if place.category == "scenic" and not (
                previous is not None and self._internal_transfer_minutes(previous, place) is not None
            ):
                current += self._entry_buffer_minutes(place)
            confirmed_opening_windows = self._opening_windows_for_day(place, request, day_index)
            opening_windows = confirmed_opening_windows or self._opening_hint_windows_for_day(
                place,
                request,
                day_index,
            )
            if place.category == "scenic":
                opening_windows = self._weather_adjusted_windows(place, opening_windows, weather, duration)
                if place.sourcePoiId in night_place_ids:
                    current = max(current, 17 * 60 + 30)
                    duration = min(duration, 90)
                reserved_window = self._user_visit_window(request, place, day_index, duration)
                if reserved_window is not None:
                    opening_windows = [
                        TimeWindow(
                            start=max(window.start, reserved_window.start),
                            end=min(window.end, reserved_window.end),
                            latest_start=min(
                                window.latest_start if window.latest_start is not None else window.end,
                                reserved_window.end - duration,
                            ),
                        )
                        for window in opening_windows or [reserved_window]
                        if min(window.end, reserved_window.end) - max(window.start, reserved_window.start) >= duration
                    ]
            has_opening_data = bool(opening_windows)
            if place.category == "scenic" and not self._is_open_on_trip_day(place, request, day_index):
                continue

            if place.category == "scenic":
                if has_opening_data:
                    slot = self._find_open_slot(opening_windows, current, duration)
                    if slot is None:
                        continue
                    current = slot[0]
                    verified = bool(confirmed_opening_windows)
                else:
                    if (
                        self._is_evening_public_place(place)
                        and self._night_experience_score(place) >= 24.0
                        and day_end >= 19 * 60 + 30
                    ):
                        current = max(current, 17 * 60 + 30)
                        duration = min(duration, 90)
                        if current + duration > min(day_end, 21 * 60 + 30):
                            continue
                    else:
                        current = max(current, 9 * 60 + 30)
                        if current + duration > 17 * 60 + 30:
                            continue
                    verified = False
            elif place.category in {"food", "drink"}:
                meal_type = meal_roles.get(place.sourcePoiId) or (
                    "BREAKFAST" if current < 10 * 60 else "LUNCH" if current < 15 * 60 else "DINNER"
                )
                duration = {"BREAKFAST": 45, "LUNCH": 60, "DINNER": 75}[meal_type]
                desired, latest_end = {
                    "BREAKFAST": (7 * 60 + 30, 11 * 60),
                    "LUNCH": (11 * 60 + 30, 14 * 60),
                    "DINNER": (17 * 60 + 30, 21 * 60),
                }[meal_type]
                current = max(current, desired)
                if has_opening_data:
                    slot = self._find_open_slot(opening_windows, current, duration)
                    if slot is None:
                        continue
                    current = slot[0]
                    verified = bool(confirmed_opening_windows)
                else:
                    verified = False
                if current + duration > latest_end:
                    if latest_end - current < 45:
                        continue
                    duration = latest_end - current
            elif place.category == "lodging":
                duration = 45
                verified = False
            elif place.category == "transport":
                duration = self._transport_anchor_buffer_minutes(place, departing=False)
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
                    duration = self._transport_anchor_buffer_minutes(place, departing=True)
                    current = max(current, self._time_to_minutes(request.departureTime) - duration)
            else:
                verified = False

            if current + duration > day_end:
                break
            start = self._minutes_to_time(current)
            end = self._minutes_to_time(current + duration)
            meal_type = meal_roles.get(place.sourcePoiId)
            note = self._schedule_note(place, verified, meal_type)
            generated.append(
                self._to_generated_place(
                    place,
                    position,
                    {"start": start, "end": end, "note": note, "mealType": meal_type},
                    request,
                    schedule_verified=verified,
                ),
            )
            current += duration
            previous = place
        return generated

    def _entry_buffer_minutes(self, place: PlaceSummary) -> int:
        if place.category != "scenic" or self._is_evening_public_place(place):
            return 0
        text = f"{place.name} {place.typeName or ''}"
        if place.officialReservationRequired or place.officialScenicGrade == "5A":
            return 20
        if any(word in text for word in ("博物馆", "美术馆", "纪念馆", "宫", "陵", "遗址", "动物园")):
            return 15
        return 10

    def _exit_buffer_minutes(self, place: PlaceSummary) -> int:
        if place.category == "transport":
            return 0
        text = f"{place.name} {place.typeName or ''}"
        if place.category == "scenic" and (
            place.officialScenicGrade == "5A"
            or any(word in text for word in ("故宫", "长城", "动物园", "主题乐园", "大型景区"))
        ):
            return 10
        if place.category in {"scenic", "food", "drink", "lodging"}:
            return 5
        return 0

    def _day_solver_config(
        self,
        request: AiPlanGenerationRequest,
        day_start: int,
        day_end: int,
        max_visits: int,
        *,
        replay: bool = False,
    ) -> DaySolverConfig:
        """Translate pace into traveler-comfort costs, not visit-count alone."""
        profile = PACE_PROFILES[request.pace]
        minimum_visit_minutes = (
            0
            if replay
            else self._minimum_scenic_minutes(
                request,
                day_start,
                day_end,
                max_visits,
            )
        )
        return DaySolverConfig(
            day_start=day_start,
            day_end=day_end,
            max_visits=max_visits,
            travel_minute_penalty=0.018 if replay else 0.014,
            waiting_minute_penalty=0.006 if replay else 0.005,
            minimum_optional_gain=-1000.0 if replay else 0.01,
            minimum_underfilled_gain=(
                -1000.0
                if replay
                else profile.minimum_underfilled_gain
            ),
            minimum_visit_minutes=minimum_visit_minutes,
            max_normal_leg_minutes=profile.max_normal_leg_minutes,
            max_fill_leg_minutes=profile.max_fill_leg_minutes,
            max_idle_minutes=profile.max_idle_minutes,
            excess_leg_minute_penalty={"RELAXED": 0.060, "BALANCED": 0.045, "INTENSIVE": 0.030}[request.pace],
            long_idle_minute_penalty=0.020,
            cross_region_penalty={"RELAXED": 0.32, "BALANCED": 0.24, "INTENSIVE": 0.16}[request.pace],
            repeated_category_penalty=0.16,
        )

    def _minimum_scenic_minutes(
        self,
        request: AiPlanGenerationRequest,
        day_start: int,
        day_end: int,
        max_visits: int,
    ) -> int:
        """Return a soft visit-time floor for a usable sightseeing day.

        This is deliberately not a hard POI minimum. Short arrival/departure
        windows need only one normal visit, while complete BALANCED and
        INTENSIVE days aim for roughly three and four normal visits. Opening
        hours, route feasibility and the compact-filler guard remain stronger.
        """
        if max_visits <= 1 or day_end <= day_start:
            return 0
        profile = PACE_PROFILES[request.pace]
        normal_visit = profile.scenic_visit_minutes
        available_minutes = day_end - day_start
        if available_minutes <= 5 * 60:
            return min(normal_visit, available_minutes)

        desired = max(
            normal_visit * profile.minimum_full_day_units,
            round(available_minutes * profile.minimum_visit_ratio),
        )
        return min(max_visits * normal_visit, desired)

    @staticmethod
    def _experience_category(place: PlaceSummary) -> str:
        text = f"{place.name} {place.typeName or ''}"
        groups = (
            ("museum", ("博物馆", "美术馆", "纪念馆", "展览馆", "科技馆")),
            ("historic", ("古迹", "故居", "寺", "庙", "宫", "陵", "遗址", "古城", "古镇")),
            ("park", ("公园", "园林", "植物园", "动物园", "湿地")),
            ("view", ("观景", "山", "塔", "夜景", "外滩", "江滩", "湖", "海滨")),
            ("street", ("街", "胡同", "里", "市集", "夜市", "商圈")),
        )
        for category, keywords in groups:
            if any(keyword in text for keyword in keywords):
                return category
        return place.category

    def _visit_duration_minutes(self, category: str, pace: str) -> int:
        if category in {"food", "drink"}:
            return 75
        if category == "scenic":
            return PACE_PROFILES[pace].scenic_visit_minutes
        return 60

    def _visit_duration_for_place(self, place: PlaceSummary, pace: str) -> int:
        if self._is_full_day_scenic(place):
            return 360
        if place.recommendedVisitMinutes is None:
            return self._visit_duration_minutes(place.category, pace)
        factor = {"RELAXED": 1.15, "BALANCED": 1.0, "INTENSIVE": 0.85}[pace]
        return max(30, round(place.recommendedVisitMinutes * factor / 5) * 5)

    @staticmethod
    def _internal_transfer_minutes(
        origin: PlaceSummary | AiGeneratedPlace,
        destination: PlaceSummary | AiGeneratedPlace,
    ) -> int | None:
        if (
            origin.visitUnitPolicy == "BUNDLE"
            and destination.visitUnitPolicy == "BUNDLE"
            and origin.visitUnitId
            and origin.visitUnitId == destination.visitUnitId
        ):
            return max(1, destination.visitUnitTransferMinutes or 10)
        return None

    def _transport_anchor_buffer_minutes(self, place: PlaceSummary, *, departing: bool) -> int:
        text = f"{place.name} {place.typeName or ''}"
        if any(word in text for word in ("机场", "航站楼")):
            return 120 if departing else 45
        if any(word in text for word in ("火车站", "高铁", "铁路", "客运站")) or place.name.endswith("站"):
            return 45 if departing else 30
        return 30

    def _anchor_name_matches(self, actual: str, requested: str) -> bool:
        left = re.sub(r"\s+", "", actual)
        right = re.sub(r"\s+", "", requested)
        return bool(left and right and (left in right or right in left))

    def _opening_window(self, place: PlaceSummary) -> tuple[int | None, int | None, bool]:
        windows = self._opening_windows(place)
        if windows:
            window = max(windows, key=lambda item: item.end - item.start)
            return window.start, window.end, True
        return None, None, False

    def _opening_windows(self, place: PlaceSummary) -> list[TimeWindow]:
        today = self._parse_opening_windows(place.openingHoursToday)
        return today or self._parse_opening_windows(place.openingHoursWeek)

    def _opening_ranges(self, place: PlaceSummary) -> list[tuple[int, int]]:
        return [(window.start, window.end) for window in self._opening_windows(place)]

    def _find_open_slot(
        self,
        windows: list[TimeWindow] | list[tuple[int, int]],
        earliest: int,
        duration: int,
    ) -> tuple[int, int] | None:
        normalized = [
            item if isinstance(item, TimeWindow) else TimeWindow(item[0], item[1])
            for item in windows
        ]
        for window in sorted(normalized, key=lambda item: item.start):
            start = max(earliest, window.start)
            latest_start = window.latest_start if window.latest_start is not None else window.end
            if start <= latest_start and start + duration <= window.end:
                return start, start + duration
        return None

    def _slot_within_open_window(
        self,
        windows: list[TimeWindow],
        start: int,
        end: int,
    ) -> bool:
        return any(
            window.start <= start
            and start <= (window.latest_start if window.latest_start is not None else window.end)
            and end <= window.end
            for window in windows
        )
    def _opening_windows_for_day(
        self,
        place: PlaceSummary,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> list[TimeWindow]:
        trip_date = self._trip_date(request, day_index)
        if trip_date is not None:
            official_override = place.officialOpeningHoursByDate.get(trip_date.date().isoformat())
            official_windows = self._parse_opening_windows(official_override)
            if official_windows:
                return official_windows
        week_text = place.openingHoursWeek or ""
        if week_text:
            if trip_date is not None and "周" in week_text:
                day_char = "一二三四五六日"[trip_date.weekday()]
                segments = [part.strip() for part in re.split(r"[；;。]", week_text) if part.strip()]
                explicit_segments = [part for part in segments if "周" in part]
                matching_windows = [
                    window
                    for part in explicit_segments
                    if self._weekday_segment_applies(part, day_char)
                    and self._calendar_segment_applies(part, trip_date)
                    for window in self._parse_opening_windows(part)
                ]
                if matching_windows:
                    return matching_windows
                if explicit_segments:
                    return []
            week_windows = self._parse_opening_windows(week_text)
            if week_windows:
                return week_windows
        if trip_date is not None and trip_date.date() == datetime.now().date():
            return self._parse_opening_windows(place.openingHoursToday)
        return []

    def _opening_hint_windows_for_day(
        self,
        place: PlaceSummary,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> list[TimeWindow]:
        """Use unconfirmed provider hours as a soft planning hint, never as a verified fact."""
        if not self._is_open_on_trip_day(place, request, day_index):
            return []
        hinted = self._parse_opening_windows(place.openingHoursToday)
        if hinted:
            return hinted
        return self._parse_opening_windows(place.openingHoursWeek)

    def _opening_ranges_for_day(
        self,
        place: PlaceSummary,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> list[tuple[int, int]]:
        return [
            (window.start, window.end)
            for window in self._opening_windows_for_day(place, request, day_index)
        ]
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

    def _calendar_segment_applies(self, text: str, trip_date: datetime) -> bool:
        """Match dated seasonal opening segments against the actual trip date."""
        day_key = trip_date.month * 100 + trip_date.day
        date_ranges: list[tuple[int, int]] = []
        date_pattern = (
            r"(?<!\d)(\d{1,2})(?:月|[./-])(\d{1,2})日?\s*"
            r"(?:至|—|-)\s*(\d{1,2})(?:月|[./-])(\d{1,2})日?(?!\d)"
        )
        for start_month, start_day, end_month, end_day in re.findall(date_pattern, text):
            try:
                start_key = int(start_month) * 100 + int(start_day)
                end_key = int(end_month) * 100 + int(end_day)
                datetime(trip_date.year, int(start_month), int(start_day))
                datetime(trip_date.year, int(end_month), int(end_day))
            except ValueError:
                continue
            date_ranges.append((start_key, end_key))
        if date_ranges:
            return any(
                start <= day_key <= end
                if start <= end
                else day_key >= start or day_key <= end
                for start, end in date_ranges
            )

        month_ranges = [
            (int(start), int(end))
            for start, end in re.findall(r"(\d{1,2})月\s*(?:至|—|-)\s*(\d{1,2})月", text)
            if 1 <= int(start) <= 12 and 1 <= int(end) <= 12
        ]
        if month_ranges:
            return any(
                start <= trip_date.month <= end
                if start <= end
                else trip_date.month >= start or trip_date.month <= end
                for start, end in month_ranges
            )
        return True

    def _is_open_on_trip_day(
        self,
        place: PlaceSummary,
        request: AiPlanGenerationRequest,
        day_index: int,
    ) -> bool:
        trip_date = self._trip_date(request, day_index)
        if trip_date is not None and trip_date.date().isoformat() in place.officialClosedDates:
            return False
        text = place.openingHoursWeek or ""
        if not text or trip_date is None or "周" not in text:
            return True
        day_chars = "一二三四五六日"
        day_char = day_chars[trip_date.weekday()]
        if re.search(rf"周{day_char}[^；;。]*(?:闭馆|闭园|全天关闭|关闭|休息|不开放)", text):
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
        dated = re.search(r"(?<!\d)(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)", request.dateRange)
        short = re.search(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})(?!\d)", request.dateRange)
        try:
            if dated is not None:
                start = datetime(int(dated.group(1)), int(dated.group(2)), int(dated.group(3)))
            elif short is not None:
                start = datetime(datetime.now().year, int(short.group(1)), int(short.group(2)))
            else:
                return None
        except ValueError:
            return None
        return start + timedelta(days=max(0, day_index - 1))

    def _parse_time_ranges(self, value: str | None) -> list[tuple[int, int]]:
        return [(window.start, window.end) for window in self._parse_opening_windows(value)]

    def _parse_opening_windows(self, value: str | None) -> list[TimeWindow]:
        if not value:
            return []
        ranges: list[tuple[int, int]] = []
        time_token = r"(?:[01]?\d|2[0-3]):[0-5]\d|24:00"
        for start, end in re.findall(
            rf"({time_token})\s*[-—至]\s*({time_token})",
            value,
        ):
            start_minutes = self._time_to_minutes(self._normalize_hour(start))
            end_minutes = self._time_to_minutes(self._normalize_hour(end))
            if end_minutes <= start_minutes and end_minutes < 6 * 60:
                end_minutes = 24 * 60
            if end_minutes > start_minutes:
                ranges.append((start_minutes, end_minutes))
        if not ranges and "24小时" in value:
            ranges.append((0, 24 * 60))

        open_time = self._labeled_time(
            value,
            ("开放入馆", "开放入园", "开始入馆", "开始入园", "开馆", "开放时间"),
        )
        last_admission = self._labeled_time(
            value,
            (
                "停止入馆", "停止入园", "停止检票", "停止入场", "停止售票",
                "最晚入馆", "最晚入园", "最晚检票", "最晚入场", "最晚进入", "截止入场",
            ),
        )
        close_time = self._labeled_time(
            value,
            ("闭馆", "闭园", "关闭时间", "结束开放"),
        )
        if not ranges and open_time is not None and (close_time is not None or last_admission is not None):
            effective_end = close_time if close_time is not None else last_admission
            if effective_end is not None and effective_end > open_time:
                ranges.append((open_time, effective_end))

        windows: list[TimeWindow] = []
        for start, end in ranges:
            latest_start = last_admission if last_admission is not None and start <= last_admission <= end else None
            windows.append(TimeWindow(start=start, end=end, latest_start=latest_start))
        return windows

    def _labeled_time(self, value: str, labels: tuple[str, ...]) -> int | None:
        label_pattern = "|".join(re.escape(label) for label in labels)
        time_pattern = r"((?:[01]?\d|2[0-3]):[0-5]\d|24:00)"
        patterns = (
            rf"(?:{label_pattern})\s*[：:]?\s*{time_pattern}",
            rf"{time_pattern}\s*(?:起|后)?\s*(?:{label_pattern})",
        )
        for pattern in patterns:
            matched = re.search(pattern, value)
            if matched is not None:
                return self._time_to_minutes(self._normalize_hour(matched.group(1)))
        return None
    def _normalize_hour(self, value: str) -> str:
        hour, minute = value.split(":", 1)
        return f"{int(hour):02d}:{minute}"

    def _schedule_note(self, place: PlaceSummary, verified: bool, meal_type: str | None = None) -> str:
        hours = place.openingHoursToday or place.openingHoursWeek
        if place.category == "transport":
            return "抵达后预留约 40 分钟用于出站、取行李和换乘。"
        if place.category == "lodging":
            return "先寄存行李或办理入住；实际入住时间以酒店政策为准。"
        if place.category in {"food", "drink"}:
            role_text = {"BREAKFAST": "特色早餐", "LUNCH": "顺路午餐", "DINNER": "特色晚餐"}.get(meal_type, "用餐")
            if verified and hours:
                hours_note = f"高德营业信息：{hours}"
            elif hours:
                hours_note = f"参考营业线索：{hours}，出发前请确认。"
            else:
                hours_note = "营业时间请在详情页确认。"
            return f"{role_text}，兼顾地方特色和前后地点通勤。{hours_note}"
        reservation = (
            f" 需提前预约：{place.officialReservationNote}"
            if place.officialReservationRequired and place.officialReservationNote
            else " 该地点有官方预约要求，请从详情页官方入口确认。"
            if place.officialReservationRequired
            else ""
        )
        closure_warning = (
            f" 官方闭园公告缺少明确生效日期，出发前请复核：{place.officialClosureWarning}"
            if place.officialClosureWarning
            else ""
        )
        access_warning = (
            f" 官方交通或入口提示：{place.officialAccessNote}"
            if place.officialAccessNote
            else ""
        )
        capacity_warning = (
            f" 官方最大日承载量约 {place.officialMaxDailyCapacity} 人次。"
            if place.officialMaxDailyCapacity
            else f" 官方容量提示：{place.officialCapacityNote}"
            if place.officialCapacityNote
            else ""
        )
        ticket_warning = f" 官方票务提示：{place.officialTicketNote}" if place.officialTicketNote else ""
        if verified and hours:
            return (
                f"游览时间已落在可用开放时段内：{hours}{reservation}{closure_warning}"
                f"{access_warning}{capacity_warning}{ticket_warning}"
            )
        if place.category == "scenic" and self._is_evening_public_place(place):
            return (
                f"按夜间公共游览场景安排；灯光、开放区域与结束时间请在出发前复核。"
                f"{reservation}{closure_warning}{access_warning}{capacity_warning}{ticket_warning}"
            )
        if hours:
            return (
                f"按当前开放时间线索安排：{hours}；该时段尚未按出行日期确认，出发前请复核。"
                f"{reservation}{closure_warning}{access_warning}{capacity_warning}{ticket_warning}"
            )
        return (
            f"开放时间数据暂缺，已保守安排在 09:30-17:30；出发前请在详情页确认。"
            f"{reservation}{closure_warning}{access_warning}{capacity_warning}{ticket_warning}"
        )

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
        meal_type = (
            str(ai.get("mealType")).upper()
            if str(ai.get("mealType") or "").upper() in {"BREAKFAST", "LUNCH", "DINNER"}
            else None
        )
        suggested_start, suggested_end, automatically_verified = self._validated_slot(
            place,
            proposed_start,
            proposed_end,
            request,
            meal_type,
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
            officialScenicGrade=place.officialScenicGrade,
            experienceEvidenceCount=place.experienceEvidenceCount,
            officialReservationRequired=place.officialReservationRequired,
            officialReservationNote=place.officialReservationNote,
            officialClosedDates=place.officialClosedDates,
            officialClosureWarning=place.officialClosureWarning,
            officialOpeningHoursByDate=place.officialOpeningHoursByDate,
            officialAccessNote=place.officialAccessNote,
            officialMaxDailyCapacity=place.officialMaxDailyCapacity,
            officialCapacityNote=place.officialCapacityNote,
            officialTicketNote=place.officialTicketNote,
            crowdRisk=place.crowdRisk,
            contentUpdatedAt=place.contentUpdatedAt,
            visitUnitId=place.visitUnitId,
            visitUnitName=place.visitUnitName,
            visitUnitPolicy=place.visitUnitPolicy,
            visitUnitMemberOrder=place.visitUnitMemberOrder,
            visitUnitTransferMinutes=place.visitUnitTransferMinutes,
            visitUnitSourceUrl=place.visitUnitSourceUrl,
            recommendedVisitMinutes=place.recommendedVisitMinutes,
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
                160,
            ),
            mealType=meal_type,
        )

    def _validated_slot(
        self,
        place: PlaceSummary,
        start: str,
        end: str,
        request: AiPlanGenerationRequest,
        meal_type: str | None = None,
    ) -> tuple[str, str, bool]:
        start_minutes = self._time_to_minutes(start)
        end_minutes = self._time_to_minutes(end)
        duration = max(45, end_minutes - start_minutes)
        opening_windows = self._opening_windows(place)
        if opening_windows:
            slot = self._find_open_slot(opening_windows, start_minutes, duration)
            if slot is None:
                slot = self._find_open_slot(opening_windows, 0, duration)
            if slot is not None:
                return self._minutes_to_time(slot[0]), self._minutes_to_time(slot[1]), True
        if place.category == "scenic":
            if self._is_evening_public_place(place) and start_minutes >= 17 * 60 + 30:
                latest_end = min(self._time_to_minutes(request.dailyEnd), 21 * 60 + 30)
                evening_end = min(start_minutes + duration, latest_end)
                if evening_end - start_minutes >= 45:
                    return self._minutes_to_time(start_minutes), self._minutes_to_time(evening_end), False
            conservative_start = max(start_minutes, 9 * 60 + 30)
            conservative_end = min(conservative_start + duration, 17 * 60 + 30)
            if conservative_end - conservative_start < 45:
                conservative_start = 15 * 60 + 45
                conservative_end = 17 * 60 + 15
            return self._minutes_to_time(conservative_start), self._minutes_to_time(conservative_end), False
        if place.category in {"food", "drink"}:
            meal_start = {
                "BREAKFAST": 7 * 60 + 30,
                "LUNCH": 11 * 60 + 30,
                "DINNER": 17 * 60 + 30,
            }.get(meal_type, 11 * 60 + 30 if start_minutes < 15 * 60 else 17 * 60 + 30)
            meal_start = max(meal_start, start_minutes)
            meal_end = min(meal_start + duration, self._time_to_minutes(request.dailyEnd))
            return self._minutes_to_time(meal_start), self._minutes_to_time(meal_end), False
        return start, end, False

    def _slot_is_within_opening_hours(self, place: PlaceSummary, start: str, end: str) -> bool:
        windows = self._opening_windows(place)
        if not windows:
            return False
        return self._slot_within_open_window(
            windows,
            self._time_to_minutes(start),
            self._time_to_minutes(end),
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
        scenic = [place for place in places if place.category == "scenic"]
        unit_count = len(
            {
                place.visitUnitId
                if place.visitUnitPolicy == "BUNDLE" and place.visitUnitId
                else place.sourcePoiId
                for place in scenic
            },
        )
        visit_minutes = sum(
            max(
                0,
                self._time_to_minutes(place.suggestedEnd)
                - self._time_to_minutes(place.suggestedStart),
            )
            for place in scenic
        )
        if unit_count >= 4 or visit_minutes >= 330:
            return "充实"
        if unit_count >= 2 or visit_minutes >= 180:
            return "适中"
        return "轻松"

    def _evaluate_plan_quality(
        self,
        request: AiPlanGenerationRequest,
        days: list[AiGeneratedDay],
        used_fallback: bool,
        data_sources: list[str],
    ) -> AiPlanQuality:
        transfers = [transfer for day in days for transfer in day.transfers]
        total_commute = sum(transfer.durationMinutes for transfer in transfers)
        longest_leg = max((transfer.durationMinutes for transfer in transfers), default=0)
        walking_meters = sum(
            transfer.distanceMeters for transfer in transfers if transfer.mode == "walking"
        )
        cross_region = 0
        backtracking = 0
        long_idle = 0
        meal_deviation = 0
        closing_margins: list[int] = []
        profile = PACE_PROFILES[request.pace]
        max_idle = profile.max_idle_minutes
        daily_loads = [self._day_scenic_load(request, day) for day in days]
        underfilled = [
            (day.dayIndex, reason)
            for day in days
            if (reason := self._underfilled_day_reason(request, day)) is not None
        ]

        for day in days:
            transfer_by_pair = {
                (item.originPlaceId, item.destinationPlaceId): item for item in day.transfers
            }
            for previous, current in zip(day.places, day.places[1:]):
                transfer = transfer_by_pair.get((previous.id, current.id))
                if transfer is None:
                    continue
                if (
                    previous.districtName
                    and current.districtName
                    and previous.districtName != current.districtName
                    and transfer.durationMinutes >= 25
                ):
                    cross_region += 1
                idle = (
                    self._time_to_minutes(current.suggestedStart)
                    - self._time_to_minutes(previous.suggestedEnd)
                    - transfer.durationMinutes
                    - self._exit_buffer_minutes(self._generated_to_summary(previous))
                    - self._entry_buffer_minutes(self._generated_to_summary(current))
                )
                if idle > max_idle:
                    long_idle += 1

            for left, middle, right in zip(day.places, day.places[1:], day.places[2:]):
                via = self._distance_coordinates(
                    left.latitude, left.longitude, middle.latitude, middle.longitude,
                ) + self._distance_coordinates(
                    middle.latitude, middle.longitude, right.latitude, right.longitude,
                )
                direct = self._distance_coordinates(
                    left.latitude, left.longitude, right.latitude, right.longitude,
                )
                if via > max(5.0, direct * 1.75) and via - direct > 3.0:
                    backtracking += 1

            for place in day.places:
                start = self._time_to_minutes(place.suggestedStart)
                end = self._time_to_minutes(place.suggestedEnd)
                meal_window = {
                    "BREAKFAST": (7 * 60 + 30, 11 * 60),
                    "LUNCH": (11 * 60 + 30, 14 * 60),
                    "DINNER": (17 * 60 + 30, 21 * 60),
                }.get(place.mealType)
                if meal_window is not None and not (meal_window[0] <= start < end <= meal_window[1]):
                    meal_deviation += 1
                if place.category == "scenic" and place.scheduleVerified:
                    windows = self._opening_windows_for_day(
                        self._generated_to_summary(place), request, day.dayIndex,
                    )
                    matching = [window for window in windows if window.start <= start and end <= window.end]
                    if matching:
                        closing_margins.append(min(window.end - end for window in matching))

        required = self._named_constraint_queries(request, required=True)
        missing = self._missing_required_place_queries(request, days)
        required_coverage = 1.0 if not required else (len(required) - len(missing)) / len(required)
        max_leg = profile.max_normal_leg_minutes
        comfort_penalty = (
            max(0, longest_leg - max_leg) * 0.45
            + cross_region * 5
            + backtracking * 7
            + long_idle * 4
            + meal_deviation * 8
            + max(0.0, walking_meters / 1000 - {"RELAXED": 5.0, "BALANCED": 8.0, "INTENSIVE": 12.0}[request.pace]) * 2
        )
        all_places = [place for day in days for place in day.places]
        return AiPlanQuality(
            realPoiRatio=1.0,
            duplicatePlaceCount=len(all_places) - len({place.sourcePoiId for place in all_places}),
            totalPlaceCount=len(all_places),
            usedFallback=used_fallback,
            dataSources=list(data_sources),
            totalCommuteMinutes=total_commute,
            longestLegMinutes=longest_leg,
            crossRegionTransferCount=cross_region,
            backtrackingLegCount=backtracking,
            longIdleGapCount=long_idle,
            estimatedWalkingKm=round(walking_meters / 1000, 1),
            mealWindowDeviationCount=meal_deviation,
            minimumClosingMarginMinutes=min(closing_margins) if closing_margins else None,
            requiredPlaceCoverage=round(required_coverage, 3),
            comfortScore=max(0, min(100, round(100 - comfort_penalty))),
            mainVisitUnitCountByDay=[load[0] for load in daily_loads],
            scheduledVisitMinutesByDay=[load[1] for load in daily_loads],
            occupancyRatioByDay=[load[2] for load in daily_loads],
            underfilledDayIndexes=[day_index for day_index, _ in underfilled],
            underfilledReasons=[f"第{day_index}天：{reason}" for day_index, reason in underfilled],
        )

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
