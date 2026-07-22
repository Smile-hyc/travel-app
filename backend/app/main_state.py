from app.core.config import get_settings
from app.services.amap_client import AmapClient
from app.services.amap_poi_service import AmapPoiService
from app.services.amap_route_service import AmapRouteService
from app.services.amap_weather_service import AmapWeatherService
from app.services.ark_client import ArkClient
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

settings = get_settings()
amap_client = AmapClient(settings)
amap_poi_service = AmapPoiService(amap_client)
amap_route_service = AmapRouteService(amap_client)
amap_weather_service = AmapWeatherService(amap_client)
ark_client = ArkClient(settings)
tikhub_review_client = TikhubReviewClient(settings)
review_store = ReviewStore(settings.review_database_path)
initialize_official_directory(review_store)
place_detail_service = PlaceDetailService(
    tikhub_review_client,
    store=review_store,
    author_hash_salt=settings.review_author_hash_salt,
    cache_ttl_seconds=settings.review_cache_ttl_seconds,
    empty_cache_ttl_seconds=settings.review_empty_cache_ttl_seconds,
)
travel_ai_service = TravelAiService(ark_client)
travel_plan_generation_service = TravelPlanGenerationService(
    ark_client,
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
    data_root=settings.mediacrawler_data_dir,
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


def get_travel_ai_service() -> TravelAiService:
    return travel_ai_service


def get_travel_plan_generation_service() -> TravelPlanGenerationService:
    return travel_plan_generation_service


def get_ai_plan_job_manager() -> AiPlanJobManager:
    return ai_plan_job_manager
