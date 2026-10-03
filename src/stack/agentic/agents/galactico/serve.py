"""Galáctico webhook — what creator_galactico_demo hosts. House only POSTs here."""
from __future__ import annotations

import os

from gaming.src.stack.agentic.agents.galactico.runtime import handle_webhook
from gaming.src.stack.agentic.runtime.webhook import serve_builder_webhook

DEFAULT_PORT = 18775


def main() -> None:
    port = int(os.getenv("GALACTICO_WEBHOOK_PORT") or DEFAULT_PORT)
    serve_builder_webhook(name="Galáctico", pick=handle_webhook, port=port)


if __name__ == "__main__":
    main()
