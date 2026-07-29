from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "AI Travel API"
    app_version: str = "0.1.0"
    debug: bool = True
    amap_web_service_key: str = ""
    amap_base_url: str = "https://restapi.amap.com"
    amap_connect_timeout_seconds: float = 5.0
    amap_read_timeout_seconds: float = 8.0
    tikhub_api_key: str = ""
    tikhub_base_url: str = "https://api.tikhub.io"
    tikhub_connect_timeout_seconds: float = 5.0
    tikhub_read_timeout_seconds: float = 12.0
    tikhub_max_sources: int = 6
    ugc_provider_authorized: bool = False
    review_cache_ttl_seconds: int = 21600
    review_empty_cache_ttl_seconds: int = 300
    review_database_path: str = "data/reviews.sqlite3"
    review_author_hash_salt: str = "change-me-in-production"
    content_admin_token: str = ""
    mediacrawler_data_dir: str = "../tools/MediaCrawler/data/xhs/jsonl"
    user_database_path: str = "data/users.sqlite3"
    database_url: str = ""
    upload_dir: str = "uploads"
    upload_max_size_mb: int = 10
    upload_base_url: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    captcha_ttl_seconds: int = 300
    mediacrawler_tool_dir: str = "../tools/MediaCrawler"
    mediacrawler_run_dir: str = "data/mediacrawler-runs"
    mediacrawler_timeout_seconds: int = 10800
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_fallback_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_request_timeout_seconds: float = 240.0
    deepseek_max_output_tokens: int = 8000
    deepseek_reasoning_max_output_tokens: int = 16000
    deepseek_reasoning_effort: str = "high"
    deepseek_temperature: float = 0.35
    dev_cors_origins: str = (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://127.0.0.1:3000,"
        "http://127.0.0.1:5173"
    )

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        if self.dev_cors_origins.strip() == "*":
            return ["*"]
        return [
            origin.strip()
            for origin in self.dev_cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def amap_web_service_key_configured(self) -> bool:
        return bool(self.amap_web_service_key.strip())

    @property
    def deepseek_api_key_configured(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @property
    def deepseek_base_url_configured(self) -> bool:
        return bool(self.deepseek_base_url.strip())

    @property
    def deepseek_configured(self) -> bool:
        return (
            self.deepseek_api_key_configured
            and bool(self.deepseek_model.strip())
            and self.deepseek_base_url_configured
        )

    @property
    def tikhub_configured(self) -> bool:
        return bool(self.tikhub_api_key.strip() and self.tikhub_base_url.strip())

    @property
    def authorized_ugc_configured(self) -> bool:
        return self.ugc_provider_authorized and self.tikhub_configured

    @property
    def active_review_provider(self) -> str | None:
        if self.authorized_ugc_configured:
            return "authorized_ugc"
        return None

    @property
    def content_admin_configured(self) -> bool:
        return len(self.content_admin_token.strip()) >= 16

    @property
    def user_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{self.user_database_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
