"""Read match evidence back from our storage (CHANNELS_DESIGN §4.4).

Screenshots arrive from chat apps and are copied at once
(``whatsapp/media.copy_to_storage``) to ``evidence://<store>/<key>``:
``local`` under the agentic data dir, or a private Supabase bucket. The
settlement's AI vision and support tooling read them through here.
"""
from __future__ import annotations

from pathlib import PurePosixPath

MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
        "pdf": "application/pdf"}


class EvidenceNotFound(Exception):
    pass


def parse_ref(ref: str) -> tuple[str, str]:
    if not (ref or "").startswith("evidence://"):
        raise EvidenceNotFound("not an evidence ref")
    rest = ref[len("evidence://"):]
    store, _, key = rest.partition("/")
    key_path = PurePosixPath(key)
    if not store or not key or key_path.is_absolute() or ".." in key_path.parts:
        raise EvidenceNotFound("bad evidence ref")
    return store, key


def mime_for(key: str) -> str:
    return MIME.get(key.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def read_evidence(ref: str) -> tuple[bytes, str]:
    """(bytes, mime) for an ``evidence://`` ref (sync)."""
    store, key = parse_ref(ref)
    if store == "local":
        from gaming.src.channels.whatsapp.media import LocalEvidenceStore

        path = LocalEvidenceStore().root / key
        if not path.is_file():
            raise EvidenceNotFound(ref)
        return path.read_bytes(), mime_for(key)
    from backend.supabase_client import get_supabase

    data = get_supabase().storage.from_(store).download(key)
    if not data:
        raise EvidenceNotFound(ref)
    return bytes(data), mime_for(key)
