"""
circle_wallet_service.py - Circle Custodial Wallet Management
──────────────────────────────────────────────────────────────

Provides custodial wallet creation and management for WhatsApp users
+ escrow wallet for locking stakes during bets.

Each new WhatsApp user gets an isolated EOA wallet controlled by sideQuest.
Stakes are locked in a shared escrow wallet during active bets.
"""

import os
import uuid
import time
import json
import logging
import requests
import hashlib
from dotenv import load_dotenv
from typing import Dict, Optional

logger = logging.getLogger(__name__)

load_dotenv()


def _circle_fee_level() -> str:
    """Circle W3S feeLevel: LOW | MEDIUM | HIGH.

    Testnet default LOW (cheaper/faster inclusion on Arc). Override with
    CIRCLE_FEE_LEVEL=MEDIUM if a chain rejects LOW.
    """
    lvl = (os.getenv("CIRCLE_FEE_LEVEL") or "LOW").strip().upper()
    if lvl not in ("LOW", "MEDIUM", "HIGH"):
        lvl = "LOW"
    return lvl


def _circle_tx_poll_sec() -> float:
    """Seconds between Circle status polls (default 1.0; was 2.0)."""
    try:
        return max(0.5, float(os.getenv("CIRCLE_TX_POLL_SEC") or "1.0"))
    except ValueError:
        return 1.0


