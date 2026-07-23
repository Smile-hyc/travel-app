from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Protocol

from app.review_store import ReviewStore
from app.schemas.explore import (
    ExperienceInsight,
    OfficialNotice,
    PlaceDetail,
    PlaceExperienceLayer,
    PlaceFactLayer,
    PlaceOfficialLayer,
    PlaceSummary,
    ReviewBatchEvent,
    ReviewBatchItem,
    ReviewBatchResponse,
    ReviewEnrichmentStatus,
    ReviewHighlight,
    ReviewSource,
)
from app.services.content_cleaning import clean_review_sources


FACT_TTL = timedelta(days=1)
CROWD_TTL = timedelta(days=7)
EXPERIENCE_TTL = timedelta(days=30)
# One attributable note is enough to expose a clearly labelled reference.
# Confidence and the UI sample badge communicate how much corroboration exists.
MIN_INDEPENDENT_EVIDENCE = 1
SUMMARY_VERSION = "experience-evidence-v3"


class PlaceReviewClient(Protocol):
    @property
    def configured(self) -> bool: ...

    async def search_place(self, place: PlaceSummary) -> list[ReviewSource]: ...


@dataclass
class _BatchRecord:
    batch_id: str
    places: dict[str, PlaceSummary]
    items: dict[str, ReviewBatchItem]
    events: list[ReviewBatchEvent] = field(default_factory=list)
    subscribers: list[asyncio.Queue[ReviewBatchEvent]] = field(default_factory=list)
    pending_ids: set[str] = field(default_factory=set)
    raw_counts: dict[str, int] = field(default_factory=dict)
    accepted_counts: dict[str, int] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None


