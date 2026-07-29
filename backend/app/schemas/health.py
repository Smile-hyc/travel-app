from pydantic import BaseModel


class HealthResponse(BaseModel):
    code: int
    message: str
    status: str


class ReviewProviderHealthResponse(BaseModel):
    configured: bool
    activeProvider: str | None = None
    authorizedUgcConfigured: bool
    authorized: bool
