import os
import secrets
import base64
import requests
import json
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from dotenv import load_dotenv

load_dotenv()

def generate_and_prepare_registration():
    api_key = os.getenv("CIRCLE_API_KEY")
    if not api_key:
        print("❌ Error: CIRCLE_API_KEY not found in .env")
        return

    # 1. Generate a new 32-byte secret (64 hex chars)
    # We use secrets.token_hex(32) for cryptographic security
    entity_secret_hex = secrets.token_hex(32)
    print(f"\n🔑 1. YOUR NEW ENTITY SECRET (SAVE THIS!):")
    print(f"   {entity_secret_hex}")
    print(f"   (Add this to your .env as CIRCLE_ENTITY_SECRET)")

    # 2. Fetch Circle's Public Key
    print("\n🌐 2. Fetching Circle Public Key...")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(
            "https://api.circle.com/v1/w3s/config/entity/publicKey",
            headers=headers,
            timeout=10
        )
        if response.status_code != 200:
            print(f"❌ Failed to fetch public key: {response.text}")
            return
        
        pub_key_pem = response.json()["data"]["publicKey"]
        print("✅ Public key fetched.")
    except Exception as e:
        print(f"❌ Error fetching public key: {e}")
        return

    # 3. Encrypt the secret
    print("\n🔒 3. Generating Registration Ciphertext...")
    try:
        recipient_key = RSA.importKey(pub_key_pem)
        cipher_rsa = PKCS1_OAEP.new(recipient_key, hashAlgo=SHA256)
        
        # Must hex-decode to raw bytes before encrypting
        secret_bytes = bytes.fromhex(entity_secret_hex)
        ciphertext = cipher_rsa.encrypt(secret_bytes)
        
        registration_ciphertext = base64.b64encode(ciphertext).decode()
        
        print("\n✅ REGISTRATION CIPHERTEXT (Paste this into Circle Console):")
        print("-" * 60)
        print(registration_ciphertext)
        print("-" * 60)
        print("\nNext steps:")
        print("1. Go to Programmatic Wallets -> Developer-Controlled -> Configurator in Circle Console.")
        print("2. Paste the ciphertext above.")
        print("3. Download the Recovery File and save it safely.")
        print("4. Add CIRCLE_ENTITY_SECRET to your .env file.")
        
    except Exception as e:
        print(f"❌ Encryption failed: {e}")

if __name__ == "__main__":
    generate_and_prepare_registration()
