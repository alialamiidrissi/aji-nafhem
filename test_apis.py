"""Quick API health check — tests Google Gemini, OpenAI, and OpenRouter endpoints."""

import asyncio
import os
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), ".env"))

# Model names mirrored from agents.py
_GOOGLE_FLASH = "gemini-3-flash-preview"
_OPENAI_FLASH = "gpt-5-mini"
_OPENROUTER_FLASH = os.environ.get("OPENROUTER_FLASH_MODEL", "google/gemini-3-flash-preview")

PING_PROMPT = "Reply with just the word OK."


async def test_google():
    import httpx
    from pydantic_ai import Agent
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    print(f"[Google] Testing {_GOOGLE_FLASH} ...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        client = httpx.AsyncClient(timeout=30.0)
        provider = GoogleProvider(http_client=client)
        agent = Agent(model=GoogleModel(_GOOGLE_FLASH, provider=provider), output_type=str)
        result = await agent.run(PING_PROMPT)
        elapsed = time.perf_counter() - t0
        print(f"OK ({elapsed:.1f}s) — response: {result.output!r}")
        await client.aclose()
        return True
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"FAILED ({elapsed:.1f}s) — {type(e).__name__}: {e}")
        return False


async def test_openai():
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    print(f"[OpenAI] Testing {_OPENAI_FLASH} ...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        provider = OpenAIProvider()
        agent = Agent(model=OpenAIChatModel(_OPENAI_FLASH, provider=provider), output_type=str)
        result = await agent.run(PING_PROMPT)
        elapsed = time.perf_counter() - t0
        print(f"OK ({elapsed:.1f}s) — response: {result.output!r}")
        return True
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"FAILED ({elapsed:.1f}s) — {type(e).__name__}: {e}")
        return False


async def test_openrouter():
    from pydantic_ai import Agent
    from pydantic_ai.models.openrouter import OpenRouterModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    print(f"[OpenRouter] Testing {_OPENROUTER_FLASH} ...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        agent = Agent(
            model=OpenRouterModel(_OPENROUTER_FLASH, provider=OpenRouterProvider()),
            output_type=str,
        )
        result = await agent.run(PING_PROMPT)
        elapsed = time.perf_counter() - t0
        print(f"OK ({elapsed:.1f}s) — response: {result.output!r}")
        return True
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"FAILED ({elapsed:.1f}s) — {type(e).__name__}: {e}")
        return False


async def main():
    print("=" * 50)
    print("API Health Check")
    print("=" * 50)

    google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")

    print(f"GOOGLE_API_KEY    : {'set' if google_key else 'NOT SET'}")
    print(f"OPENAI_API_KEY    : {'set' if openai_key else 'NOT SET'}")
    print(f"OPENROUTER_API_KEY: {'set' if openrouter_key else 'NOT SET'}")
    print()

    results = {}

    if google_key:
        results["google"] = await test_google()
    else:
        print("[Google] Skipped — no API key found")
        results["google"] = None

    if openai_key:
        results["openai"] = await test_openai()
    else:
        print("[OpenAI] Skipped — no API key found")
        results["openai"] = None

    if openrouter_key:
        results["openrouter"] = await test_openrouter()
    else:
        print("[OpenRouter] Skipped — no OPENROUTER_API_KEY found")
        results["openrouter"] = None

    print()
    print("=" * 50)
    for provider, ok in results.items():
        status = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
        print(f"  {provider:12s}: {status}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
