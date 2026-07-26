"""
logging_config.py — Structured JSON logging for sideQuest backend
Integrates with Logtail, Axiom, or any JSON log aggregator.

Usage in main.py or api/__init__.py:
    from logging_config import setup_logging
    setup_logging()
"""

import os
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict

# Choose log provider: "logtail", "axiom", or "json" (stdout)
LOG_PROVIDER = os.getenv("LOG_PROVIDER", "json")


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include extra fields
        for key, value in record.__dict__.items():
            if key not in ("name", "msg", "args", "levelname", "levelno", "pathname",
                          "filename", "module", "exc_info", "exc_text", "stack_info",
                          "lineno", "funcName", "created", "msecs", "relativeCreated",
                          "thread", "threadName", "processName", "process"):
                log_data[key] = value

        return json.dumps(log_data)


class LogtailHandler(logging.Handler):
    """Send logs to Logtail (Datadog Log Management)."""

    def __init__(self, source_token: str, host: str = "https://logtail.logtail.com"):
        super().__init__()
        self.source_token = source_token
        self.host = host
        # Lazy import to avoid requirement if not using
        self.requests = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.requests is None:
                import requests
                self.requests = requests

            log_line = self.format(record)
            response = self.requests.post(
                f"{self.host}/bulk",
                headers={
                    "Authorization": f"Bearer {self.source_token}",
                    "Content-Type": "application/json",
                },
                data=f"{log_line}\n",
                timeout=2,
            )
            if response.status_code >= 400:
                self.handleError(record)
        except Exception:
            self.handleError(record)


class AxiomHandler(logging.Handler):
    """Send logs to Axiom."""

    def __init__(self, api_token: str, dataset: str, org_id: str):
        super().__init__()
        self.api_token = api_token
        self.dataset = dataset
        self.org_id = org_id
        self.requests = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.requests is None:
                import requests
                self.requests = requests

            log_line = self.format(record)
            response = self.requests.post(
                f"https://api.axiom.co/v1/datasets/{self.dataset}/ingest",
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "X-Axiom-Org-Id": self.org_id,
                    "Content-Type": "application/json",
                },
                data=log_line,
                timeout=2,
            )
            if response.status_code >= 400:
                self.handleError(record)
        except Exception:
            self.handleError(record)


def setup_logging() -> logging.Logger:
    """
    Configure structured logging for the application.

    Sets up JSON-formatted logs with optional external aggregation
    via Logtail or Axiom based on environment variables.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove default handlers
    root_logger.handlers.clear()

    # JSON formatter
    json_formatter = JSONFormatter()

    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(json_formatter)
    root_logger.addHandler(console_handler)

    # Optional: Logtail
    if LOG_PROVIDER == "logtail" and os.getenv("LOGTAIL_SOURCE_TOKEN"):
        handler = LogtailHandler(source_token=os.getenv("LOGTAIL_SOURCE_TOKEN"))
        handler.setLevel(logging.INFO)
        handler.setFormatter(json_formatter)
        root_logger.addHandler(handler)
        root_logger.info("[Logging] Logtail handler initialized")

    # Optional: Axiom
    elif LOG_PROVIDER == "axiom" and all([
        os.getenv("AXIOM_API_TOKEN"),
        os.getenv("AXIOM_DATASET"),
        os.getenv("AXIOM_ORG_ID")
    ]):
        handler = AxiomHandler(
            api_token=os.getenv("AXIOM_API_TOKEN"),
            dataset=os.getenv("AXIOM_DATASET"),
            org_id=os.getenv("AXIOM_ORG_ID")
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(json_formatter)
        root_logger.addHandler(handler)
        root_logger.info("[Logging] Axiom handler initialized")

    # Set lower log levels for noisy libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)

    root_logger.info(
        "[Logging] Initialized",
        extra={
            "provider": LOG_PROVIDER,
            "environment": os.getenv("NETWORK", "testnet"),
        }
    )

    return root_logger


# Structured log helper
def log_event(logger: logging.Logger, event: str, **kwargs):
    """
    Log a structured event with key-value pairs.

    Example:
        log_event(logger, "user_login", user_id=user.id, ip=request_ip)
    """
    logger.info(event, extra=kwargs)
