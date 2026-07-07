"""
Xbox Game Activity Reader for ClawStation
Reads Xbox Live activity to verify:
- Gamertag authenticity  
- Recently played games
- Match outcomes and timestamps
- Gamerscore and achievements
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import aiohttp
from dotenv import load_dotenv

load_dotenv()


@dataclass
class XboxMatchResult:
    """Represents an Xbox match result"""
    game_name: str
    match_date: datetime
    duration_minutes: int
    gamerscore_earned: int
    is_win: Optional[bool] = None
    score: Optional[str] = None


@dataclass
class XboxUserProfile:
    """Enhanced Xbox user profile data"""
    gamertag: str
    xuid: str
    gamerscore: int
    account_tier: str  # Gold, Silver, etc.
    recent_games: List[Dict]
    is_real_gamer: bool


class XboxGameReader:
    """
    Reads and analyzes Xbox Live game activity for match verification.
    Uses the XBL.io API for Xbox Live data.
    """
    
    # Game IDs for supported titles
    SUPPORTED_GAMES = {
        'FIFA24': ['FIFA24', 'FIFA 24', 'EA SPORTS FC 24', 'FC24', 'FC 24'],
        'FC25': ['FC25', 'FC 25', 'EA SPORTS FC 25'],
        'NBA2K24': ['NBA2K24', 'NBA 2K24'],
        'NBA2K25': ['NBA2K25', 'NBA 2K25'],
    }
    
    # Minimum gamerscore for "real gamer" verification
    MIN_GAMERSCORE_FOR_VERIFICATION = 500
    
    def __init__(self):
        self.api_key = os.getenv("XBL_IO_KEY")
        self.base_url = "https://xbl.io/api/v2"
        self.headers = {
            "X-Authorization": self.api_key,
            "Content-Type": "application/json"
        } if self.api_key else None
        
        if not self.api_key:
            print("[WARN] XBL_IO_KEY not set. Xbox API unavailable.")
    
    async def get_full_profile(self, gamertag: str) -> Optional[XboxUserProfile]:
        """
        Get comprehensive Xbox user profile with verification status.
        """
        if not self.api_key:
            return None
        
        try:
            xuid = await self.get_xuid(gamertag)
            if not xuid:
                return None
            
            profile = await self.get_profile(xuid)
            if not profile:
                return None
            
            people_data = profile.get("people", [{}])[0]
            
            # Get recent activity
            recent_games = await self.get_recent_activity(xuid)
            
            # Determine if real gamer
            gamerscore = int(people_data.get("gamerScore", 0))
            is_real = (
                gamerscore >= self.MIN_GAMERSCORE_FOR_VERIFICATION or
                len(recent_games) > 0
            )
            
            return XboxUserProfile(
                gamertag=gamertag,
                xuid=xuid,
                gamerscore=gamerscore,
                account_tier=people_data.get("accountTier", "Unknown"),
                recent_games=recent_games,
                is_real_gamer=is_real
            )
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch Xbox profile for {gamertag}: {e}")
            return None
    
    async def get_xuid(self, gamertag: str) -> Optional[str]:
        """Search for a gamertag and return the XUID."""
        if not self.api_key:
            return None
            
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/search/{gamertag}"
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for result in data.get("people", []):
                        if result.get("gamertag").lower() == gamertag.lower():
                            return result.get("xuid")
                return None
    
    async def get_profile(self, xuid: str) -> Optional[Dict]:
        """Get profile details for a given XUID."""
        if not self.api_key:
            return None

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/player/{xuid}"
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    
    async def get_recent_activity(self, xuid: str, limit: int = 10) -> List[Dict]:
        """
        Get recent game activity for an Xbox user.
        """
        if not self.api_key:
            return []
        
        try:
            # Get activity feed
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/activity/{xuid}"
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        activities = []
                        
                        for activity in data.get("activityItems", [])[:limit]:
                            game_data = {
                                'name': activity.get('titleName', 'Unknown'),
                                'last_played': activity.get('date', None),
                                'activity_type': activity.get('activityItemType', 'Unknown'),
                                'is_supported': self._is_supported_game(
                                    activity.get('titleName', '')
                                )
                            }
                            activities.append(game_data)
                        
                        return activities
                    return []
        except Exception as e:
            print(f"[ERROR] Failed to fetch Xbox activity: {e}")
            return []
    
    def _is_supported_game(self, game_name: str) -> Tuple[bool, Optional[str]]:
        """Check if a game is in our supported list."""
        game_lower = game_name.lower()
        for game_type, variants in self.SUPPORTED_GAMES.items():
            for variant in variants:
                if variant.lower() in game_lower:
                    return True, game_type
        return False, None
    
    async def check_recent_gameplay(
        self, 
        gamertag: str, 
        game_type: str,
        hours_back: int = 2
    ) -> Dict:
        """
        Check if user played a specific game recently.
        
        Returns:
            {
                'played_recently': bool,
                'last_played': str,
                'activity_type': str,
                'game_found': bool,
                'game_name': str,
                'confidence': int
            }
        """
        if not self.api_key:
            return {
                'played_recently': False,
                'error': 'Xbox API not initialized',
                'confidence': 0
            }
        
        try:
            xuid = await self.get_xuid(gamertag)
            if not xuid:
                return {
                    'played_recently': False,
                    'error': f'Gamertag {gamertag} not found',
                    'confidence': 0
                }
            
            recent_activity = await self.get_recent_activity(xuid, limit=20)
            supported = self.SUPPORTED_GAMES.get(game_type, [game_type])
            
            result = {
                'played_recently': False,
                'last_played': None,
                'activity_type': None,
                'game_found': False,
                'game_name': None,
                'confidence': 0
            }
            
            # Check recent activities
            for activity in recent_activity:
                game_name = activity.get('name', '')
                
                for variant in supported:
                    if variant.lower() in game_name.lower():
                        result['game_found'] = True
                        result['game_name'] = game_name
                        result['last_played'] = activity.get('last_played')
                        result['activity_type'] = activity.get('activity_type')
                        result['played_recently'] = True
                        result['confidence'] = 85
                        break
            
            return result
            
        except Exception as e:
            return {
                'played_recently': False,
                'error': str(e),
                'confidence': 0
            }
    
    async def verify_identity(self, gamertag: str) -> Dict:
        """
        Comprehensive identity verification for anti-sybil.
        """
        profile = await self.get_full_profile(gamertag)
        
        if not profile:
            return {
                'verified': False,
                'reason': 'Could not fetch profile',
                'is_real_gamer': False
            }
        
        checks = {
            'has_gamerscore': profile.gamerscore >= 500,
            'has_gold_account': profile.account_tier == 'Gold',
            'has_recent_games': len(profile.recent_games) > 0,
            'has_played_supported_games': any(
                g.get('is_supported') for g in profile.recent_games
            )
        }
        
        # Score the verification
        score = 0
        if checks['has_gamerscore']:
            score += 40
        if checks['has_gold_account']:
            score += 30
        if checks['has_recent_games']:
            score += 15
        if checks['has_played_supported_games']:
            score += 15
        
        return {
            'verified': profile.is_real_gamer,
            'verification_score': score,
            'checks': checks,
            'profile': {
                'gamertag': profile.gamertag,
                'gamerscore': profile.gamerscore,
                'account_tier': profile.account_tier,
                'recent_games_count': len(profile.recent_games)
            },
            'is_real_gamer': profile.is_real_gamer
        }


# Export convenience functions
reader = XboxGameReader()


async def verify_xbox_identity(gamertag: str) -> Dict:
    """Quick access to Xbox identity verification"""
    return await reader.verify_identity(gamertag)


async def check_recent_gameplay_xbox(gamertag: str, game_type: str, hours_back: int = 2) -> Dict:
    """Quick access to recent gameplay check"""
    return await reader.check_recent_gameplay(gamertag, game_type, hours_back)


async def get_xbox_profile(gamertag: str) -> Optional[XboxUserProfile]:
    """Quick access to full profile"""
    return await reader.get_full_profile(gamertag)


if __name__ == "__main__":
    import asyncio
    import sys
    
    async def test():
        if len(sys.argv) > 1:
            test_gamertag = sys.argv[1]
            print(f"Testing Xbox Game Reader with gamertag: {test_gamertag}\n")
            
            reader = XboxGameReader()
            
            # Test identity verification
            print("=== Identity Verification ===")
            identity = await reader.verify_identity(test_gamertag)
            print(json.dumps(identity, indent=2))
            
            # Test recent gameplay check
            print("\n=== Recent FIFA/FC Gameplay ===")
            gameplay = await reader.check_recent_gameplay(test_gamertag, 'FIFA24', hours_back=24)
            print(json.dumps(gameplay, indent=2))
        else:
            print("Usage: python xbox_game_reader.py <gamertag>")
    
    asyncio.run(test())
