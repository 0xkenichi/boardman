"""
sideQuest Safe Error Responses

ELON FOCUS (2026-06-13): Zero tolerance for leaking internal errors to users.

This is the single source of truth for how the backend reports errors to clients.

Rules:
- Never put str(e), traceback, DB column names, JWT details, file paths, or function names into the HTTP response body for 5xx.
- Always log the real details server-side with request correlation.
- 4xx errors can be more specific (client did something wrong) but still no internals.
- Every error log must include request_id when available so we can trace in logs/Sentry.

Usage:
    from utils.errors import safe_error_response, register_error_handlers

    # In a route
    except Exception as e:
        raise safe_error_response(500, "Failed to load quests", e)

    # At app startup
    register_error_handlers(app)
"""

import logging
import traceback
from typing import Optional, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class SafeHTTPException(HTTPException):
    """Marker exception so our handler can distinguish intentional safe errors."""
    pass


def safe_error_response(
    status_code: int,
    public_message: str,
    original_error: Optional[Exception] = None,
    *,
    request_id: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> SafeHTTPException:
    """
    Create a safe HTTPException.

    - public_message is what the client will see.
    - original_error (if provided) is logged with full details + request_id.
    - Never leaks internals.

    Example:
        raise safe_error_response(500, "Could not join quest", e, request_id=req_id)
    """
    if status_code >= 500:
        # Log the real problem
        req = f" [request_id={request_id}]" if request_id else ""
        log_extra = {"request_id": request_id, "status": status_code}
        if extra:
            log_extra.update(extra)

        error_str = str(original_error) if original_error else "unknown"
        logger.error(
            "Safe error response triggered%s: %s | original=%s",
            req,
            public_message,
            error_str,
            exc_info=original_error,
            extra=log_extra,
        )
        if original_error:
            # Also dump a clean traceback in the log (Sentry will catch this too)
            logger.debug("Full traceback for %s:\n%s", public_message, traceback.format_exc())

    # For 4xx we can be slightly more helpful, but still no raw exception text in prod
    detail = public_message
    if status_code < 500 and original_error and not isinstance(original_error, HTTPException):
        # For client errors we sometimes want to surface a clean validation message
        # but we still never dump raw Python exceptions.
        pass

    return SafeHTTPException(status_code=status_code, detail=detail)


def register_error_handlers(app: FastAPI) -> None:
    """
    Register the global handler that turns uncaught exceptions into safe responses.

    Call this once during app creation (in api.py).
    """
    @app.exception_handler(Exception)
    async def _global_safe_handler(request: Request, exc: Exception):
        # Try to pull request_id if our middleware put it on the request state
        request_id = getattr(request.state, "request_id", None)

        if isinstance(exc, HTTPException):
            # Already a proper HTTP error (including our Safe ones). Pass through.
            # We still log 5xx at error level.
            if exc.status_code >= 500:
                logger.error(
                    "HTTPException 5xx [request_id=%s]: %s",
                    request_id,
                    exc.detail,
                    exc_info=exc,
                )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )

        # Unknown exception — treat as 500, safe message
        public_msg = "An unexpected error occurred. Our team has been notified."
        logger.error(
            "Unhandled exception [request_id=%s]: %s",
            request_id,
            str(exc),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": public_msg, "request_id": request_id},
        )

    @app.exception_handler(SafeHTTPException)
    async def _safe_http_handler(request: Request, exc: SafeHTTPException):
        # Our own safe errors already did the right logging in safe_error_response
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": request_id},
        )


# Convenience re-exports
__all__ = ["safe_error_response", "register_error_handlers", "SafeHTTPException"]