#!/usr/bin/env python3
"""
test_circle_wallet.py - Test Circle Custodial Wallets

Test wallet creation, balance checks, and USDC transfers.
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from circle_wallet_service import CircleWalletService
from db_layer import DBLayer
from wallet_service import WalletService


def test_wallet_creation():
    """Test creating a custodial wallet for a new user."""
    print("\n" + "=" * 60)
    print("TEST 1: Wallet Creation")
    print("=" * 60)

    db = DBLayer()
    wallet_svc = WalletService(db)
    circle = CircleWalletService()

    # Create a test profile
    test_whatsapp_id = "2349163497691"  # Your test number
    profile = db.get_or_create_profile("whatsapp_id", test_whatsapp_id)
    profile_id = profile["id"]

    print(f"Profile ID: {profile_id}")
    print(f"WhatsApp ID: {test_whatsapp_id}")

    # Create wallet
    print("\nCreating custodial wallet...")
    result = wallet_svc.create_custodial_wallet(profile_id)

    if result["success"]:
        print(f"✅ Wallet created!")
        print(f"   Address: {result['wallet_address']}")
        print(f"   Wallet ID: {result.get('wallet_id')}")
        print(f"   Blockchain: {result.get('blockchain')}")
        return profile_id, result["wallet_address"], result.get("wallet_id")
    else:
        print(f"❌ Failed: {result['message']}")
        return None, None, None


def test_wallet_balance(wallet_address):
    """Test getting wallet balance."""
    print("\n" + "=" * 60)
    print("TEST 2: Check Wallet Balance")
    print("=" * 60)

    circle = CircleWalletService()

    print(f"Checking balance for: {wallet_address}")
    result = circle.get_wallet_balance(wallet_address)

    if result["success"]:
        print(f"✅ Balance retrieved!")
        print(f"   USDC: {result['balance_usdc']}")
        print(f"   Wei: {result['balance_wei']}")
    else:
        print(f"⚠️  Cannot check balance: {result['error']}")
        print("   (Wallet might not be funded yet)")


def test_escrow_wallet():
    """Test getting/creating escrow wallet."""
    print("\n" + "=" * 60)
    print("TEST 3: Escrow Wallet")
    print("=" * 60)

    circle = CircleWalletService()

    print("Creating/retrieving escrow wallet...")
    result = circle.get_or_create_escrow_wallet()

    if result["success"]:
        print(f"✅ Escrow wallet ready!")
        print(f"   Address: {result['wallet_address']}")
        print(f"   Wallet ID: {result['wallet_id']}")
        print(f"   Type: {result.get('type')}")
    else:
        print(f"❌ Failed: {result['error']}")


def test_approval_flow(wallet_id, escrow_address):
    """Test USDC approval (requires wallet to have USDC)."""
    print("\n" + "=" * 60)
    print("TEST 4: USDC Approval (Requires funded wallet)")
    print("=" * 60)

    circle = CircleWalletService()

    if not wallet_id or not escrow_address:
        print("⏭️  Skipping (wallet not created)")
        return

    print(f"Approving 10 USDC for escrow...")
    result = circle.approve_usdc_transfer(wallet_id, 10.0, escrow_address)

    if result["success"]:
        print(f"✅ Approval submitted!")
        print(f"   TX ID: {result['transaction_id']}")
        print(f"   Status: {result['status']}")

        # Wait for confirmation
        print("\nWaiting for confirmation (up to 30s)...")
        confirm_result = circle.wait_for_transaction(
            result["transaction_id"],
            max_wait_seconds=30
        )

        if confirm_result["success"]:
            print(f"✅ Approval confirmed!")
            print(f"   Hash: {confirm_result.get('tx_hash')}")
        else:
            print(f"⏱️  Timeout or failed: {confirm_result.get('error')}")
    else:
        print(f"❌ Failed: {result['error']}")
        print("   Make sure wallet has USDC before testing approval")


def test_escrow_balance():
    """Test getting escrow balance."""
    print("\n" + "=" * 60)
    print("TEST 5: Escrow Balance")
    print("=" * 60)

    circle = CircleWalletService()

    # Get escrow wallet
    escrow = circle.get_or_create_escrow_wallet()
    if not escrow["success"]:
        print(f"❌ Cannot get escrow: {escrow['error']}")
        return

    # Check balance
    result = circle.get_wallet_balance(escrow["wallet_address"])

    if result["success"]:
        print(f"✅ Escrow balance:")
        print(f"   USDC: {result['balance_usdc']}")
        print(f"   Wei: {result['balance_wei']}")
    else:
        print(f"⚠️  Cannot check: {result['error']}")


def main():
    print("\n" + "🧪 CIRCLE WALLET TEST SUITE 🧪".center(60))

    # Test 1: Create wallet
    profile_id, wallet_address, wallet_id = test_wallet_creation()

    if not profile_id:
        print("\n❌ Cannot continue without wallet")
        sys.exit(1)

    # Test 2: Check balance
    test_wallet_balance(wallet_address)

    # Test 3: Escrow wallet
    escrow_result = test_escrow_wallet()

    # Get escrow address for next test
    circle = CircleWalletService()
    escrow = circle.get_or_create_escrow_wallet()
    escrow_address = escrow["wallet_address"] if escrow["success"] else None

    # Test 4: Approval (requires funding)
    if escrow_address:
        test_approval_flow(wallet_id, escrow_address)

    # Test 5: Escrow balance
    test_escrow_balance()

    # Summary
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Fund test wallet with USDC: https://www.basescan.org/faucet")
    print("2. Fund escrow wallet with ETH: https://sepoliafaucet.com/")
    print("3. Re-run this test with funds: python3 test_circle_wallet.py")
    print("4. Integrate with betting_engine.py to lock/release stakes")
    print()


if __name__ == "__main__":
    main()