class PlaceDetailService:
    """Three-layer POI profile with non-blocking, evidence-backed enrichment.

    A detail request always returns AMap and official facts immediately. Missing
    UGC is queued in a bounded batch. Every attributable experience can be
    exposed, while its source count and confidence make low-sample conclusions clear.
    """

    def __init__(
        self,
        review_client: PlaceReviewClient,
        *,
        store: ReviewStore | None = None,
        author_hash_salt: str = "local-development",
        cache_ttl_seconds: int = 21600,
        empty_cache_ttl_seconds: int = 300,
    ) -> None:
        # Legacy TTL arguments remain accepted so existing construction and
        # downstream tests do not break; durable layer-specific TTLs are used.
        del cache_ttl_seconds, empty_cache_ttl_seconds
        self._review_client = review_client
        self._store = store or ReviewStore(":memory:")
        self._author_hash_salt = author_hash_salt
        self._batches: dict[str, _BatchRecord] = {}
        self._inflight: dict[str, asyncio.Future[list[ReviewSource] | None]] = {}

    async def get_detail(self, place: PlaceSummary) -> PlaceDetail:
        batch = await self.ensure_batch([place])
        item = batch.items[0]
        return item.detail or self._build_detail(place, item.status, batch.batchId)

    def get_planning_signals(
        self,
        place: PlaceSummary,
        trip_dates: list[datetime],
    ) -> dict[str, object]:
        """Return local official/experience signals without starting UGC collection."""
        self.ensure_place_profile(place)
        official_source = self._store.get_official_source_by_poi(place.sourcePoiId) or {}
        aggregate = self._store.get_aggregate(place.sourcePoiId) or {}
        evidence_count = int(aggregate.get("evidence_count") or 0)
        insights = _json_value(aggregate.get("insights"), [])
        queue_mentions = sum(
            int(item.get("mentionCount") or item.get("mention_count") or 0)
            for item in insights
            if isinstance(item, dict) and item.get("tag") == "QUEUE"
        )
        crowd_risk = min(1.0, queue_mentions / max(evidence_count, 1))

        closed_dates: list[str] = []
        reservation_notes: list[str] = []
        undated_closures: list[str] = []
        opening_hours_by_date: dict[str, str] = {}
        access_notes: list[str] = []
        capacity_notes: list[str] = []
        ticket_notes: list[str] = []
        for trip_date in trip_dates:
            notices = self._store.list_official_notices(place.sourcePoiId, at=trip_date)
            for notice in notices:
                notice_type = str(notice.get("notice_type") or "")
                summary = str(notice.get("summary") or notice.get("title") or "").strip()
                if notice_type == "CLOSURE":
                    if _is_access_restriction_notice(summary):
                        access_notes.append(summary)
                        continue
                    # An old closure article with no validity interval must not
                    # silently close a place forever. It remains a warning.
                    if notice.get("effective_from") or notice.get("effective_to"):
                        closed_dates.append(trip_date.date().isoformat())
                    elif summary:
                        undated_closures.append(summary)
                elif notice_type == "RESERVATION" and summary:
                    reservation_notes.append(summary)
                elif notice_type == "HOLIDAY_HOURS" and summary:
                    opening_hours_by_date[trip_date.date().isoformat()] = summary
                elif notice_type == "NOTICE" and summary and _is_access_restriction_notice(summary):
                    access_notes.append(summary)
                elif notice_type == "CAPACITY" and summary:
                    capacity_notes.append(summary)
                    if (
                        any(word in summary for word in ("预约已满", "售罄", "达到最大承载", "停止售票"))
                        and (notice.get("effective_from") or notice.get("effective_to"))
                    ):
                        closed_dates.append(trip_date.date().isoformat())
                elif notice_type == "TICKET" and summary:
                    ticket_notes.append(summary)

        return {
            "officialScenicGrade": official_source.get("scenic_grade"),
            "experienceEvidenceCount": evidence_count,
            "officialReservationRequired": bool(reservation_notes),
            "officialReservationNote": next(iter(dict.fromkeys(reservation_notes)), None),
            "officialClosedDates": list(dict.fromkeys(closed_dates)),
            "officialClosureWarning": next(iter(dict.fromkeys(undated_closures)), None),
            "officialOpeningHoursByDate": opening_hours_by_date,
            "officialAccessNote": next(iter(dict.fromkeys(access_notes)), None),
            "officialMaxDailyCapacity": official_source.get("max_daily_capacity"),
            "officialCapacityNote": next(iter(dict.fromkeys(capacity_notes)), None),
            "officialTicketNote": next(iter(dict.fromkeys(ticket_notes)), None),
            "crowdRisk": crowd_risk,
            "contentUpdatedAt": aggregate.get("updated_at"),
        }

    def ensure_place_profile(self, place: PlaceSummary) -> dict:
        """Persist AMap facts so official/UGC workers share one POI identity."""
        return self._store.upsert_place_profile(self._profile_mapping(place))

    def import_review_sources(
        self,
        place: PlaceSummary,
        sources: list[ReviewSource],
    ) -> dict[str, object]:
        """Clean and persist a local collector's traceable UGC export."""
        self.ensure_place_profile(place)
        status, accepted_count = self._persist_and_aggregate(place, sources)
        return {
            "sourcePoiId": place.sourcePoiId,
            "placeName": place.name,
            "fetchedCount": len(sources),
            "acceptedCount": accepted_count,
            "status": status,
            "detail": self._build_detail(place, status, None),
        }

    async def ensure_batch(
        self,
        places: list[PlaceSummary],
        *,
        force_refresh: bool = False,
    ) -> ReviewBatchResponse:
        unique = {place.sourcePoiId: place for place in places[:30]}
        if not unique:
            raise ValueError("places must not be empty")

        batch_id = str(uuid.uuid4())
        items: dict[str, ReviewBatchItem] = {}
        pending: list[PlaceSummary] = []
        for place in unique.values():
            self.ensure_place_profile(place)
            aggregate = self._store.get_aggregate(place.sourcePoiId)
            if (
                aggregate
                and aggregate.get("summary_version") != SUMMARY_VERSION
                and self._store.list_active_evidence(place.sourcePoiId, limit=1)
            ):
                self._save_aggregate_from_evidence(place)
                aggregate = self._store.get_aggregate(place.sourcePoiId)
            current_status = self._cached_status(aggregate)
            needs_refresh = self._needs_refresh(aggregate, place, force_refresh)
            if aggregate and current_status in {"READY", "INSUFFICIENT"}:
                status = current_status
                if needs_refresh and self._review_client.configured:
                    pending.append(place)
            elif not self._review_client.configured:
                status = current_status if aggregate else "UNAVAILABLE"
            else:
                status = "PENDING"
                pending.append(place)
            detail = self._build_detail(place, status, batch_id)
            items[place.sourcePoiId] = ReviewBatchItem(
                sourcePoiId=place.sourcePoiId,
                status=status,
                detail=detail,
            )

        record = _BatchRecord(
            batch_id=batch_id,
            places=unique,
            items=items,
            pending_ids={place.sourcePoiId for place in pending},
        )
        self._remember_batch(record)
        self._publish(
            record,
            ReviewBatchEvent(
                batchId=batch_id,
                type="SNAPSHOT",
                message="地点事实已就绪，体验评价按缓存状态返回。",
                completed=len(items) - len(pending),
                total=len(items),
            ),
        )
        if pending:
            record.task = asyncio.create_task(
                self._run_enrichment(record, pending),
                name=f"review-enrichment-{batch_id}",
            )
        else:
            self._publish_complete(record)
        return self._batch_response(record)

    async def stream_batch(self, batch_id: str) -> AsyncIterator[ReviewBatchEvent]:
        record = self._batches.get(batch_id)
        if record is None:
            raise KeyError(batch_id)
        queue: asyncio.Queue[ReviewBatchEvent] = asyncio.Queue()
        history = list(record.events)
        record.subscribers.append(queue)
        try:
            for event in history:
                yield event
                if event.type == "COMPLETE":
                    return
            while True:
                event = await queue.get()
                yield event
                if event.type == "COMPLETE":
                    return
        finally:
            if queue in record.subscribers:
                record.subscribers.remove(queue)

    def get_batch(self, batch_id: str) -> ReviewBatchResponse | None:
        record = self._batches.get(batch_id)
        return self._batch_response(record) if record else None

    def get_batch_metrics(self, batch_id: str) -> dict[str, dict[str, int]]:
        """Return per-POI counts for the current collection attempt only."""
        record = self._batches.get(batch_id)
        if record is None:
            return {}
        return {
            poi_id: {
                "fetched": record.raw_counts.get(poi_id, 0),
                "accepted": record.accepted_counts.get(poi_id, 0),
            }
            for poi_id in record.places
        }

    async def _run_enrichment(self, record: _BatchRecord, places: list[PlaceSummary]) -> None:
        loop = asyncio.get_running_loop()
        futures: dict[str, asyncio.Future[list[ReviewSource] | None]] = {}
        claimed: list[PlaceSummary] = []
        for place in places:
            future = self._inflight.get(place.sourcePoiId)
            if future is None:
                future = loop.create_future()
                self._inflight[place.sourcePoiId] = future
                claimed.append(place)
            futures[place.sourcePoiId] = future

        if claimed:
            try:
                search_many = getattr(self._review_client, "search_places", None)
                if callable(search_many):
                    claimed_results = await search_many(claimed)
                else:
                    pairs = await asyncio.gather(
                        *(self._review_client.search_place(place) for place in claimed),
                    )
                    claimed_results = {
                        place.sourcePoiId: sources for place, sources in zip(claimed, pairs)
                    }
                for place in claimed:
                    futures[place.sourcePoiId].set_result(claimed_results.get(place.sourcePoiId, []))
            except Exception:
                for place in claimed:
                    future = futures[place.sourcePoiId]
                    if not future.done():
                        future.set_result(None)

        results = {poi_id: await future for poi_id, future in futures.items()}

        for place in places:
            if results.get(place.sourcePoiId) is None:
                status: ReviewEnrichmentStatus = "UNAVAILABLE"
                event_type = "PLACE_UNAVAILABLE"
                message = "授权用户内容服务暂不可用，地点事实不受影响。"
            else:
                sources = results.get(place.sourcePoiId) or []
                record.raw_counts[place.sourcePoiId] = len(sources)
                status, accepted_count = self._persist_and_aggregate(place, sources)
                record.accepted_counts[place.sourcePoiId] = accepted_count
                event_type = "PLACE_READY" if status == "READY" else "PLACE_INSUFFICIENT"
                message = (
                    "已生成带来源数量提示的体验参考。"
                    if status == "READY"
                    else "已保存可追溯来源，但暂未识别出明确体验主题。"
                )
            detail = self._build_detail(place, status, record.batch_id)
            record.items[place.sourcePoiId] = ReviewBatchItem(
                sourcePoiId=place.sourcePoiId,
                status=status,
                detail=detail,
            )
            record.pending_ids.discard(place.sourcePoiId)
            completed = len(record.items) - len(record.pending_ids)
            self._publish(
                record,
                ReviewBatchEvent(
                    batchId=record.batch_id,
                    type=event_type,
                    sourcePoiId=place.sourcePoiId,
                    status=status,
                    detail=detail,
                    message=message,
                    completed=completed,
                    total=len(record.items),
                ),
            )
        for place in claimed:
            current = self._inflight.get(place.sourcePoiId)
            if current is futures[place.sourcePoiId]:
                self._inflight.pop(place.sourcePoiId, None)
        self._publish_complete(record)

    def _persist_and_aggregate(
        self,
        place: PlaceSummary,
        sources: list[ReviewSource],
    ) -> tuple[ReviewEnrichmentStatus, int]:
        now = _utc_now()
        cleaned_sources = clean_review_sources(place, sources)
        incoming_note_ids = {
            source.id.removeprefix("xiaohongshu:")
            for source in sources
            if source.id.strip()
        }
        accepted_note_ids = {
            item.source.id.removeprefix("xiaohongshu:") for item in cleaned_sources
        }
        # Re-imports are reconciliation runs.  If a previously accepted item
        # from this same input batch now fails stricter location/relevance
        # checks, retain its audit row but remove it from active conclusions.
        for existing in self._store.list_active_evidence(place.sourcePoiId):
            if (
                existing.get("provider") == "authorized_ugc"
                and existing.get("source_note_id") in incoming_note_ids
                and existing.get("source_note_id") not in accepted_note_ids
            ):
                self._store.mark_evidence_deleted(existing["evidence_id"])
        for cleaned in cleaned_sources:
            source = cleaned.source
            author_token = source.author or source.id
            author_hash = hashlib.sha256(
                f"{self._author_hash_salt}:{author_token}".encode("utf-8"),
            ).hexdigest()
            evidence_id = hashlib.sha256(
                f"{place.sourcePoiId}:{source.id}".encode("utf-8"),
            ).hexdigest()[:32]
            self._store.save_evidence(
                {
                    "evidence_id": evidence_id,
                    "poi_id": place.sourcePoiId,
                    "source_note_id": source.id.removeprefix("xiaohongshu:"),
                    "source_url": source.url,
                    "provider": "authorized_ugc",
                    "published_at": source.publishedAt,
                    "author_hash": author_hash,
                    "relevance_score": cleaned.relevance_score,
                    "tags": cleaned.tags,
                    "short_summary": cleaned.short_summary,
                    "summary_version": SUMMARY_VERSION,
                    "data_updated_at": now,
                    "deleted": False,
                },
            )

        self._store.prune_active_evidence(place.sourcePoiId, keep=20)

        status = self._save_aggregate_from_evidence(place, now=now)
        return status, len(cleaned_sources)

    def _save_aggregate_from_evidence(
        self,
        place: PlaceSummary,
        *,
        now: str | None = None,
    ) -> ReviewEnrichmentStatus:
        now = now or _utc_now()
        evidence = self._store.list_active_evidence(place.sourcePoiId)
        insights = _aggregate_insights(evidence, now, place.name)
        status: ReviewEnrichmentStatus = "READY" if insights else "INSUFFICIENT"
        expires_at = min(
            (insight.expiresAt for insight in insights),
            default=_iso(_parse_iso(now) + CROWD_TTL),
        )
        self._store.save_aggregate(
            {
                "poi_id": place.sourcePoiId,
                "status": status,
                "summary": (
                    "；".join(insight.summary for insight in insights)
                    if insights
                    else "暂未从现有来源中提取到明确体验主题。"
                ),
                "insights": [insight.model_dump() for insight in insights],
                "evidence_count": len(evidence),
                "evidence_ids": [item["evidence_id"] for item in evidence],
                "summary_version": SUMMARY_VERSION,
                "generated_at": now,
                "data_updated_at": now,
                "independent_source_count": len(
                    {item.get("author_hash") or item["evidence_id"] for item in evidence},
                ),
                "confidence": max((item.confidence for item in insights), default=0.0),
                "expires_at": expires_at,
            },
        )
        return status

    def _build_detail(
        self,
        place: PlaceSummary,
        status: ReviewEnrichmentStatus,
        batch_id: str | None,
    ) -> PlaceDetail:
        now = _utc_now()
        aggregate = self._store.get_aggregate(place.sourcePoiId)
        raw_insights = _json_value((aggregate or {}).get("insights"), [])
        insights = [ExperienceInsight.model_validate(item) for item in raw_insights]
        evidence = self._store.list_active_evidence(place.sourcePoiId)
        notices = [self._official_notice(item) for item in self._store.list_official_notices(place.sourcePoiId)]
        official_source = self._store.get_official_source_by_poi(place.sourcePoiId)
        sources = [
            ReviewSource(
                id=f"ugc:{item['evidence_id']}",
                platform="小红书",
                title=_evidence_source_title(item.get("short_summary") or ""),
                url=item["source_url"],
                publishedAt=item.get("published_at"),
                excerpt=item.get("short_summary"),
                evidenceId=item["evidence_id"],
                relevanceScore=item.get("relevance_score"),
                anonymousAuthorId=item.get("author_hash"),
                tags=_json_value(item.get("tags"), []),
                deleted=bool(item.get("deleted", False)),
            )
            for item in evidence[:8]
        ]
        positives = [
            ReviewHighlight(title=item.title, description=item.summary)
            for item in insights
            if item.tag not in {"QUEUE", "WALKING", "RESERVATION"}
            and not (item.tag == "WORTH_IT" and _has_negative_experience(item.summary))
        ]
        negatives = [
            ReviewHighlight(title=item.title, description=item.summary)
            for item in insights
            if item.tag in {"QUEUE", "WALKING", "RESERVATION"}
            or (item.tag == "WORTH_IT" and _has_negative_experience(item.summary))
        ]
        if not insights:
            positives = _fact_highlights(place)
            if not place.openingHoursWeek and not place.openingHoursToday:
                negatives.append(
                    ReviewHighlight(
                        title="营业时间待确认",
                        description="暂未获取可靠营业时间，建议到访前通过景区官方渠道确认。",
                    ),
                )
        fact_expiry = _iso(_parse_iso(now) + FACT_TTL)
        experience_updated = (aggregate or {}).get("updated_at")
        experience_expiry = (aggregate or {}).get("expires_at")
        ready = status == "READY" and bool(insights)
        return PlaceDetail(
            summary=place,
            images=place.images,
            openingHours=place.openingHoursWeek or place.openingHoursToday,
            phone=place.phone,
            description=_build_description(place),
            reviewTitle="真实评价" if ready else "体验样本积累中" if status == "PENDING" else "地点亮点",
            reviewSubtitle=(
                f"根据 {len(evidence)} 条可追溯用户内容提炼，样本数量已逐项标注"
                if ready
                else "事实信息已返回；体验内容仅作为旅行参考"
            ),
            positiveHighlights=positives[:4],
            negativeHighlights=negatives[:3],
            reviewSources=sources,
            sourceLabels=["小红书"] if sources else [],
            hasRealReviews=ready,
            reviewUpdatedAt=experience_updated,
            enrichmentBatchId=batch_id,
            reviewStatus=status,
            factLayer=PlaceFactLayer(
                sourcePoiId=place.sourcePoiId,
                name=place.name,
                address=place.address,
                latitude=place.latitude,
                longitude=place.longitude,
                openingHours=place.openingHoursWeek or place.openingHoursToday,
                rating=place.rating,
                phone=place.phone,
                routeAvailable=place.latitude is not None and place.longitude is not None,
                updatedAt=now,
                expiresAt=fact_expiry,
            ),
            officialLayer=PlaceOfficialLayer(
                status="READY" if notices or official_source else "UNAVAILABLE",
                notices=notices,
                updatedAt=max((item.effectiveAt or "" for item in notices), default=None),
                sourceId=(official_source or {}).get("source_id"),
                officialName=(official_source or {}).get("official_name"),
                scenicGrade=(official_source or {}).get("scenic_grade"),
                maxDailyCapacity=(official_source or {}).get("max_daily_capacity"),
                websiteUrl=(official_source or {}).get("website_url"),
                wechatName=(official_source or {}).get("wechat_name"),
                miniProgramName=(official_source or {}).get("mini_program_name"),
                ticketingUrl=(official_source or {}).get("ticketing_url"),
            ),
            experienceLayer=PlaceExperienceLayer(
                status=status,
                insights=insights,
                evidenceCount=int((aggregate or {}).get("evidence_count") or len(evidence)),
                updatedAt=experience_updated,
                expiresAt=experience_expiry,
                minimumEvidenceCount=MIN_INDEPENDENT_EVIDENCE,
                summaryVersion=(aggregate or {}).get("summary_version"),
            ),
        )

    def _profile_mapping(self, place: PlaceSummary) -> dict:
        now = _utc_now()
        return {
            **place.model_dump(),
            "poi_id": place.sourcePoiId,
            "source_poi_id": place.sourcePoiId,
            "facts_updated_at": now,
            "facts_expires_at": _iso(_parse_iso(now) + FACT_TTL),
        }

    @staticmethod
    def _official_notice(raw: dict) -> OfficialNotice:
        return OfficialNotice(
            type=raw.get("notice_type") or raw.get("type") or "NOTICE",
            title=raw.get("title") or "景区通知",
            detail=raw.get("detail") or raw.get("summary") or "",
            sourceUrl=raw.get("source_url") or raw.get("sourceUrl") or "",
            effectiveAt=raw.get("effective_at") or raw.get("effectiveAt") or raw.get("effective_from"),
            expiresAt=raw.get("expires_at") or raw.get("expiresAt") or raw.get("effective_to"),
        )

    @staticmethod
    def _cached_status(aggregate: dict | None) -> ReviewEnrichmentStatus:
        value = str((aggregate or {}).get("status") or "INSUFFICIENT")
        return value if value in {"READY", "INSUFFICIENT", "UNAVAILABLE"} else "INSUFFICIENT"

    @staticmethod
    def _is_expired(aggregate: dict | None) -> bool:
        expires_at = (aggregate or {}).get("expires_at")
        return not expires_at or _parse_iso(expires_at) <= datetime.now(timezone.utc)

    @classmethod
    def _needs_refresh(
        cls,
        aggregate: dict | None,
        place: PlaceSummary,
        force_refresh: bool,
    ) -> bool:
        if force_refresh or cls._is_expired(aggregate):
            return True
        # Highly rated POIs are treated as hot inventory and refreshed sooner;
        # cold POIs remain read-through until their layer-specific TTL expires.
        try:
            popular = float(place.rating or 0) >= 4.7
        except ValueError:
            popular = False
        if not popular:
            return False
        updated_at = (aggregate or {}).get("data_updated_at") or (aggregate or {}).get("updated_at")
        return not updated_at or _parse_iso(updated_at) <= datetime.now(timezone.utc) - timedelta(days=3)

    def _remember_batch(self, record: _BatchRecord) -> None:
        self._batches[record.batch_id] = record
        while len(self._batches) > 128:
            oldest = next(iter(self._batches))
            self._batches.pop(oldest, None)

    def _publish(self, record: _BatchRecord, event: ReviewBatchEvent) -> None:
        record.events.append(event)
        record.events[:] = record.events[-96:]
        for subscriber in list(record.subscribers):
            subscriber.put_nowait(event)

    def _publish_complete(self, record: _BatchRecord) -> None:
        self._publish(
            record,
            ReviewBatchEvent(
                batchId=record.batch_id,
                type="COMPLETE",
                message="本批地点评价状态已更新。",
                completed=sum(item.status != "PENDING" for item in record.items.values()),
                total=len(record.items),
            ),
        )

    @staticmethod
    def _batch_response(record: _BatchRecord) -> ReviewBatchResponse:
        return ReviewBatchResponse(
            batchId=record.batch_id,
            items=list(record.items.values()),
            pendingCount=len(record.pending_ids),
        )


