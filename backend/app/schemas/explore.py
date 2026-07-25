from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class PlaceImageSource(str, Enum):
    AMAP = "AMAP"
    PLACEHOLDER = "PLACEHOLDER"


class PlaceImage(BaseModel):
    id: str
    url: str
    thumbnailUrl: str | None = None
    title: str | None = None
    source: PlaceImageSource = PlaceImageSource.AMAP
    sourcePageUrl: str | None = None
    author: str | None = None
    license: str | None = None
    isPrimary: bool = False
    width: int | None = None
    height: int | None = None


class PlaceSummary(BaseModel):
    id: str
    source: str = "AMAP"
    sourcePoiId: str
    name: str
    category: str
    categoryCode: str
    typeName: str | None = None
    typeCode: str | None = None
    address: str | None = None
    provinceName: str | None = None
    cityName: str | None = None
    districtName: str | None = None
    adCode: str | None = None
    cityCode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distanceMeters: int | None = None
    phone: str | None = None
    rating: str | None = None
    costAverage: str | None = None
    images: list[PlaceImage] = Field(default_factory=list)
    coverImageUrl: str | None = None
    imageUrls: list[str] = Field(default_factory=list)
    businessArea: str | None = None
    openingHoursToday: str | None = None
    openingHoursWeek: str | None = None
    officialScenicGrade: str | None = None
    experienceEvidenceCount: int = Field(default=0, ge=0)
    officialReservationRequired: bool = False
    officialReservationNote: str | None = None
    officialClosedDates: list[str] = Field(default_factory=list)
    officialClosureWarning: str | None = None
    officialOpeningHoursByDate: dict[str, str] = Field(default_factory=dict)
    officialAccessNote: str | None = None
    officialMaxDailyCapacity: int | None = Field(default=None, ge=1)
    officialCapacityNote: str | None = None
    officialTicketNote: str | None = None
    crowdRisk: float = Field(default=0.0, ge=0, le=1)
    contentUpdatedAt: str | None = None


class ReviewHighlight(BaseModel):
    title: str
    description: str


class ReviewSource(BaseModel):
    id: str
    platform: str
    title: str
    url: str
    author: str | None = None
    excerpt: str | None = None
    publishedAt: str | None = None
    coverImageUrl: str | None = None
    likeCount: str | None = None
    provider: str | None = None
    evidenceId: str | None = None
    relevanceScore: float | None = Field(default=None, ge=0, le=1)
    anonymousAuthorId: str | None = None
    tags: list[str] = Field(default_factory=list)
    deleted: bool = False


ReviewEnrichmentStatus = Literal["PENDING", "READY", "INSUFFICIENT", "UNAVAILABLE"]


class OfficialNotice(BaseModel):
    type: str
    title: str
    detail: str
    sourceUrl: str
    effectiveAt: str | None = None
    expiresAt: str | None = None


class ExperienceInsightPoint(BaseModel):
    text: str
    evidenceIds: list[str] = Field(default_factory=list)


class ExperienceInsight(BaseModel):
    tag: str
    title: str
    summary: str
    mentionCount: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    evidenceIds: list[str] = Field(default_factory=list)
    points: list[ExperienceInsightPoint] = Field(default_factory=list)
    updatedAt: str
    expiresAt: str


class PlaceFactLayer(BaseModel):
    source: str = "AMAP"
    sourcePoiId: str
    name: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    openingHours: str | None = None
    rating: str | None = None
    phone: str | None = None
    routeAvailable: bool = False
    updatedAt: str
    expiresAt: str


class PlaceOfficialLayer(BaseModel):
    status: Literal["READY", "UNAVAILABLE"] = "UNAVAILABLE"
    notices: list[OfficialNotice] = Field(default_factory=list)
    updatedAt: str | None = None
    sourceId: str | None = None
    officialName: str | None = None
    scenicGrade: str | None = None
    maxDailyCapacity: int | None = None
    websiteUrl: str | None = None
    wechatName: str | None = None
    miniProgramName: str | None = None
    ticketingUrl: str | None = None
    discoveryStatus: str | None = None
    verifiedAt: str | None = None
    sourceType: str | None = None


class PlaceExperienceLayer(BaseModel):
    status: ReviewEnrichmentStatus
    insights: list[ExperienceInsight] = Field(default_factory=list)
    evidenceCount: int = 0
    updatedAt: str | None = None
    expiresAt: str | None = None
    minimumEvidenceCount: int = 1
    summaryVersion: str | None = None


class PlaceDetail(BaseModel):
    summary: PlaceSummary
    images: list[PlaceImage] = Field(default_factory=list)
    openingHours: str | None = None
    phone: str | None = None
    description: str
    reviewTitle: str = "地点亮点"
    reviewSubtitle: str | None = None
    positiveHighlights: list[ReviewHighlight] = Field(default_factory=list)
    negativeHighlights: list[ReviewHighlight] = Field(default_factory=list)
    reviewSources: list[ReviewSource] = Field(default_factory=list)
    sourceLabels: list[str] = Field(default_factory=list)
    relatedPlans: list[str] = Field(default_factory=list)
    hasRealReviews: bool = False
    reviewUpdatedAt: str | None = None
    enrichmentBatchId: str | None = None
    reviewStatus: ReviewEnrichmentStatus = "UNAVAILABLE"
    factLayer: PlaceFactLayer | None = None
    officialLayer: PlaceOfficialLayer = Field(default_factory=PlaceOfficialLayer)
    experienceLayer: PlaceExperienceLayer = Field(
        default_factory=lambda: PlaceExperienceLayer(status="UNAVAILABLE"),
    )


class ReviewBatchRequest(BaseModel):
    places: list[PlaceSummary] = Field(min_length=1, max_length=30)
    forceRefresh: bool = False


class ReviewBatchItem(BaseModel):
    sourcePoiId: str
    status: ReviewEnrichmentStatus
    detail: PlaceDetail | None = None


class ReviewBatchResponse(BaseModel):
    batchId: str
    items: list[ReviewBatchItem]
    pendingCount: int = 0


class ReviewBatchEvent(BaseModel):
    batchId: str
    type: Literal["SNAPSHOT", "PLACE_READY", "PLACE_INSUFFICIENT", "PLACE_UNAVAILABLE", "COMPLETE"]
    sourcePoiId: str | None = None
    status: ReviewEnrichmentStatus | None = None
    detail: PlaceDetail | None = None
    message: str | None = None
    completed: int = 0
    total: int = 0


class PlaceSuggestion(BaseModel):
    id: str
    name: str
    district: str | None = None
    address: str | None = None
    cityName: str | None = None
    adCode: str | None = None
    typeCode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    hasLocation: bool = False


class ReverseGeocodePoint(BaseModel):
    name: str
    formattedAddress: str
    provinceName: str | None = None
    cityName: str | None = None
    districtName: str | None = None
    adCode: str | None = None
    latitude: float
    longitude: float
    matchedPoiWithin50m: bool = False
    distanceMeters: int | None = None


class CitySearchResult(BaseModel):
    id: str
    name: str
    provinceName: str | None = None
    adCode: str
    latitude: float
    longitude: float
    defaultZoom: float = 13.2


class PaginatedPlaces(BaseModel):
    items: list[PlaceSummary]
    page: int
    pageSize: int
    total: int
    hasMore: bool


class AmapHealthResponse(BaseModel):
    configured: bool
    webServiceKeyConfigured: bool


class ExploreWeather(BaseModel):
    city: str
    adCode: str
    weather: str
    dayTemp: str | None = None
    nightTemp: str | None = None
    text: str
    reportTime: str | None = None
