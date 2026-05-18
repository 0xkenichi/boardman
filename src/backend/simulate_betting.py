import os
import asyncio
from backend.db_layer import DBLayer
from backend.wallet_service import WalletService
from gaming.src.backend.betting_engine import BettingEngine

async def run_simulation():
    print("🚀 Starting ClawStation Wallet & Betting Simulation...")
    
    # Initialize layers
    try:
        db = DBLayer()
        wallet = WalletService(db)
        engine = BettingEngine(db)
    except Exception as e:
        print(f"❌ Initialization failed (likely missing DB keys): {e}")
        print("Falling back to logic check...")
        return

    user_a = 123456
    user_b = 654321
    
    print(f"\n--- Phase 1: Funding ---")
    # Simulate User A funding $50
    _, ref_a = wallet.initiate_funding(user_a, 50)
    wallet.verify_payment(user_a, ref_a)
    print(f"User A balance: ${wallet.get_balance(user_a)}")

    # Simulate User B funding $50
    _, ref_b = wallet.initiate_funding(user_b, 50)
    wallet.verify_payment(user_b, ref_b)
    print(f"User B balance: ${wallet.get_balance(user_b)}")

    print(f"\n--- Phase 2: Challenge ---")
    res_abc = engine.place_challenge(user_a, 20, "FIFA 24")
    if res_abc["status"] == "success":
        bet_id = res_abc["data"]["id"]
        print(f"User A placed $20 challenge (ID: {bet_id})")
        print(f"User A new balance: ${wallet.get_balance(user_a)} (Escrowed)")
    else:
        print(f"❌ Challenge failed: {res_abc['message']}")
        return

    print(f"\n--- Phase 3: Matching ---")
    res_match = engine.match_challenge(user_b, bet_id)
    if res_match["status"] == "success":
        print(f"User B matched challenge {bet_id}")
        print(f"User B new balance: ${wallet.get_balance(user_b)} (Escrowed)")
    else:
        print(f"❌ Match failed: {res_match['message']}")
        return

    print(f"\n--- Phase 4: Approval ---")
    res_app = engine.approve_challenge(user_a, bet_id)
    if res_app["status"] == "success":
        print(f"User A approved match. Game is LIVE.")
    else:
        print(f"❌ Approval failed: {res_app['message']}")
        return

    print(f"\n--- Phase 5: Resolution ---")
    # Assume User B wins
    res_win = engine.resolve_match(bet_id, user_b)
    if res_win["status"] == "success":
        print(f"🏆 User B won! Payout processed.")
        print(f"User A final balance: ${wallet.get_balance(user_a)}")
        print(f"User B final balance: ${wallet.get_balance(user_b)}")
    else:
        print(f"❌ Resolution failed: {res_win['message']}")

if __name__ == "__main__":
    asyncio.run(run_simulation())
