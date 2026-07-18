from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.schemas.ai import (
    AiGeneratedDay,
    AiPlanGenerationRequest,
    AiPlanGenerationResponse,
    AiPlanJobState,
    AiPlanJobStatusResponse,
    AiPlanProgressEvent,
)
from app.services.travel_plan_generation_service import TravelPlanGenerationService


TERMINAL_STATES: set[AiPlanJobState] = {"COMPLETED", "FAILED", "CANCELLED"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _JobRecord:
    job_id: str
    request: AiPlanGenerationRequest
    status: AiPlanJobState = "QUEUED"
    progress: int = 0
    stage: str = "任务已创建，正在等待执行"
    completed_days: int = 0
    active_day_index: int | None = None
    partial_days: list[AiGeneratedDay] = field(default_factory=list)
    events: list[AiPlanProgressEvent] = field(default_factory=list)
    result: AiPlanGenerationResponse | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    task: asyncio.Task[None] | None = None

    def response(self) -> AiPlanJobStatusResponse:
        return AiPlanJobStatusResponse(
            jobId=self.job_id,
            status=self.status,
            progress=self.progress,
            stage=self.stage,
            completedDays=self.completed_days,
            totalDays=self.request.dayCount,
            activeDayIndex=self.active_day_index,
            partialDays=self.partial_days,
            events=self.events,
            result=self.result,
            error=self.error,
            createdAt=self.created_at.isoformat(),
            updatedAt=self.updated_at.isoformat(),
        )


class AiPlanJobManager:
    def __init__(
        self,
        generation_service: TravelPlanGenerationService,
        retention_minutes: int = 30,
    ) -> None:
        self._generation_service = generation_service
        self._retention = timedelta(minutes=retention_minutes)
        self._jobs: dict[str, _JobRecord] = {}
        self._client_requests: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create(self, request: AiPlanGenerationRequest) -> AiPlanJobStatusResponse:
        async with self._lock:
            self._cleanup()
            client_request_id = request.clientRequestId
            if client_request_id:
                existing_id = self._client_requests.get(client_request_id)
                existing = self._jobs.get(existing_id or "")
                if existing is not None:
                    return existing.response()

            job_id = str(uuid.uuid4())
            record = _JobRecord(job_id=job_id, request=request)
            self._jobs[job_id] = record
            if client_request_id:
                self._client_requests[client_request_id] = job_id
            record.task = asyncio.create_task(self._run(record), name=f"ai-plan-{job_id}")
            return record.response()

    async def get(self, job_id: str) -> AiPlanJobStatusResponse:
        async with self._lock:
            self._cleanup()
            return self._require(job_id).response()

    async def cancel(self, job_id: str) -> AiPlanJobStatusResponse:
        async with self._lock:
            record = self._require(job_id)
            if record.status in TERMINAL_STATES:
                return record.response()
            record.status = "CANCELLED"
            record.progress = min(record.progress, 99)
            record.stage = "已取消智能规划"
            record.error = None
            record.updated_at = _now()
            if record.task is not None:
                record.task.cancel()
            return record.response()

    async def _run(self, record: _JobRecord) -> None:
        record.status = "RUNNING"
        record.progress = 2
        record.stage = "智能规划任务已开始"
        record.updated_at = _now()

        def update(
            progress: int,
            stage: str,
            completed_days: int,
            partial_days: list[AiGeneratedDay] | None = None,
            event: AiPlanProgressEvent | None = None,
            active_day_index: int | None = None,
        ) -> None:
            if record.status == "CANCELLED":
                return
            record.progress = progress
            record.stage = stage
            record.completed_days = completed_days
            if partial_days is not None:
                record.partial_days = [day.model_copy(deep=True) for day in partial_days]
            if event is not None:
                if not record.events or record.events[-1].message != event.message:
                    sequenced_event = event.model_copy(update={"sequence": len(record.events) + 1})
                    record.events = [*record.events, sequenced_event][-48:]
            if active_day_index is not None:
                record.active_day_index = active_day_index
            record.updated_at = _now()

        try:
            result = await self._generation_service.generate(record.request, progress=update)
        except asyncio.CancelledError:
            if record.status != "CANCELLED":
                record.status = "CANCELLED"
                record.stage = "已取消智能规划"
                record.updated_at = _now()
            return
        except HTTPException as exc:
            record.status = "FAILED"
            record.stage = "智能规划失败"
            record.error = str(exc.detail)
            record.updated_at = _now()
            return
        except Exception:
            record.status = "FAILED"
            record.stage = "智能规划失败"
            record.error = "服务发生未预期错误，请稍后重试。"
            record.updated_at = _now()
            return

        if record.status == "CANCELLED":
            return
        record.result = result
        record.status = "COMPLETED"
        record.progress = 100
        record.completed_days = result.dayCount
        record.active_day_index = result.dayCount
        record.partial_days = [day.model_copy(deep=True) for day in result.days]
        record.stage = "行程已生成并通过质量检查"
        record.updated_at = _now()

    def _require(self, job_id: str) -> _JobRecord:
        record = self._jobs.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="智能规划任务不存在或已过期。")
        return record

    def _cleanup(self) -> None:
        threshold = _now() - self._retention
        expired = [
            job_id
            for job_id, record in self._jobs.items()
            if record.status in TERMINAL_STATES and record.updated_at < threshold
        ]
        for job_id in expired:
            record = self._jobs.pop(job_id)
            if record.request.clientRequestId:
                self._client_requests.pop(record.request.clientRequestId, None)
