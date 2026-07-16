from fastapi import APIRouter, Depends

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


@router.post("/ai/plans/generate", response_model=AiPlanGenerationResponse)
async def generate_travel_plan(
    request: AiPlanGenerationRequest,
    service: TravelPlanGenerationService = Depends(get_travel_plan_generation_service),
) -> AiPlanGenerationResponse:
    return await service.generate(request)


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
