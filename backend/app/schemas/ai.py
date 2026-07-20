from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AiHealthResponse(BaseModel):
    configured: bool
    apiKeyConfigured: bool
    model: str | None = None
    baseUrlConfigured: bool


class AiHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AiPlaceContext(BaseModel):
    itemId: str
    sourcePoiId: str | None = None
    name: str
    category: str | None = None
    typeName: str | None = None
    address: str | None = None
    cityName: str | None = None
    districtName: str | None = None
    imageUrl: str | None = None
    dayIndex: int | None = None
    visitOrder: int | None = None
    suggestedStart: str | None = None
    suggestedEnd: str | None = None


class AiDayContext(BaseModel):
    dayIndex: int
    title: str | None = None
    places: list[AiPlaceContext] = Field(default_factory=list)


class AiWeatherContext(BaseModel):
    city: str | None = None
    text: str | None = None
    weather: str | None = None
    dayTemp: str | None = None
    nightTemp: str | None = None
    reportTime: str | None = None


class AiRouteSummary(BaseModel):
    dayIndex: int
    mode: str | None = None
    placeCount: int = 0
    totalDistanceMeters: int | None = None
    totalDurationSeconds: int | None = None
    warnings: list[str] = Field(default_factory=list)


class AiPlanContext(BaseModel):
    id: str | None = None
    title: str | None = None
    destination: str | None = None
    dateRange: str | None = None
    revision: int | None = None
    updatedAt: int | None = None
    days: list[AiDayContext] = Field(default_factory=list)
    unplannedPlaces: list[AiPlaceContext] = Field(default_factory=list)
    weather: AiWeatherContext | None = None
    routeSummaries: list[AiRouteSummary] = Field(default_factory=list)


class AiChatRequest(BaseModel):
    conversationId: str | None = None
    planId: str | None = None
    message: str = Field(min_length=1, max_length=2000)
    history: list[AiHistoryMessage] = Field(default_factory=list, max_length=12)
    context: AiPlanContext | None = None


AiSuggestedActionType = Literal[
    "MOVE_PLACE_TO_DAY",
    "REORDER_PLACE",
    "ASSIGN_UNPLANNED_PLACE",
    "MOVE_TO_UNPLANNED",
]


class AiSuggestedAction(BaseModel):
    id: str
    type: AiSuggestedActionType
    placeItemId: str
    fromDayIndex: int | None = None
    toDayIndex: int | None = None
    fromPosition: int | None = None
    toPosition: int | None = None
    reason: str | None = None
    requiresRouteRefresh: bool = True
    affectedDayIndexes: list[int] = Field(default_factory=list)


# ---------- Card models ----------


class AiCardType(str, Enum):
    LINK = "LINK"
    ITINERARY_OPTIMIZATION = "ITINERARY_OPTIMIZATION"


class AiLinkActionType(str, Enum):
    NAVIGATE_TO_CREATE_PLAN = "NAVIGATE_TO_CREATE_PLAN"


class AiCardPlaceRef(BaseModel):
    """卡片中引用的地点 — 前端用 itemId 从 plan 中解析完整信息"""

    itemId: str
    note: str = ""


class AiCardDay(BaseModel):
    day_index: int
    title: str = ""
    place_refs: list[AiCardPlaceRef] = Field(default_factory=list)


class AiLinkCardPayload(BaseModel):
    action_type: AiLinkActionType = AiLinkActionType.NAVIGATE_TO_CREATE_PLAN


class AiLinkCard(BaseModel):
    id: str
    type: Literal["LINK"] = "LINK"
    title: str
    subtitle: str | None = None
    payload: AiLinkCardPayload = Field(default_factory=AiLinkCardPayload)


class AiItineraryCard(BaseModel):
    id: str
    type: Literal["ITINERARY_OPTIMIZATION"] = "ITINERARY_OPTIMIZATION"
    title: str
    days: list[AiCardDay] = Field(default_factory=list)


AiCard = AiLinkCard | AiItineraryCard


class AiChatResponse(BaseModel):
    conversationId: str
    messageId: str
    message: str
    quickReplies: list[str] = Field(default_factory=list)
    referencedPlaceItemIds: list[str] = Field(default_factory=list)
    actionSetId: str | None = None
    planRevision: int | None = None
    suggestedActions: list[AiSuggestedAction] = Field(default_factory=list)
    actionWarnings: list[str] = Field(default_factory=list)
    cards: list[AiCard] = Field(default_factory=list)
    createdAt: str
    model: str | None = None


class AiPlanGenerationRequest(BaseModel):
    destination: str = Field(min_length=1, max_length=60)
    dateRange: str = Field(min_length=1, max_length=80)
    dayCount: int = Field(ge=1, le=10)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    freeText: str | None = Field(default=None, max_length=240)
    arrivalStation: str | None = Field(default=None, max_length=60)
    hotelName: str | None = Field(default=None, max_length=80)
    pace: Literal["RELAXED", "BALANCED", "INTENSIVE"] = "BALANCED"
    transportPreference: Literal["MIXED", "WALK", "TRANSIT", "DRIVE"] = "MIXED"
    dailyStart: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    dailyEnd: str = Field(default="20:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    clientRequestId: str | None = Field(default=None, min_length=8, max_length=80)


class AiGeneratedPlace(BaseModel):
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
    latitude: float
    longitude: float
    thumbnailUrl: str | None = None
    imageUrls: list[str] = Field(default_factory=list)
    phone: str | None = None
    rating: str | None = None
    costAverage: str | None = None
    businessArea: str | None = None
    openingHoursToday: str | None = None
    openingHoursWeek: str | None = None
    scheduleVerified: bool = False
    suggestedStart: str
    suggestedEnd: str
    note: str


class AiGeneratedDay(BaseModel):
    dayIndex: int
    title: str
    summary: str
    places: list[AiGeneratedPlace] = Field(default_factory=list)
    estimatedDistanceKm: float = 0.0
    intensity: Literal["轻松", "适中", "充实"] = "适中"


class AiPlanQuality(BaseModel):
    realPoiRatio: float = 1.0
    duplicatePlaceCount: int = 0
    totalPlaceCount: int = 0
    usedFallback: bool = False
    dataSources: list[str] = Field(default_factory=lambda: ["AMAP", "ARK"])


class AiPlanGenerationResponse(BaseModel):
    requestId: str
    title: str
    destination: str
    dateRange: str
    dayCount: int
    preferences: list[str] = Field(default_factory=list)
    days: list[AiGeneratedDay] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generatedAt: str
    model: str | None = None
    quality: AiPlanQuality = Field(default_factory=AiPlanQuality)


AiPlanJobState = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]

AiPlanProgressEventType = Literal[
    "ANALYSIS",
    "DAY_STARTED",
    "PLACE_ADDED",
    "DAY_COMPLETED",
    "PLAN_REFINED",
]


class AiPlanProgressEvent(BaseModel):
    sequence: int = Field(ge=1)
    type: AiPlanProgressEventType
    message: str = Field(min_length=1, max_length=160)
    dayIndex: int | None = Field(default=None, ge=1)
    placeId: str | None = None
    createdAt: str


class AiPlanJobStatusResponse(BaseModel):
    jobId: str
    status: AiPlanJobState
    progress: int = Field(ge=0, le=100)
    stage: str
    completedDays: int = 0
    totalDays: int
    activeDayIndex: int | None = None
    partialDays: list[AiGeneratedDay] = Field(default_factory=list)
    events: list[AiPlanProgressEvent] = Field(default_factory=list)
    result: AiPlanGenerationResponse | None = None
    error: str | None = None
    createdAt: str
    updatedAt: str
