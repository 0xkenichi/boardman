"""
gaming.py - Gaming quest specific endpoints

Integrates with existing staking, AI verification, and blockchain systems.
For quest_type: 'gaming' only.
"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from supabase import Client
from db_layer import DBLayer
from pydantic import BaseModel, Field
from utils.auth import require_beta_approval

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gaming", tags=["gaming"])

# ─── Pydantic Models ───────────────────────────────────────────────────────────

class StakeRequest(BaseModel):
    quest_id: str = Field(..., description="Gaming quest ID")
    amount: float = Field(..., gt=0, description="Stake amount in USDT")

class ScoreSubmissionRequest(BaseModel):
    quest_id: str = Field(..., description="Gaming quest ID")
    winner_id: str = Field(..., description="Winner profile ID")
    score: str = Field(..., description="Score (e.g., '3-1')")
    proof_image: Optional[str] = Field(None, description="Base64 encoded screenshot")

# ─── Dependency ────────────────────────────────────────────────────────────────

def get_db():
    return DBLayer()

# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/stake", response_model=dict, status_code=201)
async def initiate_stake(
    stake_data: StakeRequest,
    db: DBLayer = Depends(get_db),
    user_id: str = Depends(require_beta_approval)
):
    """
    Initiate staking for a gaming quest.
    
    Creates a bet record and triggers ClawEscrow deposit.
    """
    try:
        # user_id obtained from auth via require_beta_approval dependency
        # Get quest
        quest_res = db.supabase.table("quests").select(
            "*"
        ).eq("id", stake_data.quest_id).single().execute()
        
        if not quest_res.data:
            raise HTTPException(status_code=404, detail="Quest not found")
        
        quest = quest_res.data
        
        # Verify it's a gaming quest
        if quest["quest_type"] != "gaming":
            raise HTTPException(status_code=400, detail="Not a gaming quest")
        
        # Verify quest is open
        if quest["status"] != "open":
            raise HTTPException(status_code=400, detail=f"Quest is {quest['status']}")
        
        # Verify stake amount matches quest requirement
        if stake_data.amount != quest["stake_amount"]:
            raise HTTPException(
                status_code=400,
                detail=f"Stake amount must be {quest['stake_amount']}"
            )
        
        # Check if user is participant
        participant_res = db.supabase.table("quest_participants").select(
            "profile_id"
        ).eq("quest_id", stake_data.quest_id).eq("profile_id", user_id).single().execute()
        
        if not participant_res.data:
            raise HTTPException(status_code=403, detail="Not a participant in this quest")
        
        # Check if already staked
        existing_bet = db.supabase.table("bets").select(
            "id"
        ).eq("quest_id", stake_data.quest_id).eq("bettor", user_id).eq("status", "active").single().execute()
        
        if existing_bet.data:
            raise HTTPException(status_code=400, detail="Already staked on this quest")
        
        # Create bet record
        bet_result = db.supabase.table("bets").insert({
            "bettor": user_id,
            "amount": stake_data.amount,
            "status": "pending",
            "quest_id": stake_data.quest_id,
            "transaction_type": "stake"
        }).execute()
        
        bet = bet_result.data[0]
        
        # Note: In production, this would trigger ClawEscrow smart contract
        # For now, we simulate the escrow process
        
        return {
            "success": True,
            "bet_id": bet["id"],
            "quest_id": stake_data.quest_id,
            "amount": stake_data.amount,
            "status": "pending",
            "message": "Stake initiated. Awaiting escrow confirmation."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating stake: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/score", response_model=dict, status_code=201)
async def submit_score(
    score_data: ScoreSubmissionRequest,
    db: DBLayer = Depends(get_db)
):
    """
    Submit match score for AI verification.
    
    Triggers OpenAI GPT-4 Vision to verify score screenshot.
    """
    try:
        user_id = score_data.user_id if hasattr(score_data, 'user_id') else None
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id required")
        
        # Get quest
        quest_res = db.supabase.table("quests").select(
            "*"
        ).eq("id", score_data.quest_id).single().execute()
        
        if not quest_res.data:
            raise HTTPException(status_code=404, detail="Quest not found")
        
        quest = quest_res.data
        
        # Verify it's a gaming quest
        if quest["quest_type"] != "gaming":
            raise HTTPException(status_code=400, detail="Not a gaming quest")
        
        # Verify user is participant
        participant_res = db.supabase.table("quest_participants").select(
            "profile_id"
        ).eq("quest_id", score_data.quest_id).eq("profile_id", user_id).single().execute()
        
        if not participant_res.data:
            raise HTTPException(status_code=403, detail="Not a participant in this quest")
        
        # Check if winner is a participant
        winner_res = db.supabase.table("quest_participants").select(
            "profile_id"
        ).eq("quest_id", score_data.quest_id).eq("profile_id", score_data.winner_id).single().execute()
        
        if not winner_res.data:
            raise HTTPException(status_code=400, detail="Winner is not a participant")
        
        # Create challenge record (for AI verification)
        challenge_result = db.supabase.table("challenges").insert({
            "quest_id": score_data.quest_id,
            "challenger_id": user_id,
            "challenged_id": score_data.winner_id,  # Note: might need to determine opponent
            "score": score_data.score,
            "status": "pending_verification",
            "proof_screenshot": score_data.proof_image
        }).execute()
        
        challenge = challenge_result.data[0]
        
        # Note: In production, this would trigger OpenAI verification webhook
        # Simulate AI verification process
        
        return {
            "success": True,
            "challenge_id": challenge["id"],
            "quest_id": score_data.quest_id,
            "score": score_data.score,
            "status": "pending_verification",
            "message": "Score submitted for AI verification"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting score: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/receipt/{quest_id}", response_model=dict)
async def get_proof_of_play(
    quest_id: str,
    db: DBLayer = Depends(get_db)
):
    """
    Get Proof of Play receipt for a completed gaming quest.
    
    Returns AI-verified match details and blockchain signatures.
    """
    try:
        # Get quest
        quest_res = db.supabase.table("quests").select(
            "*"
        ).eq("id", quest_id).single().execute()
        
        if not quest_res.data:
            raise HTTPException(status_code=404, detail="Quest not found")
        
        quest = quest_res.data
        
        # Verify it's a gaming quest
        if quest["quest_type"] != "gaming":
            raise HTTPException(status_code=400, detail="Not a gaming quest")
        
        # Get proof of play receipt
        receipt_res = db.supabase.table("proof_of_play_receipts").select(
            "*"
        ).eq("quest_id", quest_id).single().execute()
        
        if not receipt_res.data:
            raise HTTPException(status_code=404, detail="Proof of Play not found")
        
        receipt = receipt_res.data
        
        # Get related challenge
        challenge_res = db.supabase.table("challenges").select(
            "*"
        ).eq("quest_id", quest_id).single().execute()
        
        challenge = challenge_res.data if challenge_res.data else None
        
        # Get participants
        participants_res = db.supabase.table("quest_participants").select(
            "profile_id"
        ).eq("quest_id", quest_id).execute()
        
        participants = [p["profile_id"] for p in participants_res.data] if participants_res.data else []
        
        return {
            "success": True,
            "quest_id": quest_id,
            "receipt": {
                "id": receipt["id"],
                "match_id": receipt.get("match_id"),
                "winner_id": receipt.get("winner_id"),
                "score": receipt.get("score"),
                "verification_status": receipt.get("verification_status"),
                "blockchain_signature": receipt.get("blockchain_signature"),
                "verified_at": receipt.get("verified_at"),
                "ai_confidence": receipt.get("ai_confidence")
            },
            "challenge": challenge,
            "participants": participants
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting proof of play: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{quest_id}/status", response_model=dict)
async def get_gaming_quest_status(
    quest_id: str,
    db: DBLayer = Depends(get_db)
):
    """
    Get comprehensive status of a gaming quest.
    
    Includes staking, verification, and payout status.
    """
    try:
        # Get quest
        quest_res = db.supabase.table("quests").select(
            "*"
        ).eq("id", quest_id).single().execute()
        
        if not quest_res.data:
            raise HTTPException(status_code=404, detail="Quest not found")
        
        quest = quest_res.data
        
        # Verify it's a gaming quest
        if quest["quest_type"] != "gaming":
            raise HTTPException(status_code=400, detail="Not a gaming quest")
        
        # Get bets/stakes
        bets_res = db.supabase.table("bets").select(
            "*"
        ).eq("quest_id", quest_id).execute()
        
        bets = bets_res.data if bets_res.data else []
        
        # Get challenge/verification status
        challenge_res = db.supabase.table("challenges").select(
            "*"
        ).eq("quest_id", quest_id).single().execute()
        
        challenge = challenge_res.data if challenge_res.data else None
        
        # Get proof of play
        receipt_res = db.supabase.table("proof_of_play_receipts").select(
            "*"
        ).eq("quest_id", quest_id).single().execute()
        
        receipt = receipt_res.data if receipt_res.data else None
        
        # Get participants
        participants_res = db.supabase.table("quest_participants").select(
            "profile_id"
        ).eq("quest_id", quest_id).execute()
        
        participants = [p["profile_id"] for p in participants_res.data] if participants_res.data else []
        
        return {
            "success": True,
            "quest_id": quest_id,
            "quest_status": quest["status"],
            "participants": participants,
            "stakes": {
                "total_bets": len(bets),
                "bets": bets,
                "total_amount": sum([b.get("amount", 0) for b in bets])
            },
            "verification": {
                "challenge": challenge,
                "status": challenge.get("status") if challenge else None,
                "verified": challenge.get("status") == "verified" if challenge else False
            },
            "payout": {
                "receipt": receipt,
                "distributed": receipt is not None and receipt.get("verification_status") == "verified"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting gaming quest status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


from fastapi import Body

@router.post("/{quest_id}/resolve", response_model=dict)
async def resolve_gaming_quest(
    quest_id: str,
    winner_id: str = Body(..., description="Winner profile ID"),
    db: DBLayer = Depends(get_db)
):
    """
    Resolve a gaming quest and distribute stakes.
    
    Note: In production, this would trigger smart contract payout.
    """
    try:
        # Get quest
        quest_res = db.supabase.table("quests").select(
            "*"
        ).eq("id", quest_id).single().execute()
        
        if not quest_res.data:
            raise HTTPException(status_code=404, detail="Quest not found")
        
        quest = quest_res.data
        
        # Verify it's a gaming quest
        if quest["quest_type"] != "gaming":
            raise HTTPException(status_code=400, detail="Not a gaming quest")
        
        # Verify quest is completed
        if quest["status"] not in ["open", "full"]:
            raise HTTPException(status_code=400, detail="Quest not in progress")
        
        # Verify winner is participant
        winner_res = db.supabase.table("quest_participants").select(
            "profile_id"
        ).eq("quest_id", quest_id).eq("profile_id", winner_id).single().execute()
        
        if not winner_res.data:
            raise HTTPException(status_code=400, detail="Winner is not a participant")
        
        # Get all stakes
        bets_res = db.supabase.table("bets").select(
            "*"
        ).eq("quest_id", quest_id).eq("status", "active").execute()
        
        bets = bets_res.data if bets_res.data else []
        
        if not bets:
            raise HTTPException(status_code=400, detail="No active stakes to distribute")
        
        # Calculate total pool
        total_pool = sum([b.get("amount", 0) for b in bets])
        
        # Note: In production, this would trigger ClawEscrow.resolve()
        # and distribute via smart contract
        
        # Update quest status
        db.supabase.table("quests").update({
            "status": "completed"
        }).eq("id", quest_id).execute()
        
        # Update bets
        db.supabase.table("bets").update({
            "status": "resolved"
        }).eq("quest_id", quest_id).execute()
        
        # Create proof of play receipt
        db.supabase.table("proof_of_play_receipts").insert({
            "quest_id": quest_id,
            "winner_id": winner_id,
            "total_pool": total_pool,
            "verification_status": "verified",
            "distributed_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        
        return {
            "success": True,
            "quest_id": quest_id,
            "winner_id": winner_id,
            "total_pool": total_pool,
            "bets_resolved": len(bets),
            "message": "Quest resolved and stakes distributed"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving gaming quest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))