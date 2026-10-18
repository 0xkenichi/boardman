"""Paycrest Sender API v2 client (sync httpx; call it from a worker thread).

* Auth: ``API-Key`` header (https://docs.paycrest.io/api-reference/authentication).
* Envelope: ``{"status", "message", "data"}``.
* Timeouts on every call; bounded retries with backoff:
  - reads (rates, institutions, verify-account, get order) retry on transport
    errors, 429 and 5xx;
  - create-order retries only when Paycrest cannot have created anything:
    a connect error (request never sent) or a 503 ("no provider / quote
    unavailable: nothing is created, retry is safe" per the docs). Any other
    failure after the request was sent raises ``AmbiguousSubmit``; the caller
    keeps the order in ``submitting`` and the reconciler looks it up by our
    ``reference`` before ever submitting again. That reference is the order's
    idempotency key: Paycrest documents no idempotency header.
* Never logs request bodies (KYC, bank details) or the key.

Tests (and any dry run) swap the client with ``set_client``.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from decimal import Decimal
from typing import Any, Callable, Optional

import httpx

from gaming.src.backend.services.paycrest import config
from gaming.src.backend.services.paycrest.models import (
    AmbiguousSubmit,
    Institution,
    KycRejected,
    PaycrestError,
    PaycrestOrder,
    RateQuote,
    money,
)

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)
READ_ATTEMPTS = 3
CREATE_ATTEMPTS = 3


def verify_signature(raw_body: bytes, header: Optional[str], secret: str) -> bool:
    """``X-Paycrest-Signature``: hex HMAC-SHA256 of the raw body, keyed with
    the API Secret. Compare hex strings in constant time; fail closed."""
    if not secret or not header:
        return False
    sig = header.strip().lower()
    if len(sig) != 64:
        return False
    computed = hmac.new(secret.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest().lower()
    return hmac.compare_digest(computed.encode("utf-8"), sig.encode("utf-8"))


def sign(raw_body: bytes, secret: str) -> str:
    """For tests and the fake: what Paycrest would send."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