TAG_TITLES = {
    "PHOTO": "拍照体验",
    "QUEUE": "排队与客流",
    "RESERVATION": "预约提醒",
    "WALKING": "步行强度",
    "FOOD": "周边美食",
    "WORTH_IT": "游览感受",
}

TAG_DETAIL_KEYWORDS = {
    "PHOTO": ("机位", "拍照", "出片", "草坪", "夜景", "光线", "复古", "好拍", "大片"),
    "QUEUE": ("排队", "人多", "拥挤", "客流", "等候", "节假日"),
    "RESERVATION": ("预约", "购票", "抢票", "放票", "实名", "门票"),
    "WALKING": (
        "公里",
        "小时",
        "步行",
        "骑行",
        "轻松不累",
        "走路",
        "台阶",
        "两万步",
        "暴走",
        "不绕路",
        "穿舒服",
    ),
    "FOOD": ("美食", "小吃", "咖啡", "餐饮", "好吃", "味道", "人均"),
    "WORTH_IT": (
        "值得",
        "推荐",
        "必去",
        "好玩",
        "老少皆宜",
        "不感兴趣",
        "商业化",
        "体验感",
    ),
}

_DETAIL_SPLIT_RE = re.compile(
    r"(?:[。！？!?；;，,\n]+|(?:地址|交通|门票|路线|行程安排|住宿|拍照|出行建议)[：:])"
)
_TOPIC_RE = re.compile(r"#[^#]{0,80}#|\[[^\]]{0,20}\]")
_DETAIL_SPACE_RE = re.compile(r"\s+")


