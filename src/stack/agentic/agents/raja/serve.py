"""Raja webhook — what creator_raja_lab hosts. House only POSTs here."""
from __future__ import annotations

import os

from gaming.src.stack.agentic.agents.raja.runtime import handle_webhook
from gaming.src.stack.agentic.runtime.webhook import serve_builder_webhook

DEFAULT_PORT = 18761


def main() -> None:
    port = int(os.getenv("RAJA_WEBHOOK_PORT") or DEFAULT_PORT)
    serve_builder_webhook(name="Raja", pick=handle_webhook, port=port)


if __name__ == "__main__":
    main()
