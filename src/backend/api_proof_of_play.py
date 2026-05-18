"""
api_proof_of_play.py - Proof of Play & Content Engine API
Public challenges, sessions, Base Markets integration for sideQuest
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
import logging

from db_layer import DBLayer

logger = logging.getLogger(__name__)
db = DBLayer()

app = FastAPI(title="sideQuest Proof of Play API", version="1.0.0")

# ─── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Helper Functions ─────────────────────────────────────────────────────────

def validate_uuid(param: str, param_name: str = "id"):
    """Validate UUID string."""
    try:
        uuid.UUID(str(param))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid {param_name}: {param}")

# ─── Sessions ─────────────────────────────────────────────────────────────────

@app.post("/api/sessions")
async def create_session(session: dict):
    """Create a new match session."""
    try:
        required = ["host_id", "title", "game_type"]
        for field in required:
            if field not in session:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        validate_uuid(session["host_id"], "host_id")
        if session.get("guest_id"):
            validate_uuid(session["guest_id"], "guest_id")
        
        result = db.create_session(
            host_id=session["host_id"],
            guest_id=session.get("guest_id"),
            title=session["title"],
            description=session.get("description", ""),
            game_type=session["game_type"],
            status=session.get("status", "scheduled")
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create session")
        
        logger.info(f"[Sessions] Created session {result['id']} by {session['host_id']}")
        return {"status": "success", "session": result}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Sessions] Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session by ID."""
    try:
        validate_uuid(session_id, "session_id")
        result = db.get_session(session_id)
        if not result:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "success", "session": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Sessions] Error fetching session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/sessions/{session_id}/status")