def _aggregate_insights(evidence: list[dict], now: str, place_name: str = "") -> list[ExperienceInsight]:
    by_tag: dict[str, dict[str, dict]] = {}
    for item in evidence:
        tags = _json_value(item.get("tags"), [])
        author = item.get("author_hash") or item["evidence_id"]
        for tag in tags:
            by_tag.setdefault(tag, {})[author] = item
    insights: list[ExperienceInsight] = []
    for tag, independent in by_tag.items():
        if len(independent) < MIN_INDEPENDENT_EVIDENCE or tag not in TAG_TITLES:
            continue
        ttl = CROWD_TTL if tag == "QUEUE" else EXPERIENCE_TTL
        items = list(independent.values())
        summary = _build_evidence_summary(tag, items, place_name)
        if not summary:
            continue
        title = TAG_TITLES[tag]
        if tag == "WORTH_IT" and _has_negative_experience(summary):
            title = "体验分歧"
        insights.append(
            ExperienceInsight(
                tag=tag,
                title=title,
                summary=summary,
                mentionCount=len(items),
                confidence=min(0.95, round(0.34 + len(items) * 0.15, 2)),
                evidenceIds=[item["evidence_id"] for item in items[:12]],
                updatedAt=now,
                expiresAt=_iso(_parse_iso(now) + ttl),
            ),
        )
    return insights


