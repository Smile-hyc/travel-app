import asyncio
import sys

from app.core.config import get_settings
from app.services.ark_client import ArkClient


async def main() -> int:
    settings = get_settings()
    print(f"ARK model: {settings.ark_model or '(missing)'}")
    print(f"ARK base URL configured: {settings.ark_base_url_configured}")
    print(f"ARK API key configured: {settings.ark_api_key_configured}")
    if not settings.ark_configured:
        print("ARK verification skipped: missing ARK_API_KEY, ARK_MODEL, or ARK_BASE_URL.")
        return 2

    client = ArkClient(settings)
    try:
        reply = await client.chat(
            [
                {"role": "system", "content": "只回复 ARK_OK，不要输出其他内容。"},
                {"role": "user", "content": "ping"},
            ],
        )
    except Exception as exc:  # noqa: BLE001 - command-line diagnostic script
        print(f"ARK verification failed: {exc.__class__.__name__}: {exc}")
        return 1

    print(f"ARK verification response: {reply[:80]}")
    return 0 if "ARK_OK" in reply else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
