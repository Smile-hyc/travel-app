import asyncio

from app.core.config import Settings
from app.services import deepseek_client as deepseek_module
from app.services.deepseek_client import DeepSeekClient


def test_chat_sends_official_thinking_controls(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "model": "deepseek-v4-flash",
                "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, json, headers):
            captured.update(json)
            return FakeResponse()

    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", FakeAsyncClient)
    client = DeepSeekClient(Settings(deepseek_api_key="test-key"))
    result = asyncio.run(
        client.chat(
            [{"role": "user", "content": "JSON"}],
            thinking_enabled=True,
            reasoning_effort="high",
            json_mode=True,
        ),
    )

    assert result == '{"ok":true}'
    assert captured["thinking"] == {"type": "enabled"}
    assert captured["reasoning_effort"] == "high"
    assert captured["response_format"] == {"type": "json_object"}


def test_reasoning_only_stream_retries_with_structured_fallback_model(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"reasoning_content":"internal"}}]}'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}'
            yield "data: [DONE]"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", FakeAsyncClient)
    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_model="deepseek-v4-flash",
        deepseek_fallback_model="deepseek-chat",
        deepseek_base_url="https://example.invalid/v1",
    )
    client = DeepSeekClient(settings)
    captured: dict[str, str] = {}

    async def fallback_chat(messages, **kwargs):
        captured["model"] = kwargs["model"]
        captured["thinking_enabled"] = kwargs["thinking_enabled"]
        captured["json_mode"] = kwargs["json_mode"]
        assert len(messages) == 2
        assert "返回这一行" in messages[-1]["content"]
        assert "fallbackNoop" in messages[-1]["content"]
        assert "candidatePlaces" not in messages[-1]["content"]
        return '{"kind":"result","proposal":{"changes":[]}}'

    monkeypatch.setattr(client, "chat", fallback_chat)
    timing: list[str] = []
    deltas: list[str] = []

    result = asyncio.run(
        client.chat_stream(
            [{"role": "user", "content": "plan"}],
            on_delta=deltas.append,
            on_timing=lambda phase, elapsed: timing.append(phase),
        ),
    )

    assert captured["model"] == "deepseek-chat"
    assert captured["thinking_enabled"] is False
    assert captured["json_mode"] is True
    assert "reasoning" in timing
    assert result == '{"kind":"result","proposal":{"changes":[]}}'
    assert deltas == [result]


def test_reasoning_only_stream_uses_local_noop_when_compact_fallback_fails(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def aiter_lines(self):
            yield 'data: {"model":"deepseek-v4-flash","choices":[{"delta":{"reasoning_content":"internal"}}]}'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}],"usage":{"completion_tokens":8000}}'
            yield "data: [DONE]"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", FakeAsyncClient)
    client = DeepSeekClient(Settings(deepseek_api_key="test-key"))

    async def failed_fallback(*args, **kwargs):
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail="empty")

    monkeypatch.setattr(client, "chat", failed_fallback)
    deltas: list[str] = []
    result = asyncio.run(client.chat_stream([{"role": "user", "content": "plan"}], on_delta=deltas.append))

    assert '"fallbackNoop":true' in result
    assert deltas == [result]


def test_truncated_visible_stream_appends_local_noop_result(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"{\\\"kind\\\":\\\"event\\\"}\\n"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"{\\\"kind\\\":\\\"res"}}]}'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}'
            yield "data: [DONE]"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", FakeAsyncClient)
    client = DeepSeekClient(Settings(deepseek_api_key="test-key"))
    deltas: list[str] = []
    result = asyncio.run(client.chat_stream([{"role": "user", "content": "plan"}], on_delta=deltas.append))

    assert result.count('"kind":"result"') == 1
    assert '"fallbackNoop":true' in result
    assert '"fallbackNoop":true' in "".join(deltas)