def _build_evidence_summary(tag: str, items: list[dict], place_name: str = "") -> str:
    """Build a compact, evidence-grounded insight instead of a canned claim."""
    candidates: list[tuple[int, str]] = []
    fingerprints: set[str] = set()
    for item in sorted(
        items,
        key=lambda value: (
            float(value.get("relevance_score") or 0),
            str(value.get("published_at") or ""),
        ),
        reverse=True,
    ):
        snippet = _extract_detail_snippet(
            str(item.get("short_summary") or ""),
            tag,
            place_name,
        )
        fingerprint = re.sub(r"\W", "", snippet)[:36]
        if snippet and fingerprint and fingerprint not in fingerprints:
            candidates.append((_snippet_quality(snippet, tag, place_name), snippet))
            fingerprints.add(fingerprint)
    if not candidates:
        return ""
    snippets = [item[1] for item in sorted(candidates, reverse=True)[:2]]
    return "；".join(snippets) + "。"


def _extract_detail_snippet(text: str, tag: str, place_name: str = "") -> str:
    cleaned = _clean_evidence_display_text(text)
    if not cleaned:
        return ""
    keywords = TAG_DETAIL_KEYWORDS.get(tag, ())
    normalized_cleaned = re.sub(r"\W", "", cleaned).lower()
    names = _summary_place_aliases(place_name) if place_name else set()
    evidence_place_matched = any(name in normalized_cleaned for name in names)
    if place_name and tag in {"PHOTO", "FOOD", "WORTH_IT"} and not evidence_place_matched:
        return ""
    if tag == "PHOTO":
        direct_photo = _direct_photo_detail(cleaned, place_name)
        if direct_photo:
            return direct_photo
    if tag == "FOOD":
        direct_food = _direct_food_detail(cleaned, place_name)
        if direct_food:
            return direct_food
    if tag == "WORTH_IT":
        route_fit = re.search(
            r"(?:推荐的)?walk路线[，, ]*总长\s*(\d+(?:\.\d+)?)\s*公里[，, ]*老少皆宜",
            cleaned,
            re.I,
        )
        if route_fit:
            return f"路线总长{route_fit.group(1)}公里，老少皆宜"
        direct_worth = _direct_worth_detail(cleaned, place_name)
        if direct_worth:
            return direct_worth
    if tag == "WALKING":
        metric = re.search(
            r"全程(?:大概|约)?\s*\d+(?:\.\d+)?\s*(?:公里|km)"
            r"[^。！？!?；;]{0,16}?\d+(?:\s*[-~至到]\s*\d+)?\s*小时",
            cleaned,
            re.I,
        )
        if metric:
            return metric.group(0).strip(" ，,、:-")
        mode = re.search(r"全程步行\s*\+\s*骑行\s*轻松不累", cleaned)
        if mode:
            return mode.group(0)
    clauses = [item.strip(" ，,、:-") for item in _DETAIL_SPLIT_RE.split(cleaned) if item.strip()]
    candidates: list[tuple[int, str]] = []
    for clause in clauses or [cleaned]:
        positions = sorted({clause.find(keyword) for keyword in keywords if keyword in clause})
        if not positions:
            continue
        for position in positions:
            start = max(0, position - 24)
            end = min(len(clause), position + 44)
            excerpt = clause[start:end].strip(" ，,、:-")
            if start > 0:
                excerpt = "…" + excerpt
            if end < len(clause):
                excerpt += "…"
            focused_excerpt = _focus_excerpt_on_place(excerpt, place_name)
            if any(keyword in focused_excerpt for keyword in keywords):
                excerpt = focused_excerpt
            score = sum(keyword in excerpt for keyword in keywords) * 3
            score += 3 if re.search(r"\d+(?:\.\d+)?\s*(?:公里|km|米|分钟|小时|元|点|步)", excerpt, re.I) else 0
            score += sum(marker in excerpt for marker in ("建议", "不要", "免费", "地铁", "路线", "适合", "最好"))
            if place_name:
                normalized_excerpt = re.sub(r"\W", "", excerpt).lower()
                place_matched = any(name in normalized_excerpt for name in names)
                if place_matched:
                    score += 8
            if any(
                marker in excerpt
                for marker in (
                    "午后",
                    "清晨",
                    "傍晚",
                    "门口",
                    "对面",
                    "草坪",
                    "公里",
                    "小时",
                    "分钟",
                    "免费",
                    "人多",
                    "复古",
                    "好拍",
                    "出片",
                    "略过",
                    "商业化",
                )
            ):
                score += 4
            if len(excerpt) <= 35 and any(marker in excerpt for marker in ("分享", "攻略", "合集")):
                score -= 8
            candidates.append((score, excerpt))
    if not candidates:
        return ""
    result = max(candidates, key=lambda item: (item[0], len(item[1])))[1]
    return result[:72] + ("…" if len(result) > 72 else "")


