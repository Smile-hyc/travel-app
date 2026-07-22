from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.core.config import Settings, get_settings
from app.main_state import get_content_ingestion_service, get_mediacrawler_import_service
from app.schemas.content import (
    ContentDatabaseStatsResponse,
    ContentIngestionRequest,
    ContentIngestionRunResponse,
    ContentTargetResponse,
    OfficialSyncRequest,
    OfficialSyncResponse,
    PopularPoiSeedResponse,
    CityBootstrapRequest,
    CityBootstrapResponse,
    MediaCrawlerExportResponse,
    MediaCrawlerImportRequest,
    MediaCrawlerImportResponse,
    OfficialSourceResponse,
)
from app.services.content_ingestion_service import (
    ContentIngestionService,
    map_ingestion_run,
    map_stats,
    map_target,
)
from app.services.mediacrawler_import_service import (
    MediaCrawlerImportError,
    MediaCrawlerImportService,
)


router = APIRouter(prefix="/api/content", tags=["content-ingestion"])


def require_content_admin(
    x_content_admin_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.content_admin_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="内容采集管理接口尚未配置 CONTENT_ADMIN_TOKEN。",
        )
    if not x_content_admin_token or not hmac.compare_digest(
        x_content_admin_token,
        settings.content_admin_token.strip(),
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="内容管理令牌无效。")


@router.get("/catalog", response_model=list[PopularPoiSeedResponse])
def get_popular_poi_catalog(
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> list[PopularPoiSeedResponse]:
    return [
        PopularPoiSeedResponse(
            city=seed.city,
            name=seed.name,
            priority=seed.priority,
            tier=seed.tier,
            officialSourceId=seed.official_source_id,
        )
        for seed in service.catalog.seeds
    ]


@router.post(
    "/ingestion/runs",
    response_model=ContentIngestionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_content_admin)],
)
async def start_content_ingestion(
    request: ContentIngestionRequest,
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> ContentIngestionRunResponse:
    run = await service.start_run(
        limit=request.limit,
        force_refresh=request.forceRefresh,
        include_official=request.includeOfficial,
    )
    return ContentIngestionRunResponse.model_validate(map_ingestion_run(run))


@router.get(
    "/ingestion/runs/{run_id}",
    response_model=ContentIngestionRunResponse,
    dependencies=[Depends(require_content_admin)],
)
def get_content_ingestion_run(
    run_id: str,
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> ContentIngestionRunResponse:
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="采集任务不存在。")
    return ContentIngestionRunResponse.model_validate(map_ingestion_run(run))


@router.get(
    "/ingestion/runs",
    response_model=list[ContentIngestionRunResponse],
    dependencies=[Depends(require_content_admin)],
)
def list_content_ingestion_runs(
    limit: int = Query(default=20, ge=1, le=100),
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> list[ContentIngestionRunResponse]:
    return [
        ContentIngestionRunResponse.model_validate(map_ingestion_run(item))
        for item in service.list_runs(limit)
    ]


@router.get(
    "/targets",
    response_model=list[ContentTargetResponse],
    dependencies=[Depends(require_content_admin)],
)
def list_content_targets(
    due_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> list[ContentTargetResponse]:
    return [
        ContentTargetResponse.model_validate(map_target(item))
        for item in service.list_targets(due_only=due_only, limit=limit)
    ]


@router.get(
    "/stats",
    response_model=ContentDatabaseStatsResponse,
    dependencies=[Depends(require_content_admin)],
)
def get_content_stats(
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> ContentDatabaseStatsResponse:
    return ContentDatabaseStatsResponse.model_validate(map_stats(service.stats()))


@router.post(
    "/official/sync",
    response_model=OfficialSyncResponse,
    dependencies=[Depends(require_content_admin)],
)
async def sync_official_content(
    request: OfficialSyncRequest,
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> OfficialSyncResponse:
    return await service.sync_official(request.sourceId)


@router.post(
    "/cities/bootstrap",
    response_model=CityBootstrapResponse,
    dependencies=[Depends(require_content_admin)],
)
async def bootstrap_city_content(
    request: CityBootstrapRequest,
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> CityBootstrapResponse:
    result = await service.bootstrap_city(city_name=request.cityName, limit=request.limit)
    return CityBootstrapResponse.model_validate(result)


@router.get("/official/sources", response_model=list[OfficialSourceResponse])
def list_official_source_directory(
    city_name: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=200, ge=1, le=500),
    service: ContentIngestionService = Depends(get_content_ingestion_service),
) -> list[OfficialSourceResponse]:
    return [
        OfficialSourceResponse(
            sourceId=item["source_id"],
            sourcePoiId=item.get("poi_id"),
            officialName=item["official_name"],
            provinceName=item.get("province_name"),
            cityName=item["city_name"],
            scenicGrade=item.get("scenic_grade"),
            websiteUrl=item.get("website_url"),
            wechatName=item.get("wechat_name"),
            miniProgramName=item.get("mini_program_name"),
            ticketingUrl=item.get("ticketing_url"),
            adapterKind=item["adapter_kind"],
            capabilities=item.get("capabilities", []),
            maxDailyCapacity=item.get("max_daily_capacity"),
            discoveryStatus=item["discovery_status"],
            verifiedAt=item.get("verified_at"),
        )
        for item in service.list_official_sources(city_name=city_name, limit=limit)
    ]


@router.get(
    "/mediacrawler/exports",
    response_model=list[MediaCrawlerExportResponse],
    dependencies=[Depends(require_content_admin)],
)
def list_mediacrawler_exports(
    service: MediaCrawlerImportService = Depends(get_mediacrawler_import_service),
) -> list[MediaCrawlerExportResponse]:
    return [MediaCrawlerExportResponse.model_validate(item) for item in service.list_exports()]


@router.post(
    "/mediacrawler/import",
    response_model=MediaCrawlerImportResponse,
    dependencies=[Depends(require_content_admin)],
)
async def import_mediacrawler_export(
    request: MediaCrawlerImportRequest,
    service: MediaCrawlerImportService = Depends(get_mediacrawler_import_service),
) -> MediaCrawlerImportResponse:
    try:
        result = await service.import_export(
            file_name=request.fileName,
            city_name=request.cityName,
        )
    except MediaCrawlerImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MediaCrawlerImportResponse.model_validate(result)
