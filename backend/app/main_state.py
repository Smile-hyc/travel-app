from app.core.config import get_settings
from app.services.amap_client import AmapClient
from app.services.amap_poi_service import AmapPoiService
from app.services.amap_route_service import AmapRouteService
from app.services.amap_weather_service import AmapWeatherService
from app.services.ark_client import ArkClient
from app.services.travel_ai_service import TravelAiService
from app.services.ai_plan_job_manager import AiPlanJobManager
from app.services.travel_plan_generation_service import TravelPlanGenerationService

settings = get_settings()
amap_client = AmapClient(settings)
amap_poi_service = AmapPoiService(amap_client)
amap_route_service = AmapRouteService(amap_client)
amap_weather_service = AmapWeatherService(amap_client)
ark_client = ArkClient(settings)
travel_ai_service = TravelAiService(ark_client)
travel_plan_generation_service = TravelPlanGenerationService(ark_client, amap_poi_service)
ai_plan_job_manager = AiPlanJobManager(travel_plan_generation_service)


def get_amap_poi_service() -> AmapPoiService:
    return amap_poi_service


def get_amap_route_service() -> AmapRouteService:
    return amap_route_service


def get_amap_weather_service() -> AmapWeatherService:
    return amap_weather_service


def get_travel_ai_service() -> TravelAiService:
    return travel_ai_service


def get_travel_plan_generation_service() -> TravelPlanGenerationService:
    return travel_plan_generation_service


def get_ai_plan_job_manager() -> AiPlanJobManager:
    return ai_plan_job_manager
