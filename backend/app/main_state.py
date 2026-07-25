from pathlib import Path

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
from app.services.tikhub_review_client import TikhubReviewClient
from app.review_store import ReviewStore
from app.services.content_ingestion_service import ContentIngestionService
from app.services.popular_poi_catalog import PopularPoiCatalogService
from app.services.official_content_service import OfficialContentService
from app.services.official_source_catalog import initialize_official_directory
from app.services.mediacrawler_import_service import MediaCrawlerImportService
from app.services.mediacrawler_runner import MediaCrawlerRunner
from app.services.city_content_pipeline import CityContentPipelineService

settings = get_settings()
backend_root = Path(__file__).resolve().parents[1]


def _setting_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (backend_root / path).resolve()


amap_client = AmapClient(settings)
amap_poi_service = AmapPoiService(amap_client)
amap_route_service = AmapRouteService(amap_client)
amap_weather_service = AmapWeatherService(amap_client)
deepseek_client = DeepSeekClient(settings)
tikhub_review_client = TikhubReviewClient(settings)
review_store = ReviewStore(_setting_path(settings.review_database_path))
initialize_official_directory(review_store)
place_detail_service = PlaceDetailService(
    tikhub_review_client,
    store=review_store,
    author_hash_salt=settings.review_author_hash_salt,
    cache_ttl_seconds=settings.review_cache_ttl_seconds,
    empty_cache_ttl_seconds=settings.review_empty_cache_ttl_seconds,
)
travel_ai_service = TravelAiService(deepseek_client, amap_poi_service)
travel_plan_generation_service = TravelPlanGenerationService(
    deepseek_client,
    amap_poi_service,
    amap_route_service,
    amap_weather_service,
    place_detail_service=place_detail_service,
)
popular_poi_catalog_service = PopularPoiCatalogService(amap_poi_service)
official_content_service = OfficialContentService()
content_ingestion_service = ContentIngestionService(
    popular_poi_catalog_service,
    place_detail_service,
    review_store,
    review_client=tikhub_review_client,
    official_service=official_content_service,
)
mediacrawler_import_service = MediaCrawlerImportService(
    popular_poi_catalog_service,
    place_detail_service,
    data_root=_setting_path(settings.mediacrawler_data_dir),
    run_root=_setting_path(settings.mediacrawler_run_dir),
)
mediacrawler_runner = MediaCrawlerRunner(
    tool_root=_setting_path(settings.mediacrawler_tool_dir),
    run_root=_setting_path(settings.mediacrawler_run_dir),
    timeout_seconds=settings.mediacrawler_timeout_seconds,
)
city_content_pipeline_service = CityContentPipelineService(
    popular_poi_catalog_service,
    place_detail_service,
    mediacrawler_import_service,
    mediacrawler_runner,
    review_store,
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


def get_content_ingestion_service() -> ContentIngestionService:
    return content_ingestion_service


def get_mediacrawler_import_service() -> MediaCrawlerImportService:
    return mediacrawler_import_service


def get_city_content_pipeline_service() -> CityContentPipelineService:
    return city_content_pipeline_service


def get_travel_ai_service() -> TravelAiService:
    return travel_ai_service


def get_travel_plan_generation_service() -> TravelPlanGenerationService:
    return travel_plan_generation_service


def get_ai_plan_job_manager() -> AiPlanJobManager:
    return ai_plan_job_manager
