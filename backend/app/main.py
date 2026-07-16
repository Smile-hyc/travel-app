from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai import router as ai_router
from app.api.explore import router as explore_router
from app.api.health import router as health_router
from app.api.routes import router as routes_router
from app.core.config import get_settings
from app.main_state import amap_client

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await amap_client.startup()
    try:
        yield
    finally:
        await amap_client.shutdown()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Welcome to AI Travel API"}


app.include_router(health_router)
app.include_router(explore_router)
app.include_router(routes_router)
app.include_router(ai_router)
