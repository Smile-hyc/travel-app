from app.core.config import get_settings
from app.services.amap_client import AmapClient
from app.services.amap_poi_service import AmapPoiService
from app.services.amap_route_service import AmapRouteService
from app.services.amap_weather_service import AmapWeatherService
from app.services.deepseek_client import DeepSeekClient
from app.services.travel_ai_service import TravelAiService
from app.services.ai_plan_job_manager import AiPlanJobManager
from app.services.travel_plan_generation_service import TravelPlanGenerationService
from app.services.place_detail_service import PlaceDetailService
from app.services.rnote_review_client import RnoteReviewClient
from app.services.tikhub_review_client import TikhubReviewClient

settings = get_settings()
amap_client = AmapClient(settings)
amap_poi_service = AmapPoiService(amap_client)
amap_route_service = AmapRouteService(amap_client)
amap_weather_service = AmapWeatherService(amap_client)
deepseek_client = DeepSeekClient(settings)
tikhub_review_client = TikhubReviewClient(settings)
rnote_review_client = RnoteReviewClient(settings)
review_client = rnote_review_client if rnote_review_client.configured else tikhub_review_client
place_detail_service = PlaceDetailService(
    review_client,
    cache_ttl_seconds=settings.review_cache_ttl_seconds,
    empty_cache_ttl_seconds=settings.review_empty_cache_ttl_seconds,
)
travel_ai_service = TravelAiService(deepseek_client, amap_poi_service)
travel_plan_generation_service = TravelPlanGenerationService(
    deepseek_client,
    amap_poi_service,
    amap_route_service,
    amap_weather_service,
)
ai_plan_job_manager = AiPlanJobManager(travel_plan_generation_service)


def get_amap_poi_service() -> AmapPoiService:
    return amap_poi_service


def get_amap_route_service() -> AmapRouteService:
    return amap_route_service


def get_amap_weather_service() -> AmapWeatherService:
    return amap_weather_service


def get_place_detail_service() -> PlaceDetailService:
    return place_detail_service


def get_travel_ai_service() -> TravelAiService:
    return travel_ai_service


def get_travel_plan_generation_service() -> TravelPlanGenerationService:
    return travel_plan_generation_service


def get_ai_plan_job_manager() -> AiPlanJobManager:
    return ai_plan_job_manager
