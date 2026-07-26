#!/usr/bin/env python3
"""
setup_circle_escrow.py - Initialize Circle Custodial Wallets & Escrow

Run this once to:
1. Create the shared escrow wallet
2. Verify Circle API connectivity
3. Output .env configuration
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from gaming.src.backend.circle_wallet_service import CircleWalletService
from gaming.src.backend.db_layer import DBLayer


def main():
    print("🔄 Initializing Circle Custodial Wallets & Escrow...")
    print("-" * 60)

    # Verify API keys
    api_key = os.getenv("CIRCLE_API_KEY")
    client_key = os.getenv("CIRCLE_CLIENT_KEY")

    if not api_key or not client_key:
        print("❌ Error: CIRCLE_API_KEY or CIRCLE_CLIENT_KEY missing in .env")
        sys.exit(1)

    print("✅ Circle API keys found")

    # Initialize services
    try:
        circle = CircleWalletService()
        db = DBLayer()
        print("✅ Database connected")
    except Exception as e:
        print(f"❌ Error initializing services: {e}")
        sys.exit(1)

    # Step 1: Create escrow wallet
    print("\n📝 Step 1: Creating escrow wallet...")
    escrow_result = circle.get_or_create_escrow_wallet()

    if not escrow_result["success"]:
        print(f"❌ Error creating escrow wallet: {escrow_result['error']}")
        sys.exit(1)

    escrow_wallet_id = escrow_result["wallet_id"]
    escrow_wallet_address = escrow_result["wallet_address"]

    print(f"✅ Escrow wallet created!")
    print(f"   ID: {escrow_wallet_id}")
    print(f"   Address: {escrow_wallet_address}")
    print(f"   Blockchain: BASE-SEPOLIA")

    # Step 2: Verify escrow balance
    print("\n🔍 Step 2: Checking escrow balance...")
    balance_result = circle.get_wallet_balance(escrow_wallet_address)

    if balance_result["success"]:
        print(f"   USDC Balance: {balance_result['balance_usdc']}")
        print(f"   Wei: {balance_result['balance_wei']}")
    else:
        print(f"   ⚠️  Cannot check balance (wallet might not be funded yet)")
        print(f"       Error: {balance_result['error']}")

    # Step 3: Create test escrow table if needed
    print("\n📊 Step 3: Checking database schema...")
    try:
        # Test if escrow_entries table exists
        test_query = db.get_escrow_entries_by_bet("00000000-0000-0000-0000-000000000000")
        print("✅ Escrow table exists")
    except Exception as e:
        print(f"⚠️  Escrow table might not exist: {e}")
        print("   Run the SQL migration from CIRCLE_ESCROW_SETUP.md")

    # Step 4: Output configuration
    print("\n" + "=" * 60)
    print("📋 ADD THESE TO YOUR .env FILE:")
    print("=" * 60)
    print(f"ESCROW_WALLET_ID={escrow_wallet_id}")
    print(f"ESCROW_WALLET_ADDRESS={escrow_wallet_address}")
    print("=" * 60)

    print("\n✅ Setup complete!")
    print("\nNext steps:")
    print("1. Copy the ESCROW_WALLET_* lines into your .env")
    print("2. Get testnet ETH: https://sepoliafaucet.com/")
    print("3. Fund escrow address with ~0.05 ETH for gas")
    print("4. Create SQL migration (see CIRCLE_ESCROW_SETUP.md)")
    print("5. Test wallet creation:")
    print("   python3 test_circle_wallet.py")


if __name__ == "__main__":
    main()
