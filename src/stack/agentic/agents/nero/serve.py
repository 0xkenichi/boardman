"""Nero webhook — what creator_nero_forge hosts. House only POSTs here."""
from __future__ import annotations

import os

from gaming.src.stack.agentic.agents.nero.runtime import handle_webhook
from gaming.src.stack.agentic.runtime.webhook import serve_builder_webhook

DEFAULT_PORT = 18762


def main() -> None:
    port = int(os.getenv("NERO_WEBHOOK_PORT") or DEFAULT_PORT)
    serve_builder_webhook(name="Nero", pick=handle_webhook, port=port)


if __name__ == "__main__":
    main()
