from fastapi import FastAPI, HTTPException, Request
from datetime import datetime
import base64
import requests
import os
import logging
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/health")
async def health_check():
    """Simple health check that responds instantly."""
    return {
        "status": "ok",
        "service": "sidequest-api",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

def verify_circle_webhook(raw_body: bytes, signature_header: str, key_id_header: str) -> bool:
    """
    Verify Circle webhook signature using ECDSA (per Circle's official docs).
    """
    if not signature_header or not key_id_header:
        logger.warning("[Circle] Missing signature or key-id headers")
        return False

    circle_api_key = os.getenv("CIRCLE_API_KEY")
    if not circle_api_key:
        logger.warning("[Circle] CIRCLE_API_KEY not set — cannot fetch public key for verification")
        return True  # Allow in dev mode

    try:
        # Fetch Circle's public key
        public_key_id = key_id_header.strip()
        response = requests.get(
            f"https://api.circle.com/v2/notifications/publicKey/{public_key_id}",
            headers={"Authorization": f"Bearer {circle_api_key}"},
            timeout=10
        )

        if response.status_code != 200:
            logger.error(f"[Circle] Failed to fetch public key: {response.status_code}")
            return False

        key_data = response.json()
        public_key_b64 = key_data["data"]["publicKey"]

        # Decode public key
        public_key_bytes = base64.b64decode(public_key_b64)
        public_key = serialization.load_der_public_key(public_key_bytes)

        # Decode signature
        signature_b64 = signature_header
        if signature_header.startswith("v1,"):
            signature_b64 = signature_header[3:]
        signature_bytes = base64.b64decode(signature_b64)

        # Verify
        public_key.verify(
            signature_bytes,
            raw_body,
            ec.ECDSA(hashes.SHA256())
        )

        return True

    except InvalidSignature:
        logger.warning("[Circle] Invalid webhook signature")
        return False
    except Exception as e:
        logger.error(f"[Circle] Verification error: {e}")
        return False

@app.post("/webhook/circle")
async def circle_webhook(request: Request):
    """Handle Circle webhooks for wallet transaction events."""
    try:
        raw_body = await request.body()

        signature_header = request.headers.get("x-circle-signature")
        key_id_header = request.headers.get("x-circle-key-id")
        if not verify_circle_webhook(raw_body, signature_header or "", key_id_header or ""):
            raise HTTPException(status_code=401, detail="Invalid Circle webhook signature")

        payload = await request.json()
        logger.info(f"[Circle] Webhook received: {payload.get('type', 'unknown')}")

        tx_type = payload.get("type")
        tx_data = payload.get("data", {})

        if not tx_type or not tx_data:
            return {"status": "ignored", "reason": "malformed payload"}

        # Basic processing - just log for now
        logger.info(f"[Circle] Processing {tx_type}: {tx_data.get('id')}")

        return {"status": "processed"}

    except Exception as e:
        logger.error(f"[Circle] Webhook processing failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)