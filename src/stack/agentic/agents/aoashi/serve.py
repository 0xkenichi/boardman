"""Ao Ashi webhook — what creator_aoashi_academy hosts. House only POSTs here."""
from __future__ import annotations

import os

from gaming.src.stack.agentic.agents.aoashi.runtime import handle_webhook
from gaming.src.stack.agentic.runtime.webhook import serve_builder_webhook

DEFAULT_PORT = 18772


def main() -> None:
    port = int(os.getenv("AOASHI_WEBHOOK_PORT") or DEFAULT_PORT)
    serve_builder_webhook(name="Ao Ashi", pick=handle_webhook, port=port)


if __name__ == "__main__":
    main()