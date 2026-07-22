import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.main_state import (
    get_ai_plan_job_manager,
    get_travel_ai_service,
    get_travel_plan_generation_service,
)
from app.schemas.ai import (
    AiChatRequest,
    AiChatResponse,
    AiHealthResponse,
    AiPlanGenerationRequest,
    AiPlanGenerationResponse,
    AiPlanJobStatusResponse,
)
from app.services.ai_plan_job_manager import AiPlanJobManager
from app.services.travel_ai_service import TravelAiService
from app.services.travel_plan_generation_service import TravelPlanGenerationService

router = APIRouter(prefix="/api", tags=["ai"])


@router.get("/health/ai", response_model=AiHealthResponse)
def ai_health_check(settings: Settings = Depends(get_settings)) -> AiHealthResponse:
    return AiHealthResponse(
        configured=settings.ark_configured,
        apiKeyConfigured=settings.ark_api_key_configured,
        model=settings.ark_model if settings.ark_model.strip() else None,
        baseUrlConfigured=settings.ark_base_url_configured,
    )


@router.post("/ai/chat", response_model=AiChatResponse)
async def chat_with_ai(
    request: AiChatRequest,
    service: TravelAiService = Depends(get_travel_ai_service),
) -> AiChatResponse:
    return await service.chat(request)


@router.post("/ai/chat/stream")
async def chat_with_ai_stream(
    request: AiChatRequest,
    service: TravelAiService = Depends(get_travel_ai_service),
):
    async def event_generator():
        async for sse_event in service.chat_stream(request):
            yield f"data: {sse_event}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/ai/plans/generate", response_model=AiPlanGenerationResponse)
async def generate_travel_plan(
    request: AiPlanGenerationRequest,
    service: TravelPlanGenerationService = Depends(get_travel_plan_generation_service),
) -> AiPlanGenerationResponse:
    return await service.generate(request)


@router.post("/ai/plans/stream")
async def stream_travel_plan(
    request: AiPlanGenerationRequest,
    service: TravelPlanGenerationService = Depends(get_travel_plan_generation_service),
) -> StreamingResponse:
    """Stream immutable planning snapshots over SSE as decisions happen."""
    job_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    queue: asyncio.Queue[AiPlanJobStatusResponse] = asyncio.Queue()
    events = []
    state = {
        "progress": 1,
        "stage": "智能规划流已建立",
        "completed_days": 0,
        "active_day_index": None,
        "partial_days": [],
    }

    def snapshot(
        status: str = "RUNNING",
        *,
        result: AiPlanGenerationResponse | None = None,
        error: str | None = None,
    ) -> AiPlanJobStatusResponse:
        now = datetime.now(timezone.utc).isoformat()
        return AiPlanJobStatusResponse(
            jobId=job_id,
            status=status,
            progress=100 if status == "COMPLETED" else state["progress"],
            stage=("行程已生成并通过质量检查" if status == "COMPLETED" else state["stage"]),
            completedDays=(request.dayCount if status == "COMPLETED" else state["completed_days"]),
            totalDays=request.dayCount,
            activeDayIndex=state["active_day_index"],
            partialDays=(result.days if result is not None else state["partial_days"]),
            events=events,
            result=result,
            error=error,
            createdAt=created_at,
            updatedAt=now,
        )

    def update(progress, stage, completed_days, partial_days=None, event=None, active_day_index=None) -> None:
        state["progress"] = progress
        state["stage"] = stage
        state["completed_days"] = completed_days
        if partial_days is not None:
            state["partial_days"] = [day.model_copy(deep=True) for day in partial_days]
        if event is not None and (not events or events[-1].message != event.message):
            events.append(event.model_copy(update={"sequence": len(events) + 1}, deep=True))
            del events[:-64]
        if active_day_index is not None:
            state["active_day_index"] = active_day_index
        queue.put_nowait(snapshot())

    async def run() -> None:
        queue.put_nowait(snapshot())
        try:
            result = await service.generate(request, progress=update)
            queue.put_nowait(snapshot("COMPLETED", result=result))
        except asyncio.CancelledError:
            raise
        except HTTPException as exc:
            state["stage"] = "智能规划失败"
            queue.put_nowait(snapshot("FAILED", error=str(exc.detail)))
        except Exception:
            state["stage"] = "智能规划失败"
            queue.put_nowait(snapshot("FAILED", error="服务发生未预期错误，请稍后重试。"))

    async def event_stream():
        worker = asyncio.create_task(run(), name=f"ai-plan-stream-{job_id}")
        try:
            while True:
                item = await queue.get()
                event_name = "complete" if item.status == "COMPLETED" else "error" if item.status == "FAILED" else "progress"
                yield f"event: {event_name}\ndata: {item.model_dump_json()}\n\n"
                if item.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                    break
        finally:
            if not worker.done():
                worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ai/plans/jobs", response_model=AiPlanJobStatusResponse, status_code=202)
async def create_travel_plan_job(
    request: AiPlanGenerationRequest,
    manager: AiPlanJobManager = Depends(get_ai_plan_job_manager),
) -> AiPlanJobStatusResponse:
    return await manager.create(request)


@router.get("/ai/plans/jobs/{job_id}", response_model=AiPlanJobStatusResponse)
async def get_travel_plan_job(
    job_id: str,
    manager: AiPlanJobManager = Depends(get_ai_plan_job_manager),
) -> AiPlanJobStatusResponse:
    return await manager.get(job_id)


@router.post("/ai/plans/jobs/{job_id}/cancel", response_model=AiPlanJobStatusResponse)
async def cancel_travel_plan_job(
    job_id: str,
    manager: AiPlanJobManager = Depends(get_ai_plan_job_manager),
) -> AiPlanJobStatusResponse:
    return await manager.cancel(job_id)
