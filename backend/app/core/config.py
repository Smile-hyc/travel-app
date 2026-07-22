from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    rnote_api_key: str = ""
    rnote_base_url: str = "https://rnote.dev"
    rnote_connect_timeout_seconds: float = 5.0
    rnote_read_timeout_seconds: float = 15.0
    rnote_max_sources: int = 5
    review_cache_ttl_seconds: int = 21600
    review_empty_cache_ttl_seconds: int = 300
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_request_timeout_seconds: float = 240.0
    deepseek_max_output_tokens: int = 8000
    deepseek_temperature: float = 0.35
    dev_cors_origins: str = (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://127.0.0.1:3000,"
        "http://127.0.0.1:5173"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
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
    def rnote_configured(self) -> bool:
        return bool(self.rnote_api_key.strip() and self.rnote_base_url.strip())

    @property
    def active_review_provider(self) -> str | None:
        if self.rnote_configured:
            return "rnote"
        if self.tikhub_configured:
            return "tikhub"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
