from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.main_state import get_travel_ai_service
from app.schemas.ai import AiChatRequest, AiChatResponse, AiHealthResponse
from app.services.travel_ai_service import TravelAiService

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
