"""
Paystack collections for Boardman Naira top-ups.

Flow:
  1. initialize_transaction(email, amount_ngn, reference, metadata)
  2. User pays on authorization_url
  3. verify_transaction(reference) or webhook charge.success
  4. Ops / float credits USDC (see PAYSTACK_CREDIT_MODE)

Env:
  PAYSTACK_SECRET_KEY  (required for init/verify)
  PAYSTACK_PUBLIC_KEY  (optional; checkout if needed)
  PAYSTACK_CALLBACK_URL  (optional redirect after pay)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

logger = logging.getLogger(__name__)

PAYSTACK_BASE = "https://api.paystack.co"


def secret_key() -> str:
    return (os.getenv("PAYSTACK_SECRET_KEY") or "").strip()


def public_key() -> str:
    return (os.getenv("PAYSTACK_PUBLIC_KEY") or "").strip()


def paystack_configured() -> bool:
    sk = secret_key()
    return bool(sk.startswith("sk_"))


def callback_url() -> str:
    return (
        os.getenv("PAYSTACK_CALLBACK_URL")
        or os.getenv("BOARDMAN_URL")
        or "https://boardman.playingsidequest.fun/app"
    ).strip()


def credit_mode() -> str:
    """
    manual  — mark paid, admin sends USDC then /credit_topup (default)
    notify  — same as manual + clear SLA copy
    """
    return (os.getenv("PAYSTACK_CREDIT_MODE") or "manual").strip().lower()


def sla_minutes() -> int:
    try:
        return max(5, int(os.getenv("PAYSTACK_CREDIT_SLA_MINUTES") or "30"))
    except ValueError:
        return 30


def ngn_to_kobo(amount_ngn: Decimal | float | int) -> int:
    d = Decimal(str(amount_ngn)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)


def _request(
    method: str,
    path: str,
    body: Optional[dict] = None,
) -> dict[str, Any]:
    sk = secret_key()
    if not sk:
        raise RuntimeError("PAYSTACK_SECRET_KEY not set")
    url = f"{PAYSTACK_BASE}{path}"
    data = None
    # Cloudflare in front of api.paystack.co bans bare Python-urllib UA (Error 1010).
    headers = {
        "Authorization": f"Bearer {sk}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Boardman/1.0 (+https://boardman.playingsidequest.fun; Paystack)",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.warning("[Paystack] HTTP %s %s: %s", exc.code, path, err_body[:400])
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"message": err_body or str(exc)}
        msg = (
            parsed.get("message")
            or parsed.get("detail")
            or parsed.get("title")
            or f"Paystack HTTP {exc.code}"
        )
        raise RuntimeError(msg) from exc


def initialize_transaction(
    *,
    email: str,
    amount_ngn: Decimal | float,
    reference: str,
    metadata: Optional[dict] = None,
    callback: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create a Paystack payment session.
    Returns {authorization_url, access_code, reference, amount_kobo}.
    """
    amount_kobo = ngn_to_kobo(amount_ngn)
    if amount_kobo < 10000:  # ₦100 min common; we enforce higher in fiat quote
        raise ValueError("Amount too small for Paystack")

    payload: dict[str, Any] = {
        "email": email,
        "amount": amount_kobo,
        "currency": "NGN",
        "reference": reference,
        "callback_url": callback or callback_url(),
        "metadata": metadata or {},
    }
    res = _request("POST", "/transaction/initialize", payload)
    if not res.get("status"):
        raise RuntimeError(res.get("message") or "Paystack initialize failed")
    data = res.get("data") or {}
    return {
        "authorization_url": data.get("authorization_url") or "",
        "access_code": data.get("access_code") or "",
        "reference": data.get("reference") or reference,
        "amount_kobo": amount_kobo,
        "raw": data,
    }


def verify_transaction(reference: str) -> dict[str, Any]:
    """
    Verify payment status with Paystack.
    Returns {ok, paid, amount_ngn, amount_kobo, status, gateway_response, customer_email, raw}.
    """
    ref = (reference or "").strip()
    if not ref:
        raise ValueError("Missing reference")
    res = _request("GET", f"/transaction/verify/{urllib.parse.quote(ref, safe='')}")
    data = res.get("data") or {}
    status = (data.get("status") or "").lower()
    amount_kobo = int(data.get("amount") or 0)
    paid = status == "success" and amount_kobo > 0
    return {
        "ok": bool(res.get("status")),
        "paid": paid,
        "status": status,
        "amount_kobo": amount_kobo,
        "amount_ngn": float(Decimal(amount_kobo) / 100),
        "gateway_response": data.get("gateway_response") or "",
        "customer_email": ((data.get("customer") or {}).get("email") or ""),
        "channel": data.get("channel") or "",
        "paid_at": data.get("paid_at") or "",
        "raw": data,
        "message": res.get("message") or "",
    }


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Paystack sends x-paystack-signature = HMAC SHA512 of body with secret key."""
    sk = secret_key()
    if not sk or not signature:
        return False
    digest = hmac.new(sk.encode("utf-8"), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature)