def _snippet_quality(snippet: str, tag: str, place_name: str) -> int:
    normalized = re.sub(r"\W", "", snippet).lower()
    score = sum(keyword in snippet for keyword in TAG_DETAIL_KEYWORDS.get(tag, ())) * 2
    if any(alias in normalized for alias in _summary_place_aliases(place_name)):
        score += 8
    if re.search(r"\d+(?:\.\d+)?\s*(?:公里|km|米|分钟|小时|元|点|步)", snippet, re.I):
        score += 5
    score += sum(
        marker in snippet
        for marker in (
            "门口",
            "对面",
            "草坪",
            "罗马柱",
            "非节假日",
            "人多",
            "免费",
            "商业化",
            "略过",
            "复古",
            "好拍",
        )
    ) * 2
    if snippet.count("→") + snippet.count("➡") >= 3:
        score -= 6
    return score


def _focus_excerpt_on_place(excerpt: str, place_name: str) -> str:
    """Cut numbered city-wide lists down to the current POI's own item."""
    normalized_aliases = sorted(_summary_place_aliases(place_name), key=len, reverse=True)
    for alias in normalized_aliases:
        match = re.search(re.escape(alias), excerpt, re.I)
        if not match:
            continue
        focused = excerpt[match.start() :]
        next_item = re.search(r"\d{1,2}(?=[\u4e00-\u9fff])", focused[len(alias) :])
        if next_item:
            focused = focused[: len(alias) + next_item.start()]
        focused = focused.strip(" …，,、:-")
        if len(focused) >= len(alias) + 3:
            return focused
    return excerpt


