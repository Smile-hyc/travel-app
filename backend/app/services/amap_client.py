from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings

logger = logging.getLogger(__name__)


class AmapClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None
        self._environment_client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=self._settings.amap_connect_timeout_seconds,
                read=self._settings.amap_read_timeout_seconds,
                write=self._settings.amap_read_timeout_seconds,
                pool=self._settings.amap_read_timeout_seconds,
            )
            # 高德国内接口直连更稳定，避免系统 SOCKS 代理造成地点检索超时。
            self._client = httpx.AsyncClient(
                base_url=self._settings.amap_base_url,
                timeout=timeout,
                trust_env=False,
            )
            # Some desktop proxy/VPN clients expose a fake-IP DNS result. Direct
            # access then fails before reaching AMap, while the system proxy can
            # resolve and route it correctly. Keep an environment-aware fallback
            # rather than forcing every deployment through a proxy.
            self._environment_client = httpx.AsyncClient(
                base_url=self._settings.amap_base_url,
                timeout=timeout,
                trust_env=True,
            )

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._environment_client is not None:
            await self._environment_client.aclose()
            self._environment_client = None

    async def _request(self, path: str, params: dict[str, Any]) -> httpx.Response:
        if self._client is None:
            await self.startup()
        assert self._client is not None
        try:
            return await self._client.get(path, params=params)
        except httpx.ConnectError as direct_error:
            if self._environment_client is None:
                raise
            logger.info("AMap direct connection failed; retrying with environment proxy routing")
            try:
                return await self._environment_client.get(path, params=params)
            except httpx.HTTPError as proxy_error:
                raise proxy_error from direct_error

    async def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.amap_web_service_key_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="高德 Web 服务 Key 未配置，请在 backend/.env 中设置 AMAP_WEB_SERVICE_KEY。",
            )
        request_params = {
            **params,
            "key": self._settings.amap_web_service_key.strip(),
        }

        try:
            payload: dict[str, Any] = {}
            for attempt in range(3):
                response = await self._request(path, request_params)
                response.raise_for_status()
                payload = response.json()
                if str(payload.get("infocode", "")) != "10021" or attempt == 2:
                    break
                await asyncio.sleep(0.2 * (attempt + 1))
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="高德地点服务请求超时，请稍后重试。") from exc
        except httpx.HTTPError as exc:
            logger.warning("AMap HTTP request failed: %s", exc)
            raise HTTPException(status_code=502, detail="高德地点服务暂时不可用。") from exc
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="高德地点服务响应格式异常。") from exc

        status_value = str(payload.get("status", ""))
        if status_value != "1":
            info = str(payload.get("info", ""))
            infocode = str(payload.get("infocode", ""))
            logger.warning("AMap API error: info=%s infocode=%s", info, infocode)
            raise HTTPException(status_code=502, detail=_friendly_amap_error(infocode))

        return payload

    async def get_raw(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.amap_web_service_key_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="高德 Web 服务 Key 未配置，请在 backend/.env 中设置 AMAP_WEB_SERVICE_KEY。",
            )
        request_params = {
            **params,
            "key": self._settings.amap_web_service_key.strip(),
        }

        try:
            response = await self._request(path, request_params)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="高德路线服务请求超时，请稍后重试。") from exc
        except httpx.HTTPError as exc:
            logger.warning("AMap HTTP request failed: %s", exc)
            raise HTTPException(status_code=502, detail="高德路线服务暂时不可用。") from exc
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="高德路线服务响应格式异常。") from exc


def _friendly_amap_error(infocode: str) -> str:
    if infocode in {"10001", "10002", "10003", "10009"}:
        return "高德地点服务鉴权失败，请检查 Web 服务 Key。"
    if infocode in {"10004", "10021", "10044", "10045", "20011", "20012"}:
        return "搜索请求过于频繁或配额不足，请稍后再试。"
    return "高德地点服务暂时不可用。"
