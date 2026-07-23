import asyncio

from app.core.config import Settings
from app.services.deepseek_client import DeepSeekClient


async def main() -> int:
    settings = Settings()
    print(f"DeepSeek model: {settings.deepseek_model or '(missing)'}")
    print(f"DeepSeek base URL configured: {settings.deepseek_base_url_configured}")
    print(f"DeepSeek API key configured: {settings.deepseek_api_key_configured}")
    if not settings.deepseek_configured:
        print("DeepSeek verification skipped: missing DEEPSEEK_API_KEY, DEEPSEEK_MODEL, or DEEPSEEK_BASE_URL.")
        return 1

    client = DeepSeekClient(settings)
    try:
        reply = await client.chat(
            [
                {"role": "system", "content": "只回复 DEEPSEEK_OK，不要输出其他内容。"},
                {"role": "user", "content": "请确认服务可用。"},
            ]
        )
    except Exception as exc:
        print(f"DeepSeek verification failed: {exc.__class__.__name__}: {exc}")
        return 1

    print(f"DeepSeek verification response: {reply[:80]}")
    return 0 if "DEEPSEEK_OK" in reply else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
