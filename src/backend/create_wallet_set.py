import os
import sys
import asyncio
from dotenv import load_dotenv

# Add current dir to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

async def create_official_wallet_set():
    load_dotenv()
    
    from circle_wallet_service import CircleWalletService
    circle = CircleWalletService()
    
    print("⏳ Creating Platform Wallet Set on Circle...")
    result = circle.create_wallet_set(name="sideQuest-users-official")
    
    if result["success"]:
        wallet_set = result["wallet_set"]
        print("\n✅ SUCCESS!")
        print(f"Wallet Set ID: {wallet_set['id']}")
        print(f"Name: {wallet_set['name']}")
        print("\n📋 ADD THIS TO YOUR .env FILE:")
        print(f"CIRCLE_WALLET_SET_ID={wallet_set['id']}")
    else:
        print("\n❌ FAILED")
        print(f"Error: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(create_official_wallet_set())
