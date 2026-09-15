"""Blue Lock webhook — what creator_bluelock_demo hosts. House only POSTs here."""
from __future__ import annotations

import os

from gaming.src.stack.agentic.agents.bluelock.runtime import handle_webhook
from gaming.src.stack.agentic.runtime.webhook import serve_builder_webhook

DEFAULT_PORT = 18771


def main() -> None:
    port = int(os.getenv("BLUELOCK_WEBHOOK_PORT") or DEFAULT_PORT)
    serve_builder_webhook(name="Blue Lock", pick=handle_webhook, port=port)


if __name__ == "__main__":
    main()