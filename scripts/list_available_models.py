"""Print the model IDs your Groq key can use, so LLM_MODEL can be set correctly.

Run from the repo root:  python -m scripts.list_available_models
"""

from __future__ import annotations

import os

from dotenv import load_dotenv


def main() -> int:
    """List model IDs from the OpenAI-compatible /models endpoint. Returns 0 on success."""
    load_dotenv()
    key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
    if not key:
        print("FAILED: set GROQ_API_KEY in .env first")
        return 1
    from openai import OpenAI, OpenAIError

    client = OpenAI(
        api_key=key,
        base_url=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
    )
    try:
        ids = sorted(m.id for m in client.models.list().data)
    except OpenAIError as exc:  # covers connection, auth and rate-limit failures
        print(f"FAILED: {exc}")
        return 1
    print("\n".join(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