def _direct_photo_detail(text: str, place_name: str) -> str:
    tangible_markers = ("门口", "对面", "草坪", "罗马柱", "复古", "好拍", "大片", "出片", "角度拍照")
    for alias in sorted(_summary_place_aliases(place_name), key=len, reverse=True):
        for match in re.finditer(re.escape(alias), text, re.I):
            detail = text[match.start() : match.start() + 82]
            if not any(marker in detail for marker in tangible_markers):
                continue
            next_item = re.search(r"\d{1,2}(?=[\u4e00-\u9fff])", detail[len(alias) :])
            if next_item:
                detail = detail[: len(alias) + next_item.start()]
            if detail.count("（") > detail.count("）"):
                detail = detail.rsplit("（", 1)[0]
            return detail.strip(" …，,、:-")
    return ""


def _direct_food_detail(text: str, place_name: str) -> str:
    proximity_markers = ("附近", "对面", "门口", "旁边", "地铁站", "巷子")
    food_markers = ("好吃", "鸡排", "米饭", "韩餐", "咖啡", "小吃", "餐厅")
    for alias in sorted(_summary_place_aliases(place_name), key=len, reverse=True):
        for match in re.finditer(re.escape(alias), text, re.I):
            detail = text[match.start() : match.start() + 132]
            if any(marker in detail for marker in proximity_markers) and any(
                marker in detail for marker in food_markers
            ):
                return _trim_complete_detail(detail)
    return ""