class PaycrestClient:
    def __init__(self, *, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 transport: Optional[httpx.BaseTransport] = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.base_url = (base_url or config.api_base()).rstrip("/")
        self._key = api_key if api_key is not None else config.api_key()
        self._transport = transport
        self._sleep = sleep

    # -- plumbing --

    def _http(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=TIMEOUT, transport=self._transport,
                            headers={"API-Key": self._key, "Content-Type": "application/json",
                                     "Accept": "application/json"})

    @staticmethod
    def _data(resp: httpx.Response) -> Any:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400:
            msg = str((body or {}).get("message") or f"HTTP {resp.status_code}")
            data = (body or {}).get("data")
            fields = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            if resp.status_code == 400 and any(
                    str((f or {}).get("field", "")).lower() in ("source", "source.kyc") for f in fields):
                raise KycRejected(msg, status_code=400, field_errors=fields, kind="kyc")
            raise PaycrestError(msg, status_code=resp.status_code,
                                retryable=resp.status_code in (429, 500, 502, 503, 504),
                                field_errors=fields,
                                kind="unavailable" if resp.status_code == 503 else "error")
        return (body or {}).get("data")

    def _read(self, method: str, path: str, **kw: Any) -> Any:
        last: Optional[Exception] = None
        for attempt in range(READ_ATTEMPTS):
            try:
                with self._http() as http:
                    return self._data(http.request(method, path, **kw))
            except PaycrestError as exc:
                if not exc.retryable:
                    raise
                last = exc
            except httpx.TransportError as exc:
                last = PaycrestError(f"network: {type(exc).__name__}", retryable=True, kind="network")
            if attempt + 1 < READ_ATTEMPTS:
                self._sleep(0.5 * (2 ** attempt))
        assert last is not None
        raise last

    # -- public endpoints --

    def get_rate(self, amount: Decimal, *, side: str, network: Optional[str] = None,
                 token: Optional[str] = None, currency: Optional[str] = None) -> RateQuote:
        """``GET /rates/{network}/{token}/{amount}/{fiat}?side=buy|sell`` (public).

        ``amount`` is the token amount. ``buy`` is the on-ramp side (customer
        buys USDC), ``sell`` the off-ramp side."""
        net, tok, cur = network or config.network(), token or config.token(), currency or config.currency()
        amt = f"{Decimal(amount).quantize(Decimal('0.01'))}"
        data = self._read("GET", f"/rates/{net}/{tok}/{amt}/{cur}", params={"side": side}) or {}
        q = data.get(side) if isinstance(data, dict) else None
        if not isinstance(q, dict):
            raise PaycrestError(f"no {side} quote", retryable=True, kind="unavailable")
        rate = money(q.get("rate"))
        if rate <= 0:
            raise PaycrestError("quote without a rate", retryable=True, kind="unavailable")
        return RateQuote(net, tok, cur, side, rate, list(q.get("providerIds") or []),
                         str(q.get("orderType") or ""), q.get("refundTimeoutMinutes"))

    def list_institutions(self, currency: Optional[str] = None) -> list[Institution]:
        data = self._read("GET", f"/institutions/{currency or config.currency()}") or []
        return [Institution(str(i.get("code") or ""), str(i.get("name") or ""), str(i.get("type") or ""))
                for i in data if isinstance(i, dict) and i.get("code")]

    def verify_account(self, institution: str, account_identifier: str) -> str:
        """Resolved account name, or ``"OK"`` when the bank gives no name."""
        data = self._read("POST", "/verify-account",
                          json={"institution": institution, "accountIdentifier": account_identifier})
        return str(data or "")

    def get_order(self, order_id: str) -> PaycrestOrder:
        return PaycrestOrder.from_api(self._read("GET", f"/sender/orders/{order_id}") or {})

    def find_order_by_reference(self, reference: str, *, pages: int = 3, page_size: int = 50
                                ) -> Optional[PaycrestOrder]:
        """Scan recent orders for our reference (used after an ambiguous submit).

        UNCERTAIN: the docs list ``GET /sender/orders`` but not its paging
        parameter names; ``page``/``pageSize`` follow the v1 list endpoint."""
        for page in range(1, pages + 1):
            data = self._read("GET", "/sender/orders", params={"page": page, "pageSize": page_size}) or {}
            rows = data.get("orders") if isinstance(data, dict) else data
            if not rows:
                return None
            for row in rows:
                if isinstance(row, dict) and str(row.get("reference") or "") == reference:
                    return PaycrestOrder.from_api(row)
        return None

    def create_order(self, payload: dict[str, Any]) -> PaycrestOrder:
        """``POST /sender/orders``. See the module docstring for retry rules."""
        last: Optional[Exception] = None
        for attempt in range(CREATE_ATTEMPTS):
            try:
                with self._http() as http:
                    resp = http.post("/sender/orders", json=payload)
            except httpx.ConnectError as exc:  # never reached Paycrest
                last = PaycrestError(f"network: {type(exc).__name__}", retryable=True, kind="network")
            except httpx.TransportError as exc:  # sent, answer lost
                raise AmbiguousSubmit(f"no answer from Paycrest ({type(exc).__name__})",
                                      kind="ambiguous") from exc
            else:
                if resp.status_code == 503:
                    last = PaycrestError("Paycrest has no provider for this right now", status_code=503,
                                         retryable=True, kind="unavailable")
                elif resp.status_code >= 500:
                    raise AmbiguousSubmit(f"Paycrest error {resp.status_code}", status_code=resp.status_code,
                                          kind="ambiguous")
                else:
                    return PaycrestOrder.from_api(self._data(resp) or {})
            if attempt + 1 < CREATE_ATTEMPTS:
                self._sleep(0.5 * (2 ** attempt))
        assert last is not None
        raise last


_override: Optional[Any] = None


def set_client(client: Optional[Any]) -> None:
    """Install a stand-in (tests, dry runs). ``None`` restores the real one."""
    global _override
    _override = client


def get_client() -> Any:
    if _override is not None:
        return _override
    return PaycrestClient()
