from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings


class ArkClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def model_name(self) -> str:
        return self._settings.ark_model

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        if not self._settings.ark_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI 服务尚未配置，请检查 ARK_API_KEY、ARK_MODEL 和 ARK_BASE_URL。",
            )

        url = f"{self._settings.ark_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._settings.ark_model,
            "messages": messages,
            "temperature": self._settings.ark_temperature if temperature is None else temperature,
            "max_tokens": self._settings.ark_max_output_tokens if max_tokens is None else max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.ark_api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(
            connect=10.0,
            read=self._settings.ark_request_timeout_seconds if timeout_seconds is None else timeout_seconds,
            write=20.0,
            pool=10.0,
        )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI 回复超时，请稍后重试，或把问题问得更具体一些。",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="无法连接 AI 服务，请检查网络或 Ark Base URL。",
            ) from exc

        if response.status_code >= 400:
            raise self._to_http_exception(response)

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI 服务没有返回可用回复。",
            )

        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI 服务返回了空回复。",
            )
        return content

    def _to_http_exception(self, response: httpx.Response) -> HTTPException:
        detail = "AI 服务调用失败，请稍后重试。"
        if response.status_code in {401, 403}:
            detail = "AI 服务鉴权失败，请检查 Ark API Key 或模型权限。"
        elif response.status_code == 404:
            detail = "AI 模型或接口不存在，请检查 ARK_MODEL 和 ARK_BASE_URL。"
        elif response.status_code == 429:
            detail = "AI 服务额度或频率受限，请稍后重试。"
        elif response.status_code >= 500:
            detail = "AI 服务暂时不可用，请稍后重试。"

        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )
