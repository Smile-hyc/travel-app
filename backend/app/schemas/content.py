from __future__ import annotations

from pydantic import BaseModel, Field


class PopularPoiSeedResponse(BaseModel):
    city: str
    name: str
    priority: int
    tier: str
    officialSourceId: str | None = None


class ContentIngestionRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=30)
    forceRefresh: bool = False
    includeOfficial: bool = True


class ContentIngestionRunResponse(BaseModel):
    runId: str
    provider: str
    status: str
    targetCount: int = 0
    fetchedCount: int = 0
    acceptedCount: int = 0
    savedCount: int = 0
    skippedCount: int = 0
    failedCount: int = 0
    startedAt: str
    finishedAt: str | None = None
    error: str | None = None


class ContentTargetResponse(BaseModel):
    sourcePoiId: str
    priority: int
    tier: str
    refreshIntervalHours: int
    lastCollectedAt: str | None = None
    nextCollectionAt: str | None = None
    status: str
    lastError: str | None = None
    active: bool = True


class ContentDatabaseStatsResponse(BaseModel):
    placeCount: int = 0
    activeEvidenceCount: int = 0
    aggregateCount: int = 0
    activeTargetCount: int = 0
    dueTargetCount: int = 0
    ingestionRunCount: int = 0
    runningIngestionCount: int = 0
    officialSourceCount: int = 0
    officialNoticeCount: int = 0
    rankedCityCount: int = 0
    rankedPoiCount: int = 0
    cityCollectionRunCount: int = 0
    runningCityCollectionCount: int = 0


class OfficialSyncRequest(BaseModel):
    sourceId: str = Field(min_length=2, max_length=40)


class OfficialSyncResponse(BaseModel):
    sourceId: str
    sourcePoiId: str
    placeName: str
    savedCount: int
    status: str
    message: str | None = None


class CityBootstrapRequest(BaseModel):
    cityName: str = Field(min_length=2, max_length=40)
    limit: int = Field(default=12, ge=1, le=25)


class CityBootstrapPlace(BaseModel):
    sourcePoiId: str
    name: str
    rating: str | None = None
    districtName: str | None = None
    crawlerKeyword: str
    officialSourceId: str | None = None


class CityBootstrapResponse(BaseModel):
    cityName: str
    count: int
    places: list[CityBootstrapPlace]


class OfficialSourceResponse(BaseModel):
    sourceId: str
    sourcePoiId: str | None = None
    officialName: str
    provinceName: str | None = None
    cityName: str
    scenicGrade: str | None = None
    websiteUrl: str | None = None
    wechatName: str | None = None
    miniProgramName: str | None = None
    ticketingUrl: str | None = None
    adapterKind: str
    capabilities: list[str] = Field(default_factory=list)
    maxDailyCapacity: int | None = None
    discoveryStatus: str
    verifiedAt: str | None = None


class MediaCrawlerExportResponse(BaseModel):
    fileName: str
    sizeBytes: int
    modifiedAt: str


class MediaCrawlerImportRequest(BaseModel):
    fileName: str = Field(min_length=6, max_length=180)
    cityName: str = Field(min_length=2, max_length=40)


class MediaCrawlerImportedPlace(BaseModel):
    sourcePoiId: str
    placeName: str
    fetchedCount: int
    acceptedCount: int
    status: str


class MediaCrawlerImportResponse(BaseModel):
    fileName: str
    cityName: str
    rowCount: int
    keywordCount: int
    imported: list[MediaCrawlerImportedPlace]
    missingKeywords: list[str]
    fetchedCount: int
    acceptedCount: int


class CityContentRunRequest(BaseModel):
    cityName: str = Field(min_length=2, max_length=40)
    top: int = Field(default=12, ge=1, le=25)
    candidateLimit: int = Field(default=30, ge=1, le=60)
    headless: bool = False
    forceRefresh: bool = False


class CityContentRunItemResponse(BaseModel):
    sourcePoiId: str
    placeName: str
    rank: int
    queryKeyword: str
    status: str
    fetchedCount: int = 0
    acceptedCount: int = 0
    error: str | None = None


class CityContentRunResponse(BaseModel):
    runId: str
    cityAdcode: str
    cityName: str
    rankingVersion: str
    status: str
    candidateLimit: int
    retainLimit: int
    displayLimit: int
    targetCount: int
    fetchedCount: int = 0
    acceptedCount: int = 0
    failedCount: int = 0
    outputPath: str | None = None
    error: str | None = None
    startedAt: str
    finishedAt: str | None = None
    items: list[CityContentRunItemResponse] = Field(default_factory=list)


class CityRankingPlaceResponse(BaseModel):
    rank: int
    sourcePoiId: str
    name: str
    rating: str | None = None
    districtName: str | None = None
    crawlerKeyword: str


class CityContentPlanResponse(BaseModel):
    cityAdcode: str
    cityName: str
    provinceName: str | None = None
    rankingVersion: str
    count: int
    places: list[CityRankingPlaceResponse]