def _direct_worth_detail(text: str, place_name: str) -> str:
    markers = ("商业化", "不感兴趣", "可以略过", "体验感", "不值得", "老少皆宜")
    for alias in sorted(_summary_place_aliases(place_name), key=len, reverse=True):
        for match in re.finditer(re.escape(alias), text, re.I):
            detail = text[match.start() : match.start() + 132]
            if any(marker in detail for marker in markers):
                return _trim_complete_detail(detail)
    return ""


def _trim_complete_detail(text: str, limit: int = 112) -> str:
    text = text.strip(" …，,、:-")
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    boundary = max(clipped.rfind(mark) for mark in ("。", "！", "？", "，", ","))
    if boundary >= 42:
        return clipped[:boundary].strip(" …，,、:-")
    return clipped.rstrip(" …，,、:-") + "…"


def _clean_evidence_display_text(text: str) -> str:
    text = _TOPIC_RE.sub(" ", text)
    text = "".join(
        character
        for character in text
        if (
            character in {"→", "➡"}
            or (
                unicodedata.category(character) not in {"So", "Sk", "Cs"}
                and ord(character) not in {0xFE0E, 0xFE0F, 0x20E3}
            )
        )
    )
    return _DETAIL_SPACE_RE.sub(" ", text).strip(" ，,。.!！?？|-_")


def _summary_place_aliases(place_name: str) -> set[str]:
    normalized = re.sub(r"\W", "", place_name).lower()
    aliases = {normalized}
    for suffix in ("文化旅游区", "风景名胜区", "旅游景区", "旅游区", "景区", "博物院", "博物馆"):
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
            aliases.add(normalized[: -len(suffix)])
    return {item for item in aliases if item}


def _evidence_source_title(summary: str) -> str:
    title = re.split(r"[。！？!?\n]", summary, maxsplit=1)[0].strip()
    return (title[:48] + "…") if len(title) > 48 else (title or "用户体验来源")


def _has_negative_experience(summary: str) -> bool:
    summary = summary.replace("不踩雷", "")
    return any(
        marker in summary
        for marker in ("不感兴趣", "略过", "商业化", "破坏", "不值得", "踩雷", "人巨多")
    )


def _is_access_restriction_notice(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    transport_terms = ("接驳", "索道", "缆车", "轮渡", "道路", "停车", "入口", "出入口", "交通管制")
    whole_place_terms = ("景区闭园", "景区闭馆", "全园闭园", "暂停开放", "停止开放")
    return any(term in compact for term in transport_terms) and not any(
        term in compact for term in whole_place_terms
    )




def _fact_highlights(place: PlaceSummary) -> list[ReviewHighlight]:
    result: list[ReviewHighlight] = []
    if place.rating:
        result.append(ReviewHighlight(title="公开评分", description=f"高德当前公开评分为 {place.rating} 分。"))
    if place.openingHoursWeek or place.openingHoursToday:
        result.append(ReviewHighlight(title="营业信息已获取", description="规划器会按高德营业信息安排到访时段。"))
    return result or [ReviewHighlight(title="地点事实已获取", description="地址和坐标可用于路线规划与导航。")]


def _build_description(place: PlaceSummary) -> str:
    location = place.address or place.districtName or place.cityName
    category = (place.typeName or place.category).replace(";", "、")
    parts = [f"{place.name}位于{location}" if location else place.name]
    if category:
        parts.append(f"地点类型为{category}")
    if place.businessArea:
        parts.append(f"所在商圈为{place.businessArea}")
    return "，".join(parts) + "。"


def _json_value(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