async def update_session_status(session_id: str, status: str):
    """Update session status."""
    try:
        validate_uuid(session_id, "session_id")
        valid_statuses = ["scheduled", "live", "completed", "cancelled"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
        
        result = db.update_session_status(session_id, status)
        if not result:
            raise HTTPException(status_code=404, detail="Session not found")
        
        logger.info(f"[Sessions] Updated session {session_id} status to {status}")
        return {"status": "success", "session": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Sessions] Error updating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/player/{player_id}")
async def get_player_sessions(player_id: str):
    """Get all sessions for a player."""
    try:
        validate_uuid(player_id, "player_id")
        result = db.get_sessions_by_player(player_id)
        return {"status": "success", "sessions": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Sessions] Error fetching player sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions")
async def list_sessions(status: Optional[str] = None, limit: int = 50):
    """List sessions."""
    try:
        # Note: This would need a dedicated query method in db_layer for production
        # For now, returning empty list as placeholder
        return {"status": "success", "sessions": []}
    except Exception as e:
        logger.error(f"[Sessions] Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Challenges ───────────────────────────────────────────────────────────────

@app.post("/api/challenges")
async def create_challenge(challenge: dict):
    """Create a public challenge."""
    try:
        required = ["issuer_id", "game_type", "stake_amount"]
        for field in required:
            if field not in challenge:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        validate_uuid(challenge["issuer_id"], "issuer_id")
        if challenge.get("target_id"):
            validate_uuid(challenge["target_id"], "target_id")
        
        stake = float(challenge["stake_amount"])
        if stake <= 0:
            raise HTTPException(status_code=400, detail="stake_amount must be positive")
        
        result = db.create_challenge(
            issuer_id=challenge["issuer_id"],
            game_type=challenge["game_type"],
            stake_amount=stake,
            target_id=challenge.get("target_id"),
            message=challenge.get("message", ""),
            theme=challenge.get("theme", "")
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create challenge")
        
        logger.info(f"[Challenges] Created challenge {result['id']} by {challenge['issuer_id']}")
        return {"status": "success", "challenge": result}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Challenges] Error creating challenge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/challenges/{challenge_id}")
async def get_challenge(challenge_id: str):
    """Get challenge by ID."""
    try:
        validate_uuid(challenge_id, "challenge_id")
        result = db.get_challenge(challenge_id)
        if not result:
            raise HTTPException(status_code=404, detail="Challenge not found")
        return {"status": "success", "challenge": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Challenges] Error fetching challenge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/challenges")
async def list_challenges(target_id: Optional[str] = None, limit: int = 50):
    """List open challenges."""
    try:
        if target_id:
            validate_uuid(target_id, "target_id")
            result = db.get_active_challenges(target_id=target_id)
        else:
            result = db.get_public_challenges(limit=limit)
        return {"status": "success", "challenges": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Challenges] Error listing challenges: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/challenges/{challenge_id}/accept")
async def accept_challenge(challenge_id: str, bet_id: Optional[str] = None):
    """Accept a public challenge."""
    try:
        validate_uuid(challenge_id, "challenge_id")
        if bet_id:
            validate_uuid(bet_id, "bet_id")
        
        result = db.accept_challenge(challenge_id, bet_id)
        if not result:
            raise HTTPException(status_code=404, detail="Challenge not found or already processed")
        
        logger.info(f"[Challenges] Accepted challenge {challenge_id}")
        return {"status": "success", "challenge": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Challenges] Error accepting challenge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/challenges/{challenge_id}/decline")
async def decline_challenge(challenge_id: str):
    """Decline a public challenge."""
    try:
        validate_uuid(challenge_id, "challenge_id")
        result = db.decline_challenge(challenge_id)
        if not result:
            raise HTTPException(status_code=404, detail="Challenge not found or already processed")
        
        logger.info(f"[Challenges] Declined challenge {challenge_id}")
        return {"status": "success", "challenge": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Challenges] Error declining challenge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/challenges/player/{player_id}")
async def get_player_challenges(player_id: str):
    """Get all challenges for a player."""
    try:
        validate_uuid(player_id, "player_id")
        result = db.get_player_challenges(player_id)
        return {"status": "success", "challenges": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Challenges] Error fetching player challenges: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Base Markets Integration ─────────────────────────────────────────────────

@app.post("/api/base-markets")
async def create_base_market(market: dict):
    """Create a Base Markets prediction pool."""
    try:
        required = ["market_type", "question", "outcomes"]
        for field in required:
            if field not in market:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        if market.get("bet_id"):
            validate_uuid(market["bet_id"], "bet_id")
        if market.get("session_id"):
            validate_uuid(market["session_id"], "session_id")
        
        result = db.create_base_market(
            bet_id=market.get("bet_id"),
            session_id=market.get("session_id"),
            market_type=market["market_type"],
            question=market["question"],
            outcomes=market["outcomes"],
            liquidity_usdc=float(market.get("liquidity_usdc", 0)),
            spread_fee_pct=float(market.get("spread_fee_pct", 0.05))
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create base market")
        
        logger.info(f"[BaseMarkets] Created market {result['id']}")
        return {"status": "success", "market": result}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BaseMarkets] Error creating market: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/base-markets/{market_id}")
async def get_base_market(market_id: str):
    """Get base market by ID."""
    try:
        result = db.get_base_market(market_id=market_id)
        if not result:
            raise HTTPException(status_code=404, detail="Market not found")
        return {"status": "success", "market": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BaseMarkets] Error fetching market: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/base-markets/bet/{bet_id}")
async def get_base_market_by_bet(bet_id: str):
    """Get base market by bet ID."""
    try:
        validate_uuid(bet_id, "bet_id")
        result = db.get_base_market(bet_id=bet_id)
        if not result:
            raise HTTPException(status_code=404, detail="Market not found")
        return {"status": "success", "market": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BaseMarkets] Error fetching market: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/base-markets")
async def list_active_base_markets():
    """List all active base markets."""
    try:
        result = db.get_active_base_markets()
        return {"status": "success", "markets": result}
    except Exception as e:
        logger.error(f"[BaseMarkets] Error listing markets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/base-markets/{market_id}/resolve")
async def resolve_base_market(market_id: str, status: str, tx_hash: Optional[str] = None):
    """Resolve a base market."""
    try:
        valid_statuses = ["resolved", "cancelled"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
        
        result = db.update_base_market_status(market_id, status, tx_hash)
        if not result:
            raise HTTPException(status_code=404, detail="Market not found")
        
        logger.info(f"[BaseMarkets] Resolved market {market_id} with status {status}")
        return {"status": "success", "market": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BaseMarkets] Error resolving market: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Proof of Play Receipts ───────────────────────────────────────────────────

@app.post("/api/proof-of-play")
async def create_proof_of_play(receipt: dict):
    """Create a proof of play receipt."""
    try:
        required = ["bet_id", "tx_hash"]
        for field in required:
            if field not in receipt:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        validate_uuid(receipt["bet_id"], "bet_id")
        if receipt.get("session_id"):
            validate_uuid(receipt["session_id"], "session_id")
        
        result = db.create_proof_of_play(
            bet_id=receipt["bet_id"],
            session_id=receipt.get("session_id"),
            tx_hash=receipt["tx_hash"],
            chain=receipt.get("chain", "base"),
            block_number=receipt.get("block_number"),
            verification_data=receipt.get("verification_data")
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create proof of play receipt")
        
        logger.info(f"[ProofOfPlay] Created receipt for bet {receipt['bet_id']}")
        return {"status": "success", "receipt": result}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ProofOfPlay] Error creating receipt: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/proof-of-play/bet/{bet_id}")
async def get_proof_of_play_by_bet(bet_id: str):
    """Get proof of play by bet ID."""
    try:
        validate_uuid(bet_id, "bet_id")
        result = db.get_proof_of_play(bet_id=bet_id)
        return {"status": "success", "receipts": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ProofOfPlay] Error fetching receipts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Leaderboard & Stats ──────────────────────────────────────────────────────

@app.get("/api/leaderboard/top10")
async def get_top10_players():
    """Get Top 10 players eligible for Base Markets."""
    try:
        result = db.get_top10_qualified(limit=10)
        return {"status": "success", "players": result}
    except Exception as e:
        logger.error(f"[Leaderboard] Error fetching top10: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leaderboard/top10/check/{player_id}")
async def check_top10_eligibility(player_id: str):
    """Check if a player is Top 10 eligible."""
    try:
        validate_uuid(player_id, "player_id")
        is_top10 = db.is_top10_player(player_id)
        return {"status": "success", "is_top10": is_top10}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Leaderboard] Error checking eligibility: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Identity & Reputation System ──────────────────────────────────────────────

@app.get("/api/identity/reputation/{player_id}")
async def get_player_reputation(player_id: str):
    """Get comprehensive reputation profile for a player."""
    try:
        validate_uuid(player_id, "player_id")
        result = db.get_player_reputation(player_id)
        if not result:
            raise HTTPException(status_code=404, detail="Player not found")
        return {"status": "success", "reputation": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Identity] Error fetching reputation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leaderboard")
async def get_leaderboard(
    state_type: Optional[str] = "global",
    state_value: Optional[str] = None,
    limit: int = 50,
    min_reputation: int = 0
):
    """
    Get leaderboard filtered by state.
    
    state_type: "global" | "game" | "region" | "tier"
    state_value: specific value (e.g., "EA FC 25", "Gold", "Lagos")
    """
    try:
        valid_states = ["global", "game", "region", "tier"]
        if state_type not in valid_states:
            raise HTTPException(status_code=400, detail=f"Invalid state_type. Must be one of: {valid_states}")
        
        result = db.get_leaderboard_by_state(
            state_type=state_type,
            state_value=state_value,
            limit=limit,
            min_reputation=min_reputation
        )
        return {"status": "success", "leaderboard": result, "state_type": state_type, "state_value": state_value}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Leaderboard] Error fetching leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leaderboard/game/{game_type}")
async def get_game_leaderboard(game_type: str, limit: int = 50):
    """Get leaderboard for a specific game."""
    try:
        result = db.get_game_leaderboard(game_type, limit)
        return {"status": "success", "leaderboard": result, "game_type": game_type}
    except Exception as e:
        logger.error(f"[Leaderboard] Error fetching game leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leaderboard/region/{region}")
async def get_region_leaderboard(region: str, limit: int = 50):
    """Get leaderboard for a specific region."""
    try:
        result = db.get_region_leaderboard(region, limit)
        return {"status": "success", "leaderboard": result, "region": region}
    except Exception as e:
        logger.error(f"[Leaderboard] Error fetching region leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/leaderboard/tier/{tier}")
async def get_tier_leaderboard(tier: str, limit: int = 50):
    """Get leaderboard for a specific reputation tier."""
    try:
        valid_tiers = ["Bronze", "Silver", "Gold", "Platinum", "Diamond"]
        if tier not in valid_tiers:
            raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {valid_tiers}")
        result = db.get_tier_leaderboard(tier, limit)
        return {"status": "success", "leaderboard": result, "tier": tier}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Leaderboard] Error fetching tier leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "sidequest-proof-of-play-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)