from __future__ import annotations

import json
from time import perf_counter
from typing import Callable

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
        disable_read_timeout: bool = False,
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
            read=(
                None
                if disable_read_timeout
                else self._settings.ark_request_timeout_seconds if timeout_seconds is None else timeout_seconds
            ),
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

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        on_delta: Callable[[str], None],
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        disable_read_timeout: bool = False,
        on_timing: Callable[[str, int], None] | None = None,
        thinking_type: str | None = None,
    ) -> str:
        """Consume the provider's real SSE token stream.

        Only the model's visible ``content`` is forwarded. Provider-specific
        hidden-reasoning fields are deliberately ignored; planning emits its
        own auditable, structured decision events instead.
        """
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
            "stream": True,
        }
        if thinking_type:
            payload["thinking"] = {"type": thinking_type}
        headers = {
            "Authorization": f"Bearer {self._settings.ark_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        timeout = httpx.Timeout(
            connect=10.0,
            read=(
                None
                if disable_read_timeout
                else self._settings.ark_request_timeout_seconds if timeout_seconds is None else timeout_seconds
            ),
            write=20.0,
            pool=10.0,
        )
        chunks: list[str] = []
        started_at = perf_counter()
        first_content_received = False
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if on_timing is not None:
                        on_timing("connected", round((perf_counter() - started_at) * 1000))
                    if response.status_code >= 400:
                        await response.aread()
                        raise self._to_http_exception(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        choices = data.get("choices") or []
                        delta = choices[0].get("delta") if choices else None
                        content = delta.get("content") if isinstance(delta, dict) else None
                        if not isinstance(content, str) or not content:
                            continue
                        if not first_content_received:
                            first_content_received = True
                            if on_timing is not None:
                                on_timing("first_token", round((perf_counter() - started_at) * 1000))
                        chunks.append(content)
                        on_delta(content)
        except HTTPException:
            raise
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="AI 流式回复超时，请稍后重试。") from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail="无法连接 AI 流式服务。") from exc
        content = "".join(chunks).strip()
        if not content:
            raise HTTPException(status_code=502, detail="AI 流式服务没有返回可用内容。")
        if on_timing is not None:
            on_timing("completed", round((perf_counter() - started_at) * 1000))
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
