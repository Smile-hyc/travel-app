from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.explore import AmapHealthResponse
from app.schemas.health import HealthResponse, ReviewProviderHealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        code=200,
        message="AI Travel backend is running",
        status="ok",
    )


@router.get("/health/amap", response_model=AmapHealthResponse)
def amap_health_check() -> AmapHealthResponse:
    settings = get_settings()
    return AmapHealthResponse(
        configured=settings.amap_web_service_key_configured,
        webServiceKeyConfigured=settings.amap_web_service_key_configured,
    )


@router.get("/health/reviews", response_model=ReviewProviderHealthResponse)
def review_provider_health_check() -> ReviewProviderHealthResponse:
    settings = get_settings()
    return ReviewProviderHealthResponse(
        configured=settings.active_review_provider is not None,
        activeProvider=settings.active_review_provider,
        authorizedUgcConfigured=settings.authorized_ugc_configured,
        authorized=settings.ugc_provider_authorized,
    )
