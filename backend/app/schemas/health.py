from pydantic import BaseModel


class HealthResponse(BaseModel):
    code: int
    message: str
    status: str

