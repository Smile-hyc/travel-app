from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.schemas.ai import (
    AiChatRequest,
    AiChatResponse,
    AiPlanContext,
    AiSuggestedAction,
)
from app.services.ark_client import ArkClient


class TravelAiService:
    def __init__(self, ark_client: ArkClient):
        self._ark_client = ark_client

    async def chat(self, request: AiChatRequest) -> AiChatResponse:
        conversation_id = request.conversationId or str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        context_text = self._format_plan_context(request.context)

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
        ]
        if context_text:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "当前旅行计划上下文如下。请只基于这些信息回答；"
                        "缺少的数据要明确说暂无，不要编造。\n"
                        f"{context_text}"
                    ),
                },
            )

        for item in request.history[-4:]:
            messages.append(
                {
                    "role": item.role,
                    "content": item.content[:500],
                },
            )

        messages.append({"role": "user", "content": request.message.strip()[:800]})

        raw_reply = await self._ark_client.chat(messages)
        parsed_reply, raw_actions, parse_warnings = self._parse_ai_reply(raw_reply)
        actions, validation_warnings = self._validate_actions(raw_actions, request.context)
        visible_reply = parsed_reply or raw_reply

        return AiChatResponse(
            conversationId=conversation_id,
            messageId=message_id,
            message=visible_reply,
            quickReplies=self._build_quick_replies(request.context),
            referencedPlaceItemIds=self._find_referenced_places(visible_reply, request.context),
            actionSetId=str(uuid.uuid4()) if actions else None,
            planRevision=request.context.revision if request.context else None,
            suggestedActions=actions,
            actionWarnings=parse_warnings + validation_warnings,
            createdAt=datetime.now(timezone.utc).isoformat(),
            model=self._ark_client.model_name,
        )

    def _system_prompt(self) -> str:
        return (
            "你是 AI 旅行助手。请用自然、具体、中文友好的方式回答，语气温和。"
            "普通问题尽量简洁；涉及行程调整、路线分析和计划建议时可以适当详细，但不要写成超长文章。"
            "你可以分析行程节奏、路线安排、天气提醒、待规划地点放入哪一天、顺序调整建议和行程总结。"
            "你不能直接修改计划，不能声称已经添加、删除、移动或应用优化。"
            "如果缺少路线、天气、营业时间、价格等真实数据，必须说明当前暂无可用数据，不能编造。"
            "回答要优先引用用户计划中的真实地点名称。"
            "只有当用户明确要求调整、安排、优化、放入某天、重新排序时，才可以在中文回复末尾追加一个 JSON 代码块。"
            "JSON 格式必须是："
            "{\"actions\":[{\"type\":\"MOVE_PLACE_TO_DAY|REORDER_PLACE|ASSIGN_UNPLANNED_PLACE|MOVE_TO_UNPLANNED\","
            "\"placeItemId\":\"计划上下文中的 itemId\",\"toDayIndex\":1,\"toPosition\":1,\"reason\":\"原因\"}]}"
            "不要使用不存在的地点 ID，不要创建新地点，不要删除地点。"
            "如果只是普通问答或总结，不要输出 actions。"
        )

    def _parse_ai_reply(self, raw_reply: str) -> tuple[str, list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        json_text = self._extract_json_object(raw_reply)
        if not json_text:
            return raw_reply.strip(), [], []

        visible_reply = raw_reply.replace(json_text, "").strip()
        visible_reply = re.sub(r"```(?:json)?\s*```", "", visible_reply, flags=re.IGNORECASE).strip()

        try:
            data = json.loads(json_text.strip().strip("`"))
        except json.JSONDecodeError:
            warnings.append("AI 返回了结构化建议，但 JSON 解析失败，已降级为普通回复。")
            return raw_reply.strip(), [], warnings

        actions = data.get("actions", [])
        if not isinstance(actions, list):
            warnings.append("AI 建议动作格式不是列表，已忽略。")
            actions = []

        return visible_reply or raw_reply.strip(), [a for a in actions if isinstance(a, dict)], warnings

    def _extract_json_object(self, text: str) -> str | None:
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced.group(1)
        generic_fenced = re.search(r"```\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if generic_fenced:
            return generic_fenced.group(1)
        marker_index = text.find('"actions"')
        if marker_index == -1:
            return None
        start = text.rfind("{", 0, marker_index)
        if start == -1:
            return None
        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None

    def _validate_actions(
        self,
        raw_actions: list[dict[str, Any]],
        context: AiPlanContext | None,
    ) -> tuple[list[AiSuggestedAction], list[str]]:
        if not raw_actions or context is None:
            return [], []

        warnings: list[str] = []
        valid_actions: list[AiSuggestedAction] = []
        day_indexes = {day.dayIndex for day in context.days}
        places: dict[str, tuple[int | None, int | None]] = {}
        unplanned_ids = {place.itemId for place in context.unplannedPlaces}

        for day in context.days:
            for place in day.places:
                places[place.itemId] = (day.dayIndex, place.visitOrder)
        for place in context.unplannedPlaces:
            places[place.itemId] = (None, place.visitOrder)

        touched_places: set[str] = set()
        for index, raw in enumerate(raw_actions[:6], start=1):
            raw = dict(raw)
            raw.setdefault("id", f"ai-action-{index}")
            raw.setdefault("requiresRouteRefresh", True)

            place_id = str(raw.get("placeItemId") or "").strip()
            action_type = str(raw.get("type") or "").strip()
            if not place_id or place_id not in places:
                warnings.append(f"已忽略无效建议：地点 {place_id or '未知'} 不在当前计划中。")
                continue
            if place_id in touched_places:
                warnings.append(f"已忽略重复建议：{place_id} 在同一轮中被多次修改。")
                continue

            current_day, current_position = places[place_id]
            raw.setdefault("fromDayIndex", current_day)
            raw.setdefault("fromPosition", current_position)

            affected_days: set[int] = set()
            if current_day is not None:
                affected_days.add(current_day)

            if action_type in {"MOVE_PLACE_TO_DAY", "ASSIGN_UNPLANNED_PLACE", "REORDER_PLACE"}:
                to_day = self._safe_int(raw.get("toDayIndex"))
                if to_day not in day_indexes:
                    warnings.append(f"已忽略无效建议：目标 DAY {to_day} 不存在。")
                    continue
                raw["toDayIndex"] = to_day
                affected_days.add(to_day)
                if action_type == "ASSIGN_UNPLANNED_PLACE" and place_id not in unplanned_ids:
                    warnings.append(f"已忽略无效建议：{place_id} 不是待规划地点。")
                    continue
                if action_type == "REORDER_PLACE" and current_day != to_day:
                    raw["type"] = "MOVE_PLACE_TO_DAY"
            elif action_type == "MOVE_TO_UNPLANNED":
                raw["toDayIndex"] = None
            else:
                warnings.append(f"已忽略不支持的建议类型：{action_type or '未知'}。")
                continue

            raw["toPosition"] = max(1, self._safe_int(raw.get("toPosition")) or 1)
            raw["affectedDayIndexes"] = sorted(affected_days)

            try:
                action = AiSuggestedAction.model_validate(raw)
            except ValidationError:
                warnings.append(f"已忽略格式不完整的建议：{place_id}。")
                continue

            valid_actions.append(action)
            touched_places.add(place_id)

        return valid_actions, warnings

    def _safe_int(self, value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _format_plan_context(self, context: AiPlanContext | None) -> str:
        if context is None:
            return "当前没有绑定具体旅行计划。"

        lines: list[str] = [
            f"计划 ID：{context.id or '未知'}",
            f"计划版本：{context.revision if context.revision is not None else '未知'}",
            f"计划：{context.title or '未命名计划'}",
            f"目的地：{context.destination or '未知'}",
            f"日期：{context.dateRange or '未设置'}",
        ]
        if context.weather and context.weather.text:
            lines.append(f"天气：{context.weather.text}（{context.weather.reportTime or '无报告时间'}）")
        else:
            lines.append("天气：当前暂无可用数据")

        if context.routeSummaries:
            lines.append("路线摘要：")
            for route in context.routeSummaries[:4]:
                distance = (
                    f"{route.totalDistanceMeters}米"
                    if route.totalDistanceMeters is not None
                    else "暂无距离"
                )
                duration = (
                    f"{route.totalDurationSeconds // 60}分钟"
                    if route.totalDurationSeconds is not None
                    else "暂无耗时"
                )
                lines.append(
                    f"- DAY {route.dayIndex}：{route.placeCount}个地点，{route.mode or '未知方式'}，{distance}，{duration}"
                )
        else:
            lines.append("路线摘要：当前暂无可用数据")

        lines.append("每日地点：")
        for day in context.days[:5]:
            lines.append(f"- {day.title or f'DAY {day.dayIndex}'}")
            if not day.places:
                lines.append("  - 暂无地点")
            for place in day.places[:8]:
                parts = [
                    f"itemId={place.itemId}",
                    f"{place.visitOrder or '?'}.{place.name}",
                    place.category or place.typeName or "未分类",
                    place.address or "暂无地址",
                ]
                if place.suggestedStart or place.suggestedEnd:
                    parts.append(f"{place.suggestedStart or '?'}-{place.suggestedEnd or '?'}")
                lines.append("  - " + "；".join(parts))

        if context.unplannedPlaces:
            lines.append("待规划地点：")
            for place in context.unplannedPlaces[:8]:
                lines.append(
                    f"- itemId={place.itemId}；{place.name}；{place.category or place.typeName or '未分类'}；{place.address or '暂无地址'}"
                )

        return "\n".join(lines)[:6000]

    def _build_quick_replies(self, context: AiPlanContext | None) -> list[str]:
        if context is None:
            return ["推荐一个周末旅行目的地", "帮我做旅行准备清单", "怎么规划一天行程"]

        return [
            "帮我看看 DAY 1 会不会太赶",
            "待规划地点应该放到哪一天",
            "帮我优化一下当天顺序",
            "根据天气给我提醒",
        ]

    def _find_referenced_places(self, reply: str, context: AiPlanContext | None) -> list[str]:
        if context is None:
            return []
        referenced: list[str] = []
        for day in context.days:
            for place in day.places:
                if place.name and place.name in reply:
                    referenced.append(place.itemId)
        for place in context.unplannedPlaces:
            if place.name and place.name in reply:
                referenced.append(place.itemId)
        return list(dict.fromkeys(referenced))
