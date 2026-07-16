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
    createdAt: str
    model: str | None = None
