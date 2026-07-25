from __future__ import annotations

from collections.abc import AsyncGenerator
import json
import logging
from time import perf_counter
from typing import Callable

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings


logger = logging.getLogger(__name__)

LOCAL_NOOP_PROPOSAL = (
    '{"kind":"result","proposal":{"changes":[],"fallbackNoop":true,'
    '"travelerExplanation":"AI未提出通过验证的局部修改，保留可执行草案。"}}'
)


class DeepSeekClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def model_name(self) -> str:
        return self._settings.deepseek_model

    @property
    def fallback_model_name(self) -> str:
        return self._settings.deepseek_fallback_model.strip() or self._settings.deepseek_model

    @property
    def reasoning_max_output_tokens(self) -> int:
        return max(1000, self._settings.deepseek_reasoning_max_output_tokens)

    @property
    def reasoning_effort(self) -> str:
        effort = self._settings.deepseek_reasoning_effort.strip().lower()
        return effort if effort in {"high", "max"} else "high"

    async def chat_stream_chunks(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用 AI API，逐 chunk yield 文本内容。"""
        if not self._settings.deepseek_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI 服务尚未配置，请检查 DEEPSEEK_API_KEY、DEEPSEEK_MODEL 和 DEEPSEEK_BASE_URL。",
            )

        url = f"{self._settings.deepseek_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._settings.deepseek_model,
            "messages": messages,
            "temperature": self._settings.deepseek_temperature if temperature is None else temperature,
            "max_tokens": self._settings.deepseek_max_output_tokens if max_tokens is None else max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(
            connect=10.0,
            read=self._settings.deepseek_request_timeout_seconds if timeout_seconds is None else timeout_seconds,
            write=20.0,
            pool=10.0,
        )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        # 读取完整响应体以构建错误信息
                        body = await response.aread()
                        raise self._status_to_exception(response.status_code, body)

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line.removeprefix("data:").strip()
                        if data_str == "[DONE]":
                            return
                        try:
                            import json

                            data = json.loads(data_str)
                        except (ValueError, TypeError):
                            continue
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield content
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI 回复超时，请稍后重试，或把问题问得更具体一些。",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="无法连接 AI 服务，请检查网络或 DeepSeek Base URL。",
            ) from exc

    def _status_to_exception(self, status_code: int, body: bytes) -> HTTPException:
        detail = "AI 服务调用失败，请稍后重试。"
        if status_code in {401, 403}:
            detail = "AI 服务鉴权失败，请检查 DeepSeek API Key 或模型权限。"
        elif status_code == 404:
            detail = "AI 模型或接口不存在，请检查 DEEPSEEK_MODEL 和 DEEPSEEK_BASE_URL。"
        elif status_code == 429:
            detail = "AI 服务额度或频率受限，请稍后重试。"
        elif status_code >= 500:
            detail = "AI 服务暂时不可用，请稍后重试。"

        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_seconds: float | None = None,
        disable_read_timeout: bool = False,
        model: str | None = None,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
        json_mode: bool = False,
    ) -> str:
        if not self._settings.deepseek_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI 服务尚未配置，请检查 DEEPSEEK_API_KEY、DEEPSEEK_MODEL 和 DEEPSEEK_BASE_URL。",
            )

        url = f"{self._settings.deepseek_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model or self._settings.deepseek_model,
            "messages": messages,
            "temperature": self._settings.deepseek_temperature if temperature is None else temperature,
            "max_tokens": self._settings.deepseek_max_output_tokens if max_tokens is None else max_tokens,
        }
        if thinking_enabled is not None:
            payload["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}
        if thinking_enabled and reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort if reasoning_effort in {"high", "max"} else "high"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self._settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(
            connect=10.0,
            read=(
                None
                if disable_read_timeout
                else self._settings.deepseek_request_timeout_seconds if timeout_seconds is None else timeout_seconds
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
                detail="无法连接 AI 服务，请检查网络或 DeepSeek Base URL。",
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

        choice = choices[0]
        message = choice.get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            finish_reason = str(choice.get("finish_reason") or "unknown")
            reasoning = message.get("reasoning_content")
            reasoning_received = isinstance(reasoning, str) and bool(reasoning.strip())
            logger.warning(
                "DeepSeek returned no visible content: requested_model=%s response_model=%s "
                "reasoning_received=%s finish_reason=%s completion_tokens=%s",
                payload["model"],
                data.get("model") or "unknown",
                reasoning_received,
                finish_reason,
                (data.get("usage") or {}).get("completion_tokens"),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI 服务本次没有返回可用建议，当前可继续使用已生成的规则草案。",
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
        model: str | None = None,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        """Consume the provider's real SSE token stream.

        Only the model's visible ``content`` is forwarded. Provider-specific
        hidden-reasoning fields are deliberately ignored; planning emits its
        own auditable, structured decision events instead.
        """
        if not self._settings.deepseek_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI 服务尚未配置，请检查 DEEPSEEK_API_KEY、DEEPSEEK_MODEL 和 DEEPSEEK_BASE_URL。",
            )
        url = f"{self._settings.deepseek_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model or self._settings.deepseek_model,
            "messages": messages,
            "temperature": self._settings.deepseek_temperature if temperature is None else temperature,
            "max_tokens": self._settings.deepseek_max_output_tokens if max_tokens is None else max_tokens,
            "stream": True,
        }
        if thinking_enabled is not None:
            payload["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}
        if thinking_enabled and reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort if reasoning_effort in {"high", "max"} else "high"
        headers = {
            "Authorization": f"Bearer {self._settings.deepseek_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        timeout = httpx.Timeout(
            connect=10.0,
            read=(
                None
                if disable_read_timeout
                else self._settings.deepseek_request_timeout_seconds if timeout_seconds is None else timeout_seconds
            ),
            write=20.0,
            pool=10.0,
        )
        chunks: list[str] = []
        started_at = perf_counter()
        first_content_received = False
        reasoning_received = False
        finish_reason: str | None = None
        response_model: str | None = None
        completion_tokens: int | None = None
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
                        response_model = data.get("model") or response_model
                        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
                        completion_tokens = usage.get("completion_tokens") or completion_tokens
                        choice = choices[0] if choices else {}
                        finish_reason = choice.get("finish_reason") or finish_reason
                        delta = choice.get("delta") if choices else None
                        reasoning = delta.get("reasoning_content") if isinstance(delta, dict) else None
                        if isinstance(reasoning, str) and reasoning and not reasoning_received:
                            reasoning_received = True
                            if on_timing is not None:
                                on_timing("reasoning", round((perf_counter() - started_at) * 1000))
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
        if content and finish_reason == "length":
            logger.warning(
                "DeepSeek visible stream was truncated; appending local no-op proposal: "
                "requested_model=%s response_model=%s completion_tokens=%s",
                payload["model"],
                response_model or "unknown",
                completion_tokens,
            )
            separator = "" if content.endswith("\n") else "\n"
            recovery = separator + LOCAL_NOOP_PROPOSAL + "\n"
            content += recovery
            on_delta(recovery)
        if not content:
            # Some DeepSeek reasoning-capable models can consume a short
            # streaming token budget with hidden reasoning and finish without
            # emitting visible ``content``. Retry once through the ordinary
            # completion endpoint with the configured full output budget so a
            # valid plan is not discarded after the executable draft exists.
            fallback_started_at = perf_counter()
            retry_messages = [
                {
                    "role": "system",
                    "content": "你是JSON响应器。不要分析、解释或输出Markdown，只返回用户指定的一行JSON。",
                },
                {
                    "role": "user",
                    "content": (
                        "返回这一行，不得添加其他内容："
                        + LOCAL_NOOP_PROPOSAL
                    ),
                },
            ]
            try:
                content = await self.chat(
                    retry_messages,
                    max_tokens=max(
                        self._settings.deepseek_max_output_tokens,
                        max_tokens or 0,
                    ),
                    temperature=temperature,
                    timeout_seconds=timeout_seconds,
                    disable_read_timeout=disable_read_timeout,
                    model=self._settings.deepseek_fallback_model.strip() or self._settings.deepseek_model,
                    thinking_enabled=False,
                    json_mode=True,
                )
            except HTTPException as exc:
                if reasoning_received:
                    logger.warning(
                        "DeepSeek reasoning-only response and compact fallback both failed: "
                        "requested_model=%s response_model=%s finish_reason=%s "
                        "completion_tokens=%s fallback_status=%s; using local no-op proposal",
                        payload["model"],
                        response_model or "unknown",
                        finish_reason or "unknown",
                        completion_tokens,
                        exc.status_code,
                    )
                    content = LOCAL_NOOP_PROPOSAL
                else:
                    raise
            if on_timing is not None:
                on_timing("first_token", round((perf_counter() - fallback_started_at) * 1000))
            on_delta(content)
        if on_timing is not None:
            on_timing("completed", round((perf_counter() - started_at) * 1000))
        return content

    def _to_http_exception(self, response: httpx.Response) -> HTTPException:
        detail = "AI 服务调用失败，请稍后重试。"
        if response.status_code in {401, 403}:
            detail = "AI 服务鉴权失败，请检查 DeepSeek API Key 或模型权限。"
        elif response.status_code == 404:
            detail = "AI 模型或接口不存在，请检查 DEEPSEEK_MODEL 和 DEEPSEEK_BASE_URL。"
        elif response.status_code == 429:
            detail = "AI 服务额度或频率受限，请稍后重试。"
        elif response.status_code >= 500:
            detail = "AI 服务暂时不可用，请稍后重试。"

        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )
