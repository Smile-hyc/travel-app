from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, unquote

from pydantic import ValidationError

from app.schemas.ai import (
    AiCard,
    AiCardDay,
    AiCardPlaceRef,
    AiChatRequest,
    AiChatResponse,
    AiHistoryMessage,
    AiItineraryCard,
    AiLinkCard,
    AiPlanContext,
    AiRecommendedPlace,
    AiSuggestedAction,
)
from app.schemas.explore import PlaceSummary
from app.services.amap_poi_service import AmapPoiService
from app.services.deepseek_client import DeepSeekClient


class TravelAiService:
    def __init__(self, model_client: DeepSeekClient, poi_service: AmapPoiService | None = None):
        self._model_client = model_client
        self._poi_service = poi_service

    def _build_messages(
        self,
        request: AiChatRequest,
        retrieved_places: list[PlaceSummary] | None = None,
        retrieval_city: str | None = None,
    ) -> list[dict[str, str]]:
        context_text = self._format_plan_context(request.context)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt()},
        ]
        if request.planContexts:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "以下是用户计划页面中的全部旅行计划和每日行程。"
                        "你必须把这些内容作为每轮对话的长期计划记忆。"
                        "用户询问今天时，使用 todayDayIndex 不为空的计划；"
                        "用户询问某个目的地、日期或计划名称时，从全部计划中匹配，不能声称没有绑定计划。"
                        f"当前用于调整操作的计划 ID：{request.planId or '无'}。\n"
                        f"{self._format_all_plan_contexts(request.planContexts)}"
                    ),
                },
            )
        elif context_text:
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
        if retrieved_places:
            place_lines = []
            for place in retrieved_places:
                place_lines.append(
                    " | ".join(
                        filter(
                            None,
                            [
                                f"id={place.id}",
                                f"name={place.name}",
                                f"category={place.typeName or place.category}",
                                f"address={place.address or '暂无'}",
                                f"district={place.districtName or '暂无'}",
                                f"rating={place.rating or '暂无'}",
                                f"cost={place.costAverage or '暂无'}",
                            ],
                        ),
                    ),
                )
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"以下是刚刚从高德地图检索到的{retrieval_city or ''}真实地点。"
                        "回答涉及具体店铺或景点时，只能推荐这份列表里的地点，不得编造店名。"
                        "凡是在正文中提到列表里的地点，必须使用 Markdown 内部链接格式："
                        "[地点名称](aitravel://place/地点id)。"
                        "先回答用户真正问的知识或建议，再自然推荐 3 至 6 个最匹配地点；"
                        "不用在正文重复卡片里的全部地址和评分。\n"
                        + "\n".join(place_lines)
                    ),
                },
            )
        for item in request.history[-4:]:
            messages.append({"role": item.role, "content": item.content[:500]})
        messages.append({"role": "user", "content": request.message.strip()[:800]})
        return messages

    def _format_all_plan_contexts(self, contexts: list[AiPlanContext]) -> str:
        sections: list[str] = []
        for index, context in enumerate(contexts, start=1):
            sections.append(
                f"===== 计划页计划 {index}/{len(contexts)} =====\n"
                f"{self._format_plan_context(context)}"
            )
        return "\n".join(sections)

    async def chat_stream(self, request: AiChatRequest) -> AsyncGenerator[str, None]:
        """流式对话：逐 chunk yield SSE 事件字符串。"""
        conversation_id = request.conversationId or str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        retrieved_places, retrieval_city = await self._retrieve_places(request.message, request.history)
        messages = self._build_messages(request, retrieved_places, retrieval_city)

        full_text = ""
        async for chunk in self._model_client.chat_stream_chunks(messages):
            full_text += chunk
            yield json.dumps({"type": "chunk", "content": chunk}, ensure_ascii=False)

        parsed_reply, raw_actions, raw_cards, parse_warnings = self._parse_ai_reply(full_text)
        actions, validation_warnings = self._validate_actions(raw_actions, request.context)
        cards, card_warnings = self._validate_cards(raw_cards, request.context, actions)
        visible_reply = self._linkify_places(
            parsed_reply or full_text,
            retrieved_places,
            request.planContexts,
        )
        all_warnings = parse_warnings + validation_warnings + card_warnings
        recommended_places = self._to_recommended_places(retrieved_places)

        done_payload = {
            "type": "done",
            "fullText": visible_reply,
            "conversationId": conversation_id,
            "messageId": message_id,
            "quickReplies": self._build_quick_replies(request.context, retrieval_city, recommended_places),
            "referencedPlaceItemIds": self._find_referenced_places(visible_reply, request.context),
            "actionSetId": str(uuid.uuid4()) if actions else None,
            "planRevision": request.context.revision if request.context else None,
            "suggestedActions": [a.model_dump(mode="json") for a in actions],
            "actionWarnings": all_warnings,
            "cards": [c.model_dump(mode="json") for c in cards],
            "recommendedPlaces": [place.model_dump(mode="json") for place in recommended_places],
            "retrievalCity": retrieval_city,
            "offerPlan": bool(recommended_places) and request.context is None,
            "dataSources": ["DEEPSEEK"] + (["AMAP"] if recommended_places else []),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "model": self._model_client.model_name,
        }
        yield json.dumps(done_payload, ensure_ascii=False)

    async def chat(self, request: AiChatRequest) -> AiChatResponse:
        conversation_id = request.conversationId or str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        retrieved_places, retrieval_city = await self._retrieve_places(request.message, request.history)
        messages = self._build_messages(request, retrieved_places, retrieval_city)
        raw_reply = await self._model_client.chat(messages)
        parsed_reply, raw_actions, raw_cards, parse_warnings = self._parse_ai_reply(raw_reply)
        actions, validation_warnings = self._validate_actions(raw_actions, request.context)
        cards, card_warnings = self._validate_cards(raw_cards, request.context, actions)
        visible_reply = self._linkify_places(
            parsed_reply or raw_reply,
            retrieved_places,
            request.planContexts,
        )
        recommended_places = self._to_recommended_places(retrieved_places)

        return AiChatResponse(
            conversationId=conversation_id,
            messageId=message_id,
            message=visible_reply,
            quickReplies=self._build_quick_replies(request.context, retrieval_city, recommended_places),
            referencedPlaceItemIds=self._find_referenced_places(visible_reply, request.context),
            actionSetId=str(uuid.uuid4()) if actions else None,
            planRevision=request.context.revision if request.context else None,
            suggestedActions=actions,
            actionWarnings=parse_warnings + validation_warnings + card_warnings,
            cards=cards,
            recommendedPlaces=recommended_places,
            retrievalCity=retrieval_city,
            offerPlan=bool(recommended_places) and request.context is None,
            dataSources=["DEEPSEEK"] + (["AMAP"] if recommended_places else []),
            createdAt=datetime.now(timezone.utc).isoformat(),
            model=self._model_client.model_name,
        )

    async def _retrieve_places(
        self,
        message: str,
        history: list[AiHistoryMessage] | None = None,
    ) -> tuple[list[PlaceSummary], str | None]:
        if self._poi_service is None:
            return [], None
        planner_messages = [
            {
                "role": "system",
                "content": (
                    "你是旅行检索规划器。判断用户问题是否需要查询中国境内真实店铺、景点、酒店、购物或饮品地点。"
                    "只要用户询问具体目的地的玩法、推荐，或者要求生成某地行程，都应 search=true；"
                    "行李清单、通用知识等不涉及具体地点的问题才 search=false。"
                    "只输出一个 JSON 对象，不要解释："
                    '{"search":true,"city":"天津","queries":'
                    '[{"category":"scenic","keyword":"天津经典景点"},'
                    '{"category":"food","keyword":"天津特色美食"}]}。'
                    "category 只能是 scenic、food、drink、shopping、lodging、transport；"
                    "普通单类问题给 1 至 3 个 queries，多日游同时给 scenic 和 food，最多 4 个；"
                    "keyword 必须适合高德地图检索。如果不需要地点检索，search=false。"
                ),
            },
            {
                "role": "user",
                "content": self._retrieval_conversation_text(message, history or []),
            },
        ]
        try:
            raw_plan = await self._model_client.chat(
                planner_messages,
                max_tokens=280,
                temperature=0.05,
                timeout_seconds=30,
            )
            match = re.search(r"\{.*\}", raw_plan, flags=re.DOTALL)
            plan = json.loads(match.group(0) if match else raw_plan)
            if not plan.get("search"):
                return [], None
            city = str(plan.get("city") or "").strip()[:30]
            allowed_categories = {"scenic", "food", "drink", "shopping", "lodging", "transport"}
            queries: list[tuple[str, str]] = []
            raw_queries = plan.get("queries")
            if isinstance(raw_queries, list):
                for raw_query in raw_queries[:4]:
                    if not isinstance(raw_query, dict):
                        continue
                    category = str(raw_query.get("category") or "scenic").strip()
                    if category not in allowed_categories:
                        category = "scenic"
                    keyword = str(raw_query.get("keyword") or "").strip()[:40]
                    if keyword:
                        queries.append((category, keyword))
            else:
                # Backward-compatible with the original single-category protocol.
                category = str(plan.get("category") or "scenic").strip()
                if category not in allowed_categories:
                    category = "scenic"
                queries.extend(
                    (category, str(value).strip()[:40])
                    for value in (plan.get("keywords") or [])[:3]
                    if str(value).strip()
                )
            if not city or not queries:
                return [], None
            city_results = await self._poi_service.search_cities(keyword=city, limit=3)
            if not city_results:
                return [], city
            city_result = city_results[0]
            collected: list[PlaceSummary] = []
            seen: set[str] = set()
            for category, keyword in queries:
                page = await self._poi_service.search_pois(
                    keyword=keyword,
                    adcode=city_result.adCode,
                    category=category,
                    page=1,
                    page_size=6,
                    city_limit=True,
                )
                for place in page.items:
                    if place.id in seen:
                        continue
                    seen.add(place.id)
                    collected.append(place)
            collected.sort(
                key=lambda place: (
                    0 if place.coverImageUrl else 1,
                    -self._safe_float(place.rating),
                ),
            )
            return collected[:6], city_result.name
        except Exception:
            return [], None

    def _retrieval_conversation_text(
        self,
        message: str,
        history: list[AiHistoryMessage],
    ) -> str:
        context_lines = [
            f"{item.role}: {item.content[:220]}"
            for item in history[-4:]
        ]
        context_lines.append(f"current_user: {message[:500]}")
        return (
            "请结合最近对话判断当前问题中的省略城市、商圈和地点指代。\n"
            + "\n".join(context_lines)
        )[:1400]

    def _linkify_places(
        self,
        reply: str,
        places: list[PlaceSummary],
        plan_contexts: list[AiPlanContext] | None = None,
    ) -> str:
        # Models sometimes wrap a complete Markdown link in **bold**. That
        # creates overlapping spans in lightweight mobile Markdown renderers
        # and can expose both the raw URL and a duplicate blue label. Internal
        # place links own their visual emphasis, so remove the outer wrapper.
        linked = re.sub(
            r"\*\*([^\n]*?\[[^\]\n]+\]\(aitravel://place/[^)\s]+\)[^\n]*?)\*\*",
            r"\1",
            reply,
        )
        linked = re.sub(
            r"__([^\n]*?\[[^\]\n]+\]\(aitravel://place/[^)\s]+\)[^\n]*?)__",
            r"\1",
            linked,
        )
        link_targets: list[tuple[str, str]] = [
            (place.name, place.id) for place in places if place.name and place.id
        ]
        for context in plan_contexts or []:
            for day in context.days:
                link_targets.extend(
                    (place.name, place.itemId)
                    for place in day.places
                    if place.name and place.itemId
                )
            link_targets.extend(
                (place.name, place.itemId)
                for place in context.unplannedPlaces
                if place.name and place.itemId
            )
        link_targets = list(dict.fromkeys(link_targets))
        allowed_place_ids = {place_id for _, place_id in link_targets}

        internal_link_pattern = re.compile(
            r"\[([^\]\n]+)\]\(aitravel://place/([^)\s]+)\)"
        )
        linked = internal_link_pattern.sub(
            lambda match: (
                match.group(0)
                if unquote(match.group(2)) in allowed_place_ids
                else match.group(1)
            ),
            linked,
        )

        for place_name, place_id in sorted(link_targets, key=lambda value: len(value[0]), reverse=True):
            if place_name not in linked:
                continue
            internal_url = f"aitravel://place/{quote(place_id, safe=':')}"
            markdown = f"[{place_name}]({internal_url})"
            if markdown in linked:
                continue
            # DeepSeek often bolds landmark names. Remove the outer emphasis so
            # Android's lightweight Markdown renderer sees one unambiguous link.
            linked = linked.replace(f"**{place_name}**", markdown)
            linked = linked.replace(f"__{place_name}__", markdown)
            if markdown in linked:
                pass
            else:
                linked = linked.replace(place_name, markdown)

            # Keep a single clickable label when the model emits the same
            # place as adjacent plain text and Markdown, or repeats the link.
            escaped_name = re.escape(place_name)
            escaped_markdown = re.escape(markdown)
            linked = re.sub(
                rf"(?:{escaped_name}\s*)?{escaped_markdown}(?:\s*{escaped_name})?",
                markdown,
                linked,
            )
            linked = re.sub(
                rf"{escaped_markdown}(?:\s*{escaped_markdown})+",
                markdown,
                linked,
            )
        return self._dedupe_internal_place_links(linked)

    def _dedupe_internal_place_links(self, reply: str) -> str:
        link_pattern = re.compile(
            r"\[([^\]\n]+)\]\((aitravel://place/[^)\s]+)\)"
        )
        normalized_lines: list[str] = []
        for line in reply.split("\n"):
            unique_links = list(dict.fromkeys(match.group(0) for match in link_pattern.finditer(line)))
            if not unique_links:
                normalized_lines.append(line)
                continue

            normalized = line
            link_details: list[tuple[str, str, str, str]] = []
            for index, markdown in enumerate(unique_links):
                match = link_pattern.fullmatch(markdown)
                if match is None:
                    continue
                label, url = match.groups()
                token = f"\ue000PLACE_LINK_{index}\ue001"
                normalized = normalized.replace(markdown, token)
                link_details.append((markdown, label, url, token))

            for _, label, url, token in link_details:
                normalized = normalized.replace(f"**{label}**", "")
                normalized = normalized.replace(f"__{label}__", "")
                normalized = normalized.replace(label, "")
                normalized = re.sub(rf"\(?{re.escape(url)}\)?", "", normalized)
                first_token = normalized.find(token)
                if first_token >= 0:
                    after_first = first_token + len(token)
                    normalized = (
                        normalized[:after_first]
                        + normalized[after_first:].replace(token, "")
                    )

            for markdown, _, _, token in link_details:
                normalized = normalized.replace(token, markdown)
            normalized_lines.append(normalized.strip())

        return "\n".join(normalized_lines)

    def _to_recommended_places(self, places: list[PlaceSummary]) -> list[AiRecommendedPlace]:
        recommendations: list[AiRecommendedPlace] = []
        for place in places[:6]:
            description_parts = [place.typeName or "高德真实地点"]
            if place.businessArea:
                description_parts.append(f"位于{place.businessArea}")
            elif place.districtName:
                description_parts.append(f"位于{place.districtName}")
            if place.rating:
                description_parts.append(f"高德评分 {place.rating}")
            recommendations.append(
                AiRecommendedPlace(
                    **place.model_dump(),
                    description="，".join(description_parts) + "。",
                ),
            )
        return recommendations

    def _safe_float(self, value: str | None) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _system_prompt(self) -> str:
        return (
            "你是一个旅行领域的专业聊天顾问，产品名称是 AI 旅行助手。"
            "你的核心职责是通过自然对话解决各种旅行问题，而不是代替智能规划 Agent。"
            "你尤其擅长目的地选择、本地美食与文化、景点取舍、交通衔接、住宿区域、预算、季节天气、"
            "行前准备、安全注意事项、签证常识以及已有行程的解释和优化。"
            "始终紧密围绕旅行场景展开。对于明显与旅行无关的问题，简短说明你专注于旅行，并主动给出一个可继续咨询的旅行方向；"
            "但如果通用问题与一次具体旅行有关，例如摄影、穿搭、健康准备、亲子需求或语言沟通，应结合旅行场景正常回答。"
            "回答应自然、具体、中文友好，优先给出可执行建议；普通问题尽量简洁，复杂问题用清晰的小标题或列表。"
            "信息不足且会显著影响答案时，只追问一个最关键的问题，不要一次抛出很多表单问题。"
            "涉及实时价格、营业时间、天气、交通班次、签证法规或安全政策时，要说明信息可能变化并建议用户再次核实。"
            "严禁编造不存在的地点、营业时间、价格、路线、政策或用户未提供的个人信息。"
            "智能规划是另一项专用能力：它负责收集日期、节奏等条件，并自动生成可保存、可编辑的完整旅行计划。"
            "当用户明确要求制定或生成完整旅行计划/多日行程时，不要在聊天回复里自行编造一份完整日程；"
            "应简短说明将交给智能规划，并输出 LINK 卡片，让前端展示日期和旅行节奏选择。"
            "当用户只是问美食、景点、交通、住宿、天气、预算、文化或准备清单时，直接回答，绝不要求先选日期和节奏。"
            "如果用户已经绑定一个计划，你可以分析行程节奏、路线安排、天气提醒、待规划地点放入哪一天、"
            "顺序调整建议和行程总结，但任何修改都必须由用户确认。"
            "你不能直接修改计划，不能声称已经添加、删除、移动或应用优化。"
            "如果缺少路线、天气、营业时间、价格等真实数据，必须说明当前暂无可用数据，不能编造。"
            "回答要优先引用用户计划中的真实地点名称。"
            "只有在用户已绑定计划，并明确要求调整、安排、优化或重新排序该计划时，才在中文回复末尾追加 JSON 代码块。"
            "只有在已绑定计划的调整对话中，用户说「好的」「同意」「可以」「执行」「确认」等确认词时，"
            "才输出包含 actions 和 cards 的 JSON 代码块。普通旅行问答绝不输出 actions。"
            "JSON 必须严格用 ```json 包裹，示例：\n"
            "```json\n"
            "{\"actions\":[{\"type\":\"MOVE_PLACE_TO_DAY\",\"placeItemId\":\"计划中的itemId\",\"toDayIndex\":1,\"toPosition\":1,\"reason\":\"原因\"}],"
            "\"cards\":[{\"id\":\"card-itin\",\"type\":\"ITINERARY_OPTIMIZATION\",\"title\":\"优化后的行程\","
            "\"days\":[{\"day_index\":1,\"title\":\"优化后 DAY 1\",\"place_refs\":[{\"itemId\":\"上下文中的itemId\",\"note\":\"建议上午先去\"}]}]}]}\n"
            "```\n"
            "必须使用上下文中已有的真实 itemId 和 dayIndex，绝不允许编造地点 ID。"
            "注意：dayIndex 从 1 开始计数（DAY 1 = 1，不是 0）。toDayIndex 最小值是 1。"
            "普通问答或总结不要输出 JSON。\n"
            "\n"
            "## 卡片类型补充\n"
            "### LINK 卡片（用户无绑定计划时要求创建旅行）\n"
            "只有用户明确要求制定、生成或安排完整旅行计划/多日行程时才能输出 LINK 卡片。"
            "如果用户只是咨询某地美食、景点、交通、天气、准备清单或其他普通问题，禁止输出 LINK 卡片，直接正常回答。\n"
            "{\"cards\":[{\"id\":\"card-link\",\"type\":\"LINK\",\"title\":\"创建旅行计划\",\"subtitle\":\"引导文案\",\"payload\":{\"action_type\":\"NAVIGATE_TO_CREATE_PLAN\"}}]}\n"
            "### ITINERARY 卡片（用户确认优化后必须输出，需同时输出对应的 actions）"
        )

    def _parse_ai_reply(self, raw_reply: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        json_text = self._extract_json_object(raw_reply)
        if not json_text:
            return raw_reply.strip(), [], [], []

        visible_reply = raw_reply.replace(json_text, "").strip()
        visible_reply = re.sub(r"```(?:json)?\s*```", "", visible_reply, flags=re.IGNORECASE).strip()

        try:
            data = json.loads(json_text.strip().strip("`"))
        except json.JSONDecodeError:
            warnings.append("AI 返回了结构化建议，但 JSON 解析失败，已降级为普通回复。")
            return raw_reply.strip(), [], [], warnings

        actions = data.get("actions", [])
        if not isinstance(actions, list):
            warnings.append("AI 建议动作格式不是列表，已忽略。")
            actions = []

        raw_cards = data.get("cards", [])
        if not isinstance(raw_cards, list):
            warnings.append("AI 卡片格式不是列表，已忽略。")
            raw_cards = []
        raw_cards = [c for c in raw_cards if isinstance(c, dict)]

        return visible_reply or raw_reply.strip(), [a for a in actions if isinstance(a, dict)], raw_cards, warnings

    def _extract_json_object(self, text: str) -> str | None:
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced.group(1)
        generic_fenced = re.search(r"```\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if generic_fenced:
            return generic_fenced.group(1)
        marker_index = text.find('"actions"')
        if marker_index == -1:
            marker_index = text.find('"cards"')
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

    def _validate_cards(
        self,
        raw_cards: list[dict[str, Any]],
        context: AiPlanContext | None,
        actions: list[AiSuggestedAction],
    ) -> tuple[list[AiCard], list[str]]:
        if not raw_cards:
            return [], []

        warnings: list[str] = []
        valid_cards: list[AiCard] = []

        valid_place_ids: set[str] = set()
        if context:
            for day in context.days:
                for place in day.places:
                    valid_place_ids.add(place.itemId)
            for place in context.unplannedPlaces:
                valid_place_ids.add(place.itemId)

        for raw in raw_cards[:2]:
            card_type = str(raw.get("type") or "").strip()
            if card_type not in ("LINK", "ITINERARY_OPTIMIZATION"):
                warnings.append(f"已忽略不支持的卡片类型：{card_type or '未知'}。")
                continue

            if card_type == "LINK":
                if context is not None:
                    warnings.append("LINK 卡片仅在未绑定计划时可用，已忽略。")
                    continue
                try:
                    payload_raw = raw.get("payload") or {}
                    payload = {
                        "action_type": str(payload_raw.get("action_type") or "NAVIGATE_TO_CREATE_PLAN"),
                    }
                    card = AiLinkCard(
                        id=str(raw.get("id") or "card-link"),
                        title=str(raw.get("title") or "创建旅行计划"),
                        subtitle=raw.get("subtitle"),
                        payload=payload,
                    )
                    valid_cards.append(card)
                except ValidationError:
                    warnings.append("LINK 卡片格式不完整，已忽略。")

            elif card_type == "ITINERARY_OPTIMIZATION":
                if context is None:
                    warnings.append("ITINERARY_OPTIMIZATION 卡片需要绑定计划，已忽略。")
                    continue

                raw_days = raw.get("days", [])
                if not isinstance(raw_days, list) or not raw_days:
                    warnings.append("ITINERARY_OPTIMIZATION 卡片缺少 days 数据，已忽略。")
                    continue

                parsed_days: list[AiCardDay] = []
                for raw_day in raw_days[:5]:
                    if not isinstance(raw_day, dict):
                        continue
                    day_index = self._safe_int(raw_day.get("day_index"))
                    if day_index is None:
                        warnings.append("卡片 day 缺少 day_index，已跳过。")
                        continue

                    raw_places = raw_day.get("place_refs", [])
                    if not isinstance(raw_places, list):
                        raw_places = []
                    parsed_places: list[AiCardPlaceRef] = []
                    for raw_place in raw_places[:10]:
                        if not isinstance(raw_place, dict):
                            continue
                        place_id = str(raw_place.get("itemId") or "").strip()
                        if not place_id:
                            warnings.append("卡片地点缺少 itemId，已跳过。")
                            continue
                        if place_id not in valid_place_ids:
                            warnings.append(f"卡片引用了无效地点：{place_id}，已跳过。")
                            continue
                        parsed_places.append(
                            AiCardPlaceRef(
                                itemId=place_id,
                                note=str(raw_place.get("note") or ""),
                            )
                        )

                    if parsed_places:
                        parsed_days.append(
                            AiCardDay(
                                day_index=day_index,
                                title=str(raw_day.get("title") or f"DAY {day_index}"),
                                place_refs=parsed_places,
                            )
                        )

                if not parsed_days:
                    warnings.append("ITINERARY_OPTIMIZATION 卡片无有效 day 数据，已忽略。")
                    continue

                try:
                    card = AiItineraryCard(
                        id=str(raw.get("id") or "card-itinerary"),
                        title=str(raw.get("title") or "行程优化建议"),
                        days=parsed_days,
                    )
                    valid_cards.append(card)
                except ValidationError:
                    warnings.append("ITINERARY_OPTIMIZATION 卡片格式不完整，已忽略。")

        return valid_cards, warnings

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
            f"当前日期：{context.currentDate or '未知'}",
        ]
        if context.todayDayIndex is not None:
            lines.append(
                f"今天对应计划中的 DAY {context.todayDayIndex}。"
                "用户询问今天的行程时，只介绍这一天的真实安排，不要说没有绑定计划。"
            )
        else:
            lines.append("当前日期不在该计划日期范围内。")
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

    def _build_quick_replies(
        self,
        context: AiPlanContext | None,
        retrieval_city: str | None = None,
        recommended_places: list[AiRecommendedPlace] | None = None,
    ) -> list[str]:
        if recommended_places:
            category = recommended_places[0].category
            city = retrieval_city or "这里"
            if category == "food":
                return [
                    f"{city}还有哪些本地人常去的店",
                    "这些店分别适合吃什么",
                    "怎样避开用餐排队高峰",
                ]
            return [
                "这些地点应该怎么选",
                f"再推荐几个{city}的小众地点",
                "这些地方适合带家人吗",
            ]
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