class CircleWalletService:
    def __init__(
        self,
        blockchain: Optional[str] = None,
        usdc_address: Optional[str] = None,
        usdc_token_id: Optional[str] = None,
        rpc_url: Optional[str] = None,
    ):
        self.api_url = "https://api.circle.com/v1"
        self.api_key = os.getenv("CIRCLE_API_KEY")
        self.client_key = os.getenv("CIRCLE_CLIENT_KEY")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Security for Developer-Controlled Wallets
        self.entity_secret = os.getenv("CIRCLE_ENTITY_SECRET")
        if not self.entity_secret:
            logger.warning("[Circle] CIRCLE_ENTITY_SECRET not found in .env")

        # Default Base Sepolia; multi-chain callers pass blockchain/usdc/rpc overrides
        self.blockchain = blockchain or os.getenv("CIRCLE_BLOCKCHAIN", "BASE-SEPOLIA")
        self.usdc_address = usdc_address or os.getenv(
            "USDC_ADDRESS", "0x036CbD53842c5426634E7929541eC2318f3dCF7e"
        )
        # Circle W3S token UUID (NOT the on-chain contract address).
        # /transactions/approve and /transfer require tokenId = UUID.
        self.usdc_token_id = usdc_token_id or os.getenv("CIRCLE_USDC_TOKEN_ID")
        self.rpc_url = rpc_url or os.getenv("RPC_URL")

    def _resolve_usdc_token_id(self, wallet_id: Optional[str] = None) -> Optional[str]:
        """Return Circle token UUID for USDC on this blockchain.

        Prefer configured ``usdc_token_id``. On Arc, fall back to the known
        ERC-20 facade UUID (0x3600…), then look up from wallet balances.
        """
        tid = (self.usdc_token_id or "").strip()
        if tid and not tid.startswith("0x"):
            return tid

        chain = (self.blockchain or "").upper()
        # Known Circle W3S token UUIDs (stable across entities)
        known = {
            # ARC-TESTNET ERC-20 USDC facade @ 0x3600…0000 (6 decimals)
            "ARC-TESTNET": "ef87c8c3-85de-598a-af50-c5135eecfa74",
            # Base Sepolia USDC
            "BASE-SEPOLIA": "bdf128b4-827b-5267-8f9e-243694989b5f",
        }
        if chain in known:
            return known[chain]

        if not wallet_id:
            return None
        try:
            response = requests.get(
                f"{self.api_url}/w3s/wallets/{wallet_id}/balances",
                headers=self.headers,
                timeout=15,
            )
            if response.status_code != 200:
                return None
            balances = (response.json().get("data") or {}).get("tokenBalances") or []
            usdc_addr = (self.usdc_address or "").lower()
            # Prefer non-native ERC-20 USDC matching our contract address
            for row in balances:
                tok = row.get("token") or {}
                if (tok.get("blockchain") or "").upper() != chain:
                    continue
                addr = (tok.get("tokenAddress") or "").lower()
                sym = (tok.get("symbol") or "").upper()
                if usdc_addr and addr == usdc_addr:
                    return tok.get("id")
                if sym == "USDC" and not tok.get("isNative"):
                    return tok.get("id")
            for row in balances:
                tok = row.get("token") or {}
                if (tok.get("symbol") or "").upper() == "USDC":
                    return tok.get("id")
        except Exception as e:
            logger.warning("[Circle] token id lookup failed: %s", e)
        return None

    def _generate_entity_secret_ciphertext(self) -> str:
        """
        Generate entitySecretCiphertext required for sensitive operations.
        1. Fetch public key from Circle
        2. Encrypt entity secret using RSA/OAEP
        3. Return base64 encoded ciphertext
        """
        if not self.entity_secret:
            return ""

        try:
            import base64
            from Crypto.PublicKey import RSA
            from Crypto.Cipher import PKCS1_OAEP
            from Crypto.Hash import SHA256

            # 1. Fetch Public Key
            pub_response = requests.get(
                f"{self.api_url}/w3s/config/entity/publicKey",
                headers=self.headers,
                timeout=10
            )
            if pub_response.status_code != 200:
                logger.error(f"[Circle] Failed to fetch public key: {pub_response.text}")
                return ""

            pub_key_pem = pub_response.json()["data"]["publicKey"]
            
            # 2. Encrypt
            recipient_key = RSA.importKey(pub_key_pem)
            cipher_rsa = PKCS1_OAEP.new(recipient_key, hashAlgo=SHA256)
            
            # Entity secret must be exactly 32 bytes (64 hex chars)
            secret_bytes = bytes.fromhex(self.entity_secret)
            ciphertext = cipher_rsa.encrypt(secret_bytes)
            
            return base64.b64encode(ciphertext).decode()
        except Exception as e:
            logger.error(f"[Circle] Ciphertext generation failed: {e}")
            return ""

    def create_wallet_set(self, name: str = "sideQuest-users") -> Dict:
        """
        Create a new wallet set. Required before creating wallets.
        """
        idempotency_key = str(uuid.uuid4())
        ciphertext = self._generate_entity_secret_ciphertext()
        
        payload = {
            "idempotencyKey": idempotency_key,
            "entitySecretCiphertext": ciphertext,
            "name": name
        }
        
        response = requests.post(
            f"{self.api_url}/w3s/developer/walletSets",
            json=payload,
            headers=self.headers,
            timeout=10
        )
        
        if response.status_code not in [200, 201]:
            return {"success": False, "error": response.json()}
            
        return {"success": True, "wallet_set": response.json()["data"]["walletSet"]}

    def create_custodial_wallet_for_user(self, profile_id: str, phone_number: str = None) -> Dict:
        """
        Create an EOA wallet for a user within the platform wallet set.
        """
        try:
            wallet_set_id = os.getenv("CIRCLE_WALLET_SET_ID")
            if not wallet_set_id:
                return {"success": False, "error": "CIRCLE_WALLET_SET_ID not configured in .env"}

            idempotency_key = str(uuid.uuid4())
            ciphertext = self._generate_entity_secret_ciphertext()

            payload = {
                "idempotencyKey": idempotency_key,
                "entitySecretCiphertext": ciphertext,
                "walletSetId": wallet_set_id,
                "blockchains": [self.blockchain],
                "count": 1,
                "accountType": "EOA",
                "metadata": [{
                    "profile_id": profile_id,
                    "phone_number": phone_number or "unknown",
                    "user_type": "telegram_user"
                }]
            }

            response = requests.post(
                f"{self.api_url}/w3s/developer/wallets",
                json=payload,
                headers=self.headers,
                timeout=10
            )

            if response.status_code not in [200, 201]:
                error_detail = response.json() if response.text else "Unknown error"
                return {
                    "success": False,
                    "error": str(error_detail),
                    "status_code": response.status_code
                }

            data = response.json().get("data", {})
            wallets = data.get("wallets", [])
            if not wallets:
                return {"success": False, "error": "No wallet returned in response"}

            wallet = wallets[0]
            return {
                "success": True,
                "wallet_id": wallet["id"],
                "wallet_address": wallet["address"],
                "blockchain": wallet["blockchain"]
            }
        except Exception as e:
            logger.error(f"[Circle] Create wallet failed: {e}")
            return {"success": False, "error": str(e)}
    def get_or_create_escrow_wallet(self) -> Dict:
        """
        Get or create the platform's shared escrow wallet for holding locked stakes.
        This wallet is controlled by sideQuest and holds all user escrow funds.

        Returns:
            {
                "success": bool,
                "wallet_id": str,
                "wallet_address": str,
                "type": "shared_escrow"
            }
        """
        # Check if escrow already exists in env
        escrow_wallet_id = os.getenv("ESCROW_WALLET_ID")
        escrow_wallet_address = os.getenv("ESCROW_WALLET_ADDRESS")

        if escrow_wallet_id and escrow_wallet_address:
            return {
                "success": True,
                "wallet_id": escrow_wallet_id,
                "wallet_address": escrow_wallet_address,
                "type": "shared_escrow",
                "note": "Existing escrow wallet from env"
            }

        # Create new escrow wallet
        return self.create_custodial_wallet_for_user(
            profile_id="PLATFORM_ESCROW",
            phone_number=None
        )

    def get_wallet(self, wallet_id: str) -> Dict:
        """Fetch a Circle wallet by id (used to validate chain + address)."""
        try:
            if not wallet_id:
                return {"success": False, "error": "wallet_id required"}
            response = requests.get(
                f"{self.api_url}/w3s/wallets/{wallet_id}",
                headers=self.headers,
                timeout=10,
            )
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": str(response.json() if response.text else "wallet fetch failed"),
                    "status_code": response.status_code,
                }
            wallet = response.json().get("data", {}).get("wallet") or response.json().get("data") or {}
            return {
                "success": True,
                "wallet_id": wallet.get("id") or wallet_id,
                "wallet_address": wallet.get("address"),
                "blockchain": wallet.get("blockchain"),
                "state": wallet.get("state"),
                "wallet_set_id": wallet.get("walletSetId"),
            }
        except Exception as e:
            logger.error(f"[Circle] get_wallet failed: {e}")
            return {"success": False, "error": str(e)}

    def get_wallet_balance(self, wallet_address: str) -> Dict:
        """
        Get USDC balance of a wallet via on-chain RPC.

        Arc: USDC is native gas + optional ERC-20 facade at 0x3600… (6 decimals).
        We read ERC-20 balanceOf first (recommended by Arc docs), and also check
        native balance (18 decimals on Arc) so we never report $0 when funds sit
        as native USDC only.

        Returns success=False on RPC errors — callers must NOT treat that as $0.
        """
        try:
            from web3 import Web3

            if not self.rpc_url:
                return {"success": False, "error": "RPC_URL not configured"}
            if not wallet_address or not str(wallet_address).startswith("0x"):
                return {"success": False, "error": "invalid wallet_address"}

            w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 20}))
            if not w3.is_connected():
                return {"success": False, "error": "Cannot connect to RPC"}

            checksum_wallet = Web3.to_checksum_address(wallet_address)
            erc20_usdc = 0.0
            native_as_usdc = 0.0
            balance_wei = 0

            # ERC-20 facade (6 decimals) — preferred read path
            if self.usdc_address:
                usdc_abi = [
                    {
                        "constant": True,
                        "inputs": [{"name": "_owner", "type": "address"}],
                        "name": "balanceOf",
                        "outputs": [{"name": "balance", "type": "uint256"}],
                        "type": "function",
                    }
                ]
                try:
                    checksum_usdc = Web3.to_checksum_address(self.usdc_address)
                    contract = w3.eth.contract(address=checksum_usdc, abi=usdc_abi)
                    balance_wei = int(contract.functions.balanceOf(checksum_wallet).call())
                    erc20_usdc = balance_wei / 1_000_000
                except Exception as e:
                    logger.warning("[Circle] ERC20 balanceOf failed %s: %s", wallet_address, e)

            # Native balance — on Arc this IS USDC (18 decimals for gas unit)
            try:
                native_wei = int(w3.eth.get_balance(checksum_wallet))
                chain = (self.blockchain or "").upper()
                if "ARC" in chain:
                    native_as_usdc = native_wei / 1e18
                else:
                    # non-Arc: native is ETH/AVAX etc — not USDC
                    native_as_usdc = 0.0
            except Exception as e:
                logger.warning("[Circle] native balance failed %s: %s", wallet_address, e)

            balance_usdc = max(erc20_usdc, native_as_usdc)

            return {
                "success": True,
                "balance_usdc": float(balance_usdc),
                "balance_wei": str(balance_wei),
                "erc20_usdc": float(erc20_usdc),
                "native_usdc": float(native_as_usdc),
                "wallet_address": wallet_address,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _is_arc(self) -> bool:
        return "ARC" in (self.blockchain or "").upper()

    def approve_usdc_transfer(self, wallet_id: str, amount_usdc: float, spender_address: str) -> Dict:
        """
        Approve a spender to transfer USDC from user's wallet.

        Arc Testnet: Circle's ``/transactions/approve`` returns Resource not found.
        Use contractExecution ``approve(address,uint256)`` on the USDC contract
        (Circle's recommended Arc path). Other chains try the approve endpoint first.
        """
        try:
            amount_wei = int(amount_usdc * 1_000_000)  # USDC ERC-20 facade: 6 decimals

            # Arc: always contract-exec (approve endpoint is 404 on ARC-TESTNET)
            if self._is_arc() and self.usdc_address:
                logger.info(
                    "[Circle] Arc approve via contractExecution wallet=%s spender=%s amount=%s",
                    wallet_id,
                    spender_address,
                    amount_usdc,
                )
                return self.execute_contract_function(
                    wallet_id=wallet_id,
                    contract_address=self.usdc_address,
                    function_signature="approve(address,uint256)",
                    args=[spender_address, str(amount_wei)],
                )

            token_id = self._resolve_usdc_token_id(wallet_id)
            if not token_id:
                return {
                    "success": False,
                    "error": (
                        f"No Circle USDC tokenId for {self.blockchain}. "
                        "Set CIRCLE_USDC_TOKEN_ID_* in .env"
                    ),
                }

            ciphertext = self._generate_entity_secret_ciphertext()
            if not ciphertext:
                return {"success": False, "error": "entity secret ciphertext missing"}

            payload = {
                "idempotencyKey": str(uuid.uuid4()),
                "entitySecretCiphertext": ciphertext,
                "walletId": wallet_id,
                "tokenId": token_id,
                "spender": spender_address,
                "amounts": [str(amount_wei)],
                "feeLevel": _circle_fee_level(),
            }

            logger.info(
                "[Circle] approve tokenId=%s wallet=%s spender=%s amount=%s chain=%s fee=%s",
                token_id,
                wallet_id,
                spender_address,
                amount_usdc,
                self.blockchain,
                payload["feeLevel"],
            )
            response = requests.post(
                f"{self.api_url}/w3s/developer/transactions/approve",
                json=payload,
                headers=self.headers,
                timeout=30,
            )

            if response.status_code not in [200, 201]:
                err_body = response.json() if response.text else {"message": "Approval failed"}
                # Fallback: contract-exec approve
                if self.usdc_address:
                    logger.warning(
                        "[Circle] approve endpoint failed (%s) — contractExecution approve",
                        err_body,
                    )
                    return self.execute_contract_function(
                        wallet_id=wallet_id,
                        contract_address=self.usdc_address,
                        function_signature="approve(address,uint256)",
                        args=[spender_address, str(amount_wei)],
                    )
                return {
                    "success": False,
                    "error": str(err_body),
                    "status_code": response.status_code,
                }

            data = response.json()["data"]
            tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else data
            return {
                "success": True,
                "transaction_id": tx.get("id") or data.get("id"),
                "status": tx.get("status") or data.get("status") or data.get("state", "PENDING"),
                "tx_hash": tx.get("txHash") or data.get("txHash"),
                "blockchain": tx.get("blockchain") or data.get("blockchain"),
                "token_id": token_id,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def transfer_usdc(self, from_wallet_id: str, to_address: str, amount_usdc: float) -> Dict:
        """
        Transfer USDC from user's wallet to recipient (usually escrow).

        ``tokenId`` must be the Circle UUID, not the contract address.
        """
        try:
            token_id = self._resolve_usdc_token_id(from_wallet_id)
            if not token_id:
                return {
                    "success": False,
                    "error": f"No Circle USDC tokenId for {self.blockchain}",
                }

            idempotency_key = str(uuid.uuid4())
            amount_wei = int(amount_usdc * 1_000_000)
            ciphertext = self._generate_entity_secret_ciphertext()
            if not ciphertext:
                return {"success": False, "error": "entity secret ciphertext missing"}

            payload = {
                "idempotencyKey": idempotency_key,
                "entitySecretCiphertext": ciphertext,
                "walletId": from_wallet_id,
                "tokenId": token_id,
                "destinationAddress": to_address,
                "amounts": [str(amount_wei)],
                # Top-level feeLevel works on Arc; nested fee object is rejected
                "feeLevel": _circle_fee_level(),
            }

            response = requests.post(
                f"{self.api_url}/w3s/developer/transactions/transfer",
                json=payload,
                headers=self.headers,
                timeout=30,
            )

            if response.status_code not in [200, 201]:
                return {
                    "success": False,
                    "error": str(response.json() if response.text else "Transfer failed"),
                    "status_code": response.status_code,
                }

            data = response.json()["data"]
            tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else data

            return {
                "success": True,
                "transaction_id": tx.get("id") or data.get("id"),
                "status": tx.get("status") or data.get("status", "PENDING"),
                "tx_hash": tx.get("txHash") or data.get("txHash"),
                "to_address": to_address,
                "amount_usdc": amount_usdc,
                "blockchain": tx.get("blockchain") or data.get("blockchain"),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_contract_function(
        self,
        wallet_id: str,
        contract_address: str,
        function_signature: str,
        args: list,
    ) -> Dict:
        """Call a contract via Circle contractExecution (createMatch / joinMatch / approve).

        Args:
            wallet_id: Circle developer wallet id
            contract_address: Target contract (escrow or USDC)
            function_signature: e.g. ``createMatch(bytes32,uint256)``
            args: ABI-encoded parameter values as strings / hex
        """
        try:
            ciphertext = self._generate_entity_secret_ciphertext()
            if not ciphertext:
                return {"success": False, "error": "entity secret ciphertext missing"}

            # Circle expects abiParameters as strings
            abi_params = [str(a) for a in (args or [])]
            # Arc (and current W3S API) wants top-level feeLevel, not nested fee config
            fee = _circle_fee_level()
            payload = {
                "idempotencyKey": str(uuid.uuid4()),
                "entitySecretCiphertext": ciphertext,
                "walletId": wallet_id,
                "contractAddress": contract_address,
                "abiFunctionSignature": function_signature,
                "abiParameters": abi_params,
                "feeLevel": fee,
            }
            logger.info(
                "[Circle] contractExecution %s wallet=%s contract=%s args=%s fee=%s",
                function_signature,
                wallet_id,
                contract_address,
                abi_params,
                fee,
            )
            response = requests.post(
                f"{self.api_url}/w3s/developer/transactions/contractExecution",
                json=payload,
                headers=self.headers,
                timeout=45,
            )
            if response.status_code not in (200, 201):
                # Retry once with alternate fee if primary rejected
                if response.status_code == 400:
                    alt = "MEDIUM" if fee == "LOW" else "LOW"
                    payload["idempotencyKey"] = str(uuid.uuid4())
                    payload["feeLevel"] = alt
                    response = requests.post(
                        f"{self.api_url}/w3s/developer/transactions/contractExecution",
                        json=payload,
                        headers=self.headers,
                        timeout=45,
                    )
            if response.status_code not in (200, 201):
                return {
                    "success": False,
                    "error": str(response.json() if response.text else "contractExecution failed"),
                    "status_code": response.status_code,
                }
            data = response.json().get("data") or {}
            tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else data
            return {
                "success": True,
                "transaction_id": tx.get("id") or data.get("id"),
                "status": tx.get("status") or data.get("status") or data.get("state", "PENDING"),
                "tx_hash": tx.get("txHash") or data.get("txHash"),
                "blockchain": tx.get("blockchain") or data.get("blockchain"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_transaction_status(self, transaction_id: str) -> Dict:
        """
        Poll transaction status from Circle.

        Returns:
            {
                "success": bool,
                "status": str,  # PENDING, CONFIRMED, FAILED
                "tx_hash": str,
                "created_at": str
            }
        """
        try:
            # Prefer developer path; fall back to shared transactions path
            response = requests.get(
                f"{self.api_url}/w3s/developer/transactions/{transaction_id}",
                headers=self.headers,
                timeout=15,
            )
            if response.status_code == 404:
                response = requests.get(
                    f"{self.api_url}/w3s/transactions/{transaction_id}",
                    headers=self.headers,
                    timeout=15,
                )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Transaction not found ({response.status_code})",
                    "status_code": response.status_code,
                }

            data = response.json().get("data") or {}
            tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else data
            status = (
                tx.get("status")
                or tx.get("state")
                or data.get("status")
                or data.get("state")
                or "UNKNOWN"
            )
            return {
                "success": True,
                "status": str(status).upper(),
                "tx_hash": tx.get("txHash") or data.get("txHash"),
                "created_at": tx.get("createDate") or data.get("createDate"),
                "blockchain": tx.get("blockchain") or data.get("blockchain"),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def wait_for_transaction(self, transaction_id: str, max_wait_seconds: int = 120) -> Dict:
        """
        Poll transaction until confirmed or failed (sync — blocks the thread).

        Prefer :meth:`wait_for_transaction_async` from async bot/API code so
        Telegram polling is not frozen for the whole wait.
        """
        start_time = time.time()
        poll_interval = _circle_tx_poll_sec()

        while time.time() - start_time < max_wait_seconds:
            result = self.get_transaction_status(transaction_id)

            if not result["success"]:
                return {"success": False, "error": result["error"]}

            status = result["status"]

            # Circle: INITIATED, PENDING, QUEUED, SENT, CONFIRMED, COMPLETE, FAILED
            if status in ("CONFIRMED", "COMPLETE", "COMPLETE_CONFIRMED"):
                return {
                    "success": True,
                    "status": "CONFIRMED",
                    "tx_hash": result.get("tx_hash"),
                    "time_waited": int(time.time() - start_time),
                }

            if status in ("FAILED", "DENIED", "CANCELLED"):
                return {
                    "success": False,
                    "error": f"Transaction failed on-chain ({status})",
                    "status": "FAILED",
                    "time_waited": int(time.time() - start_time),
                }

            time.sleep(poll_interval)

        return {
            "success": False,
            "error": f"Transaction not confirmed within {max_wait_seconds} seconds",
            "status": "TIMEOUT",
        }

    async def wait_for_transaction_async(
        self, transaction_id: str, max_wait_seconds: int = 120
    ) -> Dict:
        """Async poll — does not block the event loop (uses asyncio.sleep + to_thread)."""
        import asyncio

        start_time = time.time()
        poll_interval = _circle_tx_poll_sec()

        while time.time() - start_time < max_wait_seconds:
            result = await asyncio.to_thread(self.get_transaction_status, transaction_id)

            if not result.get("success"):
                return {"success": False, "error": result.get("error") or "status poll failed"}

            status = result.get("status") or ""
            if status in ("CONFIRMED", "COMPLETE", "COMPLETE_CONFIRMED"):
                waited = int(time.time() - start_time)
                logger.info(
                    "[Circle] tx %s CONFIRMED in %ss",
                    transaction_id[:12],
                    waited,
                )
                return {
                    "success": True,
                    "status": "CONFIRMED",
                    "tx_hash": result.get("tx_hash"),
                    "time_waited": waited,
                }
            if status in ("FAILED", "DENIED", "CANCELLED"):
                return {
                    "success": False,
                    "error": f"Transaction failed on-chain ({status})",
                    "status": "FAILED",
                    "time_waited": int(time.time() - start_time),
                }
            await asyncio.sleep(poll_interval)

        return {
            "success": False,
            "error": f"Transaction not confirmed within {max_wait_seconds} seconds",
            "status": "TIMEOUT",
        }

    def lock_stake_in_escrow(self, profile_id: str, wallet_id: str,
                             stake_amount: float, escrow_address: str, bet_id: str = None) -> Dict:
        """
        Complete flow: Approve → Transfer stake to escrow.

        Args:
            profile_id: User's profile ID
            wallet_id: User's Circle wallet ID
            stake_amount: Amount to lock
            escrow_address: Escrow wallet address
            bet_id: Optional bet ID for tracking

        Returns:
            {
                "success": bool,
                "escrow_tx_id": str,
                "amount_locked": float,
                "tx_hash": str
            }
        """
        try:
            # Step 1: Approve escrow to spend USDC
            approve_result = self.approve_usdc_transfer(wallet_id, stake_amount, escrow_address)
            if not approve_result["success"]:
                return {
                    "success": False,
                    "error": f"Approval failed: {approve_result['error']}"
                }

            # Wait for approval to be confirmed
            approval_status = self.wait_for_transaction(
                approve_result["transaction_id"],
                max_wait_seconds=60
            )
            if not approval_status["success"]:
                return {
                    "success": False,
                    "error": f"Approval confirmation timeout: {approval_status['error']}"
                }

            # Step 2: Transfer to escrow
            transfer_result = self.transfer_usdc(wallet_id, escrow_address, stake_amount)
            if not transfer_result["success"]:
                return {
                    "success": False,
                    "error": f"Transfer failed: {transfer_result['error']}"
                }

            # Wait for transfer to be confirmed
            transfer_status = self.wait_for_transaction(
                transfer_result["transaction_id"],
                max_wait_seconds=120
            )
            if not transfer_status["success"]:
                return {
                    "success": False,
                    "error": f"Transfer confirmation timeout: {transfer_status['error']}"
                }

            return {
                "success": True,
                "escrow_tx_id": transfer_result["transaction_id"],
                "amount_locked": stake_amount,
                "tx_hash": transfer_status.get("tx_hash"),
                "time_to_confirm": transfer_status.get("time_waited"),
                "bet_id": bet_id
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def release_stake_to_winner(self, winner_wallet_address: str,
                                amount_usdc: float, escrow_wallet_id: str,
                                bet_id: str = None) -> Dict:
        """
        Release locked stake from escrow to winner's wallet.

        Args:
            winner_wallet_address: Recipient's blockchain address
            amount_usdc: Amount to payout
            escrow_wallet_id: Circle wallet ID of escrow
            bet_id: Optional bet ID for tracking

        Returns:
            {
                "success": bool,
                "payout_tx_id": str,
                "amount_released": float,
                "tx_hash": str
            }
        """
        try:
            # Transfer from escrow to winner
            transfer_result = self.transfer_usdc(escrow_wallet_id, winner_wallet_address, amount_usdc)
            if not transfer_result["success"]:
                return {
                    "success": False,
                    "error": f"Payout transfer failed: {transfer_result['error']}"
                }

            # Wait for confirmation
            transfer_status = self.wait_for_transaction(
                transfer_result["transaction_id"],
                max_wait_seconds=120
            )
            if not transfer_status["success"]:
                return {
                    "success": False,
                    "error": f"Payout confirmation timeout: {transfer_status['error']}"
                }

            return {
                "success": True,
                "payout_tx_id": transfer_result["transaction_id"],
                "amount_released": amount_usdc,
                "to_address": winner_wallet_address,
                "tx_hash": transfer_status.get("tx_hash"),
                "time_to_confirm": transfer_status.get("time_waited"),
                "bet_id": bet_id
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_or_create_wallet_set_id(self, profile_id: str) -> str:
        """
        Get or create a walletSetId for the platform.
        Historically this was per-user, but Circle best practice is 
        to group users in platform-wide wallet sets.
        """
        # 1. Check for global wallet set in .env
        global_set = os.getenv("CIRCLE_WALLET_SET_ID")
        if global_set:
            return global_set

        # 2. Default platform-wide ID (stable UUID)
        # generated once: 550e8400-e29b-41d4-a716-446655440000
        return "550e8400-e29b-41d4-a716-446655440000"
