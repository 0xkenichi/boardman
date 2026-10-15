"""Cloud API client: send messages, mark read, fetch media.

All HTTP goes through one ``Transport`` callable, so tests (and a future BSP)
swap it without touching the request code. Endpoints (Graph API) [?]:

* ``POST {base}/{version}/{phone_number_id}/messages`` with
  ``{"messaging_product": "whatsapp", "recipient_type": "individual", "to": ..., "type": ...}``;
  the response carries ``messages[0].id`` (the wamid).
* mark read: same endpoint, ``{"messaging_product": "whatsapp", "status": "read", "message_id": ...}``.
* ``GET {base}/{version}/{media_id}`` → ``{url, mime_type, sha256, file_size}``;
  then ``GET url`` with the same bearer token (URL valid ~5 min [?]).

Auth: ``Authorization: Bearer <system-user token>``. Default API version is a
recent one at the time of writing (``WHATSAPP_GRAPH_VERSION``) [?].
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"
DEFAULT_VERSION = "v21.0"


@dataclass
class HttpResponse:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        import json

        return json.loads(self.body.decode("utf-8") or "null")


Transport = Callable[..., HttpResponse]  # (method, url, *, headers, json=None, params=None)


class WhatsAppError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"WhatsApp API {status}: {detail}")
        self.status = status
        self.detail = detail


def httpx_transport(timeout: float = 10.0) -> Transport:
    import httpx

    def call(method: str, url: str, *, headers: dict[str, str], json: Any = None,
             params: Optional[dict] = None) -> HttpResponse:
        r = httpx.request(method, url, headers=headers, json=json, params=params, timeout=timeout)
        return HttpResponse(r.status_code, r.content, dict(r.headers))

    return call


class GraphClient:
    def __init__(self, token: str, phone_number_id: str, *, transport: Optional[Transport] = None,
                 version: Optional[str] = None, base: str = GRAPH_BASE) -> None:
        if not token or not phone_number_id:
            raise ValueError("WhatsApp token and phone number id are required")
        self._token = token
        self.phone_number_id = phone_number_id
        self.version = version or os.getenv("WHATSAPP_GRAPH_VERSION") or DEFAULT_VERSION
        self.base = base.rstrip("/")
        self.transport = transport or httpx_transport()

    # -- plumbing --

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.base}/{self.version}/{path.lstrip('/')}"

    def _call(self, method: str, url: str, *, json: Any = None) -> Any:
        r = self.transport(method, url, headers=self._headers(), json=json)
        if r.status >= 400:
            try:
                err = (r.json() or {}).get("error") or {}
                detail = f"{err.get('code')} {err.get('message') or ''}".strip()
            except Exception:
                detail = "unreadable error body"
            raise WhatsAppError(r.status, detail)
        return r.json() if r.body else {}

    # -- messages --

    def send(self, to: str, message: dict[str, Any]) -> str:
        """Send one rendered message (``render.render`` output). Returns the wamid."""
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **message}
        data = self._call("POST", self._url(f"{self.phone_number_id}/messages"), json=body)
        msgs = (data or {}).get("messages") or [{}]
        return str(msgs[0].get("id") or "")

    def send_text(self, to: str, body: str) -> str:
        return self.send(to, {"type": "text", "text": {"body": body, "preview_url": False}})

    def send_template(self, to: str, name: str, language: str, components: list[dict]) -> str:
        return self.send(to, {"type": "template", "template": {
            "name": name, "language": {"code": language}, "components": components}})

    def mark_read(self, message_id: str) -> None:
        self._call("POST", self._url(f"{self.phone_number_id}/messages"), json={
            "messaging_product": "whatsapp", "status": "read", "message_id": message_id})

    # -- media --

    def media_info(self, media_id: str) -> dict[str, Any]:
        return self._call("GET", self._url(media_id))

    def download(self, url: str, *, max_bytes: int) -> bytes:
        r = self.transport("GET", url, headers={"Authorization": f"Bearer {self._token}"})
        if r.status >= 400:
            raise WhatsAppError(r.status, "media download failed")
        if len(r.body) > max_bytes:
            raise WhatsAppError(413, "media too large")
        return r.body


def client_from_env(transport: Optional[Transport] = None) -> Optional[GraphClient]:
    token = (os.getenv("WHATSAPP_ACCESS_TOKEN") or "").strip()
    phone_id = (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    if not token or not phone_id:
        return None
    return GraphClient(token, phone_id, transport=transport)
