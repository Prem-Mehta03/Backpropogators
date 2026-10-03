"""Step 1 of setup: prove the API key, model name and network work (no tools involved).

Run from the repo root:  python -m scripts.check_llm_connection
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv

from procedural.llm_client import LLMClient, LLMClientError


def main() -> int:
    """Send one plain message. Returns 0 on success, 1 on failure."""
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    try:
        client = LLMClient()
        reply = client.chat([{"role": "user", "content": "Reply with exactly one word: pong"}])
    except LLMClientError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"model={client.model!r} replied: {reply.content!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
