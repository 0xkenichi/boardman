"""Inbound media → our storage (CHANNELS_DESIGN §4.4).

Meta's media URLs expire within minutes and the media itself after weeks, so
a screenshot is copied the moment it arrives and referenced as
``evidence://<store>/<key>``. Bytes are size-capped and checked against the
SHA-256 Meta reports. Two stores:

* ``local`` (default): ``<agentic data dir>/channels/evidence/``.
* ``supabase``: private bucket ``CHANNELS_EVIDENCE_BUCKET`` (default
  ``match-evidence``) via the service-role client.

EXIF stripping happens when Pillow is installed; otherwise the bytes are kept
as received (noted as an open item).
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from gaming.src.channels import config

logger = logging.getLogger(__name__)

EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


class MediaRejected(Exception):
    pass


class EvidenceStore(Protocol):
    def put(self, key: str, data: bytes, mime: str) -> str: ...


class LocalEvidenceStore:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            from gaming.src.stack.agentic.store import data_dir

            root = data_dir() / "channels" / "evidence"
        self.root = root

    def put(self, key: str, data: bytes, mime: str) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"evidence://local/{key}"


class SupabaseEvidenceStore:
    def __init__(self, bucket: str | None = None) -> None:
        self.bucket = bucket or os.getenv("CHANNELS_EVIDENCE_BUCKET") or "match-evidence"

    def put(self, key: str, data: bytes, mime: str) -> str:
        from backend.supabase_client import get_supabase

        get_supabase().storage.from_(self.bucket).upload(key, data, {"content-type": mime})
        return f"evidence://{self.bucket}/{key}"


def evidence_store() -> EvidenceStore:
    if (os.getenv("CHANNELS_EVIDENCE_STORE") or "local").strip().lower() == "supabase":
        return SupabaseEvidenceStore()
    return LocalEvidenceStore()


def strip_exif(data: bytes, mime: str) -> bytes:
    if not mime.startswith("image/"):
        return data
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return data
    try:
        img = Image.open(io.BytesIO(data))
        clean = Image.new(img.mode, img.size)
        clean.putdata(list(img.getdata()))
        buf = io.BytesIO()
        clean.save(buf, format=img.format or "PNG")
        return buf.getvalue()
    except Exception:
        logger.warning("[whatsapp] EXIF strip failed; keeping original", exc_info=True)
        return data


def copy_to_storage(client, media_id: str, *, store: EvidenceStore | None = None) -> tuple[str, str, str]:
    """Download ``media_id`` and store it. Returns (evidence ref, mime, sha256)."""
    max_bytes = config.int_env("CHANNELS_MEDIA_MAX_BYTES", 8 * 1024 * 1024)
    info = client.media_info(media_id) or {}
    url = info.get("url")
    mime = str(info.get("mime_type") or "application/octet-stream").split(";")[0].strip()
    if not url:
        raise MediaRejected("no media url")
    if mime not in EXT:
        raise MediaRejected(f"unsupported media type {mime}")
    declared = int(info.get("file_size") or 0)
    if declared and declared > max_bytes:
        raise MediaRejected("too large")
    data = client.download(url, max_bytes=max_bytes)
    digest = hashlib.sha256(data).hexdigest()
    expected = str(info.get("sha256") or "").lower()
    if expected and expected != digest:
        raise MediaRejected("checksum mismatch")
    return store_bytes(data, mime, channel="whatsapp", store=store)


def store_bytes(data: bytes, mime: str, *, channel: str, store: EvidenceStore | None = None) -> tuple[str, str, str]:
    """Size/type-check, strip EXIF and store evidence bytes from any channel."""
    mime = (mime or "").split(";")[0].strip()
    if mime not in EXT:
        raise MediaRejected(f"unsupported media type {mime}")
    if len(data) > config.int_env("CHANNELS_MEDIA_MAX_BYTES", 8 * 1024 * 1024):
        raise MediaRejected("too large")
    digest = hashlib.sha256(data).hexdigest()
    clean = strip_exif(data, mime)
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    key = f"{channel}/{day}/{digest}.{EXT[mime]}"
    ref = (store or evidence_store()).put(key, clean, mime)
    return ref, mime, digest
