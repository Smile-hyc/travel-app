import asyncio

import httpx

from app.core.config import Settings
from app.services.amap_client import AmapClient


def test_amap_client_retries_connect_failure_with_environment_routing() -> None:
    direct_calls = 0
    environment_calls = 0

    def direct_handler(request: httpx.Request) -> httpx.Response:
        nonlocal direct_calls
        direct_calls += 1
        raise httpx.ConnectError("direct connection failed", request=request)

    def environment_handler(request: httpx.Request) -> httpx.Response:
        nonlocal environment_calls
        environment_calls += 1
        return httpx.Response(200, json={"status": "1", "pois": []}, request=request)

    async def run() -> dict:
        client = AmapClient(Settings(amap_web_service_key="test-key"))
        client._client = httpx.AsyncClient(
            base_url="https://restapi.amap.com",
            transport=httpx.MockTransport(direct_handler),
        )
        client._environment_client = httpx.AsyncClient(
            base_url="https://restapi.amap.com",
            transport=httpx.MockTransport(environment_handler),
        )
        try:
            return await client.get("/v3/place/text", {"keywords": "北京"})
        finally:
            await client.shutdown()

    payload = asyncio.run(run())

    assert payload["status"] == "1"
    assert direct_calls == 1
    assert environment_calls == 1
