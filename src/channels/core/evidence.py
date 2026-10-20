"""Read match evidence back from our storage (CHANNELS_DESIGN §4.4).

Screenshots arrive from chat apps and are copied at once
(``whatsapp/media.copy_to_storage``) to ``evidence://<store>/<key>``:
``local`` under the agentic data dir, or a private Supabase bucket. The
settlement's AI vision and support tooling read them through here.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Optional

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


_DIGEST = re.compile(r"(?:^|/)([0-9a-f]{64})\.[a-z]+$")


def digest_of(ref: str) -> Optional[str]:
    """SHA-256 of the bytes as received (stores name keys ``…/<digest>.<ext>``)."""
    try:
        _, key = parse_ref(ref)
    except EvidenceNotFound:
        return None
    m = _DIGEST.search(key)
    return m.group(1) if m else None


def note_use(ref: str, challenge_id: str, profile_id: str) -> Optional[dict]:
    """Record ``ref`` as evidence for ``challenge_id``.

    Returns the earlier use when the very same file was already sent for a
    *different* match (a recycled or borrowed screenshot), else None. Exact
    bytes only: a re-encoded, cropped or edited copy has a new digest
    (perceptual matching is out of scope; see the audit's residual risks).
    """
    digest = digest_of(ref)
    if not digest:
        return None
    from gaming.src.channels.core import store

    with store.db().transaction() as tx:
        tx.lock_key("channel_evidence", digest)
        row = tx.one("SELECT challenge_id, profile_id FROM channel_evidence WHERE digest = ?", (digest,))
        if row is None:
            tx.execute(
                "INSERT INTO channel_evidence (digest, challenge_id, profile_id, first_seen_ms) "
                "VALUES (?, ?, ?, ?)",
                (digest, str(challenge_id), str(profile_id), store.now_ms()),
            )
            return None
    if str(row["challenge_id"]) == str(challenge_id):
        return None
    return dict(row)


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
