"""Sheila webhook — what creator_sheila_lab hosts. House only POSTs here."""
from __future__ import annotations

import os

from gaming.src.stack.agentic.agents.sheila.runtime import handle_webhook
from gaming.src.stack.agentic.runtime.webhook import serve_builder_webhook

DEFAULT_PORT = 18764


def main() -> None:
    port = int(os.getenv("SHEILA_WEBHOOK_PORT") or DEFAULT_PORT)
    serve_builder_webhook(name="Sheila", pick=handle_webhook, port=port)


if __name__ == "__main__":
    main()
