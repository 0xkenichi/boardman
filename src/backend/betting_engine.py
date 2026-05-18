from db_layer import DBLayer
from court_layer import CourtLayer
from score_verifier import ScoreVerifier, verify_match


class BettingEngine:
    def __init__(self, db: DBLayer, blockchain=None):
        self.db = db
        self.court = CourtLayer(db)
        self.blockchain = blockchain
        self.verifier = ScoreVerifier()

    def place_challenge(self, creator_uuid: str, amount, game_type: str, is_on_chain: bool = False):
        profile = self.db.get_profile_by_uuid(creator_uuid)
        if not profile:
            return {"status": "error", "message": "Profile not found."}

        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return {"status": "error", "message": "Invalid bet amount."}

        if amount <= 0:
            return {"status": "error", "message": "Bet amount must be positive."}

        if self.db.get_available_balance(creator_uuid) < amount:
            return {"status": "error", "message": "Insufficient funds to place challenge."}

        on_chain_pool_id = None
        if is_on_chain:
            if not self.blockchain:
                return {"status": "error", "message": "On-chain betting is unavailable: blockchain client not configured."}
            try:
                entry_fee = int(round(amount * 10**6))
                on_chain_pool_id = self.blockchain.create_pool(0, 0, entry_fee, 86400, False)
                self.db.log_activity(creator_uuid, "FEE", 0, {"bet_id": None, "action": "on_chain_pool_created", "pool_id": on_chain_pool_id})
            except Exception as e:
                return {"status": "error", "message": f"Failed to create on-chain pool: {e}"}

        # Atomically lock funds with proper error handling
        try:
            lock_result = self.db.lock_funds(creator_uuid, amount)
            if not lock_result:
                return {"status": "error", "message": "Failed to lock funds. Please try again."}
        except Exception as e:
            return {"status": "error", "message": f"Fund locking failed: {e}"}

        bet = self.db.create_bet(creator_uuid, amount, game_type, is_on_chain=is_on_chain, on_chain_pool_id=on_chain_pool_id)
        if not bet:
            # Rollback on failure
            self.db.unlock_funds(creator_uuid, amount)
            return {"status": "error", "message": "Failed to create bet record."}

        self.db.log_activity(creator_uuid, "STAKE", amount, {"bet_id": bet["id"], "game": game_type})
        return {"status": "success", "data": bet}

    def match_challenge(self, opponent_uuid: str, bet_id: str):
        profile = self.db.get_profile_by_uuid(opponent_uuid)
        bet = self.db.get_bet(bet_id)

        if not bet or bet["status"] != "OPEN":
            return {"status": "error", "message": "This challenge is no longer open."}

        if bet.get("creator_id") == opponent_uuid:
            return {"status": "error", "message": "You cannot match your own challenge."}

        if self.db.get_available_balance(opponent_uuid) < float(bet["amount"]):
            return {"status": "error", "message": "Insufficient funds to match."}

        # Atomically lock opponent funds
        try:
            self.db.lock_funds(opponent_uuid, float(bet["amount"]))
        except Exception as e:
            return {"status": "error", "message": f"Fund locking failed: {e}"}

        if bet.get("is_on_chain") and self.blockchain:
            pool_id = bet.get("on_chain_pool_id")
            try:
                if pool_id is not None:
                    self.blockchain.join_pool(pool_id)
                else:
                    return {"status": "error", "message": "On-chain pool metadata missing."}
            except Exception as e:
                self.db.update_balance(opponent_uuid, float(bet["amount"]))
                return {"status": "error", "message": f"Failed to lock opponent stake on-chain: {e}"}

        # Atomic status update: only succeeds if status is still OPEN (race guard)
        updated_bet = self.db.match_bet(bet_id, opponent_uuid)
        if not updated_bet:
            # Bet was taken by someone else between our read and write — rollback
            self.db.update_balance(opponent_uuid, float(bet["amount"]))
            return {"status": "error", "message": "Challenge already matched. Funds returned."}

        return {"status": "success", "data": updated_bet}

    def approve_challenge(self, creator_uuid: str, bet_id: str):
        bet = self.db.get_bet(bet_id)
        if not bet:
            return {"status": "error", "message": "Bet not found."}
        if bet.get("creator_id") != creator_uuid:
            return {"status": "error", "message": "You are not the creator of this challenge."}
        if bet["status"] != "MATCHED":
            return {"status": "error", "message": "No matching challenge pending approval."}

        if bet.get("is_on_chain") and self.blockchain:
            pool_id = bet.get("on_chain_pool_id")
            try:
                if pool_id is not None:
                    self.blockchain.start_pool(pool_id)
                else:
                    return {"status": "error", "message": "On-chain pool metadata missing."}
            except Exception as e:
                return {"status": "error", "message": f"Failed to start on-chain pool: {e}"}

        updated_bet = self.db.approve_bet(bet_id, creator_uuid)
        if not updated_bet:
            return {"status": "error", "message": "Approval failed — bet may have changed state."}
        return {"status": "success", "data": updated_bet}

    def resolve_match(self, bet_id: str, winner_uuid: str):
        """
        Finalises a match and pays out the pot.
        Called internally by submit_report after consensus.
        """
        bet = self.db.get_bet(bet_id)
        if not bet:
            return {"status": "error", "message": "Match not found."}

        # Guard: only resolve bets in active states
        if bet["status"] not in ("ACCEPTED", "PENDING_REPORTS"):
            return {"status": "error", "message": f"Cannot resolve bet in state: {bet['status']}"}

        # Validate winner is a participant
        if winner_uuid not in (bet.get("creator_id"), bet.get("opponent_id")):
            return {"status": "error", "message": "Winner is not a participant in this bet."}

        total_pot = float(bet["amount"]) * 2

        # 1. On-Chain Payout (if applicable)
        tx_hash = None
        if bet.get("is_on_chain") and self.blockchain:
            winner_profile = self.db.get_profile_by_uuid(winner_uuid)
            winner_wallet = winner_profile.get("wallet_address") if winner_profile else None
            pool_id = bet.get("on_chain_pool_id")
            if winner_wallet and pool_id is not None:
                try:
                    tx_hash = self.blockchain.finalize_win_on_chain(pool_id, winner_wallet, total_pot)
                    self.db.update_bet_on_chain_tx(bet_id, tx_hash)
                except Exception as e:
                    print(f"[ERROR] On-Chain Payout failed: {e}")
            else:
                if not winner_wallet:
                    print("[WARN] Winner has no wallet address linked. Skipping on-chain payout.")
                if pool_id is None:
                    print("[WARN] On-chain pool id missing. Skipping on-chain payout.")

        # 2. Calculate dynamic fee: 3% for early adopters, 7% for others. Minimum $0.50.
        winner_profile = self.db.get_profile_by_uuid(winner_uuid)
        is_early = winner_profile.get("is_early_adopter", False) if winner_profile else False
        rate = 0.03 if is_early else 0.07
        
        commission = max(0.5, total_pot * rate)
        final_payout = total_pot - commission

        # 3. Award PlayPoints to both players
        mining_reward = float(bet["amount"]) * 10
        self.db.award_play_points(bet["creator_id"], mining_reward)
        if bet.get("opponent_id"):
            self.db.award_play_points(bet["opponent_id"], mining_reward)

        # 4. Credit winner (atomic – DB CHECK constraint guards against negative)
        try:
            self.db.update_balance(winner_uuid, final_payout)
        except Exception as e:
            print(f"[ERROR] Winner balance credit failed: {e}")
            return {"status": "error", "message": "Payout credit failed. Please contact support."}

        # 5. Mark bet resolved (idempotency: only transitions from active states)
        updated_bet = self.db.resolve_bet(bet_id, winner_uuid)
        if not updated_bet:
            return {"status": "error", "message": "Bet resolution status update failed."}

        # 6. Audit logs
        self.db.log_fee(bet_id, commission)
        self.db.log_activity(winner_uuid, "WIN", final_payout, {"bet_id": bet_id, "total_pot": total_pot})
        self.db.log_activity(None, "FEE", commission, {"bet_id": bet_id})

        return {
            "status": "success",
            "data": updated_bet,
            "on_chain_tx": tx_hash,
            "mined_points": mining_reward,
            "fee_deducted": commission
        }

    async def submit_report(self, bet_id: str, reporter_uuid: str, score: str, proof_url=None, use_verifier=True):
        """Submits a match report and checks for consensus."""
        bet = self.db.get_bet(bet_id)
        if not bet or bet["status"] not in ("ACCEPTED", "PENDING_REPORTS"):
            return {"status": "error", "message": "Match not in valid state for reporting."}

        # Only participants may report
        if reporter_uuid not in (bet.get("creator_id"), bet.get("opponent_id")):
            return {"status": "error", "message": "You are not a participant in this match."}

        # Get player profiles for verification
        creator = self.db.get_profile_by_uuid(bet["creator_id"])
        opponent = self.db.get_profile_by_uuid(bet["opponent_id"]) if bet.get("opponent_id") else None
        
        # Use score verifier if enabled
        verification_result = None
        if use_verifier:
            psn_id = creator.get("psn_id") if creator.get("id") == reporter_uuid else opponent.get("psn_id") if opponent else None
            xbox_id = creator.get("xbox_id") if creator.get("id") == reporter_uuid else opponent.get("xbox_id") if opponent else None
            
            verification_result = await self.verifier.verify_match_outcome(
                game_type=bet.get("game_type", "FIFA"),
                player1_id=bet["creator_id"],
                player2_id=bet.get("opponent_id"),
                screenshot_url=proof_url,
                expected_score=score,
                psn_id=psn_id,
                xbox_id=xbox_id
            )
            
            # Auto-resolve if screenshot verification is confident
            if verification_result.get("verified") and verification_result.get("confidence", 0) >= 80:
                # Extract winner from verification
                score_obj = verification_result.get("score")
                if score_obj:
                    winner = bet["creator_id"] if score_obj.winner == "home" else bet.get("opponent_id")
                    if score_obj.winner == "draw":
                        return {"status": "draw", "message": "Match ended in a draw. Stake returned."}
                    return self.resolve_match(bet_id, winner)

        # Transition to PENDING_REPORTS if still ACCEPTED
        if bet["status"] == "ACCEPTED":
            self.db.supabase.table("bets").update({"status": "PENDING_REPORTS"}).eq("id", bet_id).eq("status", "ACCEPTED").execute()

        # Store report with verification data
        try:
            report_data = {"score": score, "proof_url": proof_url}
            if verification_result:
                report_data["verification"] = verification_result
            self.court.report_result(bet_id, reporter_uuid, score, proof_url)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        # Check consensus
        status, winner = await self.court.check_consensus(bet_id)

        if status == "AGREEMENT":
            return self.resolve_match(bet_id, winner)
        elif status == "CONFLICT":
            self.db.supabase.table("bets").update({"status": "DISPUTED"}).eq("id", bet_id).execute()
            return {"status": "disputed", "message": "Reports conflict! Case sent to AI Mediator."}
        else:
            return {"status": "pending", "message": "Result reported. Waiting for opponent.", "verification": verification_result}
