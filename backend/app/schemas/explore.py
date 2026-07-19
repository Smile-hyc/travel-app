from enum import Enum

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
