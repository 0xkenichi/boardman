"""
PSN Game Activity Reader for ClawStation
Reads PSN activity to verify:
- Username authenticity
- Recently played games
- Match outcomes and timestamps
- Trophy/achievement activity
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from psnawp_api import PSNAWP
from dotenv import load_dotenv

load_dotenv()


@dataclass
class PSNMatchResult:
    """Represents a PSN match result"""
    game_name: str
    match_date: datetime
    duration_minutes: int
    trophies_earned: int
    is_win: Optional[bool] = None
    score: Optional[str] = None


@dataclass
class PSNUserProfile:
    """Enhanced PSN user profile data"""
    online_id: str
    account_id: str
    total_trophies: int
    platinum_count: int
    gold_count: int
    silver_count: int
    bronze_count: int
    level: int
    recent_games: List[Dict]
    is_real_gamer: bool
    account_age_days: int


class PSNGameReader:
    """
    Reads and analyzes PSN game activity for match verification.
    """
    
    # Game IDs for supported titles
    SUPPORTED_GAMES = {
        'FIFA24': ['FIFA24', 'FIFA 24', 'EA SPORTS FC 24', 'FC24', 'FC 24'],
        'FC25': ['FC25', 'FC 25', 'EA SPORTS FC 25'],
        'NBA2K24': ['NBA2K24', 'NBA 2K24'],
        'NBA2K25': ['NBA2K25', 'NBA 2K25'],
    }
    
    # Minimum trophies for "real gamer" verification
    MIN_TROPHIES_FOR_VERIFICATION = 10
    
    def __init__(self):
        npsso = os.getenv("NPSSO_CODE")
        if npsso:
            self.psnawp = PSNAWP(npsso)
        else:
            self.psnawp = None
            print("[WARN] NPSSO_CODE not set. PSN API unavailable.")
    
    def get_full_profile(self, online_id: str) -> Optional[PSNUserProfile]:
        """
        Get comprehensive PSN user profile with verification status.
        """
        if not self.psnawp:
            return None
        
        try:
            user = self.psnawp.user(online_id=online_id)
            
            # Get trophy summary
            trophies = user.trophy_summary()
            total = (trophies.earned_trophies.bronze + 
                    trophies.earned_trophies.silver + 
                    trophies.earned_trophies.gold + 
                    trophies.earned_trophies.platinum)
            
            # Get presence/activity
            presence = user.get_presence()
            recent_games = []
            
            if hasattr(presence, 'played'):
                for title in presence.played:
                    game_data = {
                        'name': getattr(title, 'title_name', 'Unknown'),
                        'last_played': getattr(title, 'last_played_date', None),
                        'play_duration': getattr(title, 'play_duration', 0),
                        'is_supported': self._is_supported_game(
                            getattr(title, 'title_name', '')
                        )
                    }
                    recent_games.append(game_data)
            
            # Get profile info for account age
            profile = user.get_profile()
            account_creation = getattr(profile, 'created_date', None)
            account_age = 0
            if account_creation:
                try:
                    created = datetime.fromisoformat(account_creation.replace('Z', '+00:00'))
                    account_age = (datetime.now(created.tzinfo) - created).days
                except:
                    pass
            
            # Determine if real gamer
            is_real = (
                total >= self.MIN_TROPHIES_FOR_VERIFICATION or
                account_age > 30 or
                len(recent_games) > 0
            )
            
            return PSNUserProfile(
                online_id=online_id,
                account_id=getattr(profile, 'account_id', ''),
                total_trophies=total,
                platinum_count=trophies.earned_trophies.platinum,
                gold_count=trophies.earned_trophies.gold,
                silver_count=trophies.earned_trophies.silver,
                bronze_count=trophies.earned_trophies.bronze,
                level=trophies.trophy_level,
                recent_games=recent_games,
                is_real_gamer=is_real,
                account_age_days=account_age
            )
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch PSN profile for {online_id}: {e}")
            return None
    
    def _is_supported_game(self, game_name: str) -> Tuple[bool, str]:
        """Check if a game is in our supported list."""
        game_lower = game_name.lower()
        for game_type, variants in self.SUPPORTED_GAMES.items():
            for variant in variants:
                if variant.lower() in game_lower:
                    return True, game_type
        return False, None
    
    def check_recent_gameplay(
        self, 
        online_id: str, 
        game_type: str,
        hours_back: int = 2
    ) -> Dict:
        """
        Check if user played a specific game recently.
        
        Returns:
            {
                'played_recently': bool,
                'last_played': datetime,
                'duration_minutes': int,
                'game_found': bool,
                'game_name': str,
                'confidence': int
            }
        """
        if not self.psnawp:
            return {
                'played_recently': False,
                'error': 'PSN API not initialized',
                'confidence': 0
            }
        
        try:
            user = self.psnawp.user(online_id=online_id)
            presence = user.get_presence()
            
            # Get supported game variants
            supported = self.SUPPORTED_GAMES.get(game_type, [game_type])
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            result = {
                'played_recently': False,
                'last_played': None,
                'duration_minutes': 0,
                'game_found': False,
                'game_name': None,
                'confidence': 0
            }
            
            if hasattr(presence, 'played'):
                for title in presence.played:
                    game_name = getattr(title, 'title_name', '')
                    
                    # Check if this is a supported game
                    for variant in supported:
                        if variant.lower() in game_name.lower():
                            result['game_found'] = True
                            result['game_name'] = game_name
                            
                            # Parse last played time
                            last_played_str = getattr(title, 'last_played_date', None)
                            if last_played_str:
                                try:
                                    last_played = datetime.fromisoformat(
                                        last_played_str.replace('Z', '+00:00')
                                    )
                                    result['last_played'] = last_played.isoformat()
                                    
                                    # Check if within our window
                                    if last_played > cutoff_time:
                                        result['played_recently'] = True
                                        result['confidence'] = 90
                                    else:
                                        hours_ago = (datetime.now(last_played.tzinfo) - last_played).total_seconds() / 3600
                                        if hours_ago <= 24:
                                            result['confidence'] = 70
                                        else:
                                            result['confidence'] = 40
                                    
                                except Exception as e:
                                    print(f"[WARN] Could not parse date: {e}")
                            
                            # Get play duration if available
                            duration = getattr(title, 'play_duration', 0)
                            if duration:
                                result['duration_minutes'] = duration // 60
                            
                            break
            
            # Also check currently playing
            if hasattr(presence, 'basic_presence'):
                current = presence.basic_presence
                if hasattr(current, 'game_title_info'):
                    current_game = current.game_title_info
                    if current_game:
                        for variant in supported:
                            if variant.lower() in str(current_game).lower():
                                result['played_recently'] = True
                                result['confidence'] = 95
                                result['currently_playing'] = True
                                break
            
            return result
            
        except Exception as e:
            return {
                'played_recently': False,
                'error': str(e),
                'confidence': 0
            }
    
    def get_match_history(
        self, 
        online_id: str, 
        game_type: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get recent match history for a specific game.
        Note: Full match history requires game-specific API access.
        This returns available activity data.
        """
        if not self.psnawp:
            return []
        
        try:
            user = self.psnawp.user(online_id=online_id)
            
            # Get trophy data for recent activity
            trophies = user.trophy_summary()
            
            # Get played titles
            presence = user.get_presence()
            matches = []
            
            supported = self.SUPPORTED_GAMES.get(game_type, [game_type])
            
            if hasattr(presence, 'played'):
                for title in presence.played[:limit]:
                    game_name = getattr(title, 'title_name', '')
                    
                    for variant in supported:
                        if variant.lower() in game_name.lower():
                            match_data = {
                                'game_name': game_name,
                                'last_played': getattr(title, 'last_played_date', None),
                                'play_duration_minutes': getattr(title, 'play_duration', 0) // 60,
                                'trophies_earned': 0  # Would need per-game trophy data
                            }
                            matches.append(match_data)
                            break
            
            return matches
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch match history: {e}")
            return []
    
    def verify_identity(self, online_id: str) -> Dict:
        """
        Comprehensive identity verification for anti-sybil.
        """
        profile = self.get_full_profile(online_id)
        
        if not profile:
            return {
                'verified': False,
                'reason': 'Could not fetch profile',
                'is_real_gamer': False
            }
        
        checks = {
            'has_trophies': profile.total_trophies >= 10,
            'has_platinum': profile.platinum_count >= 1,
            'account_age': profile.account_age_days >= 30,
            'has_recent_games': len(profile.recent_games) > 0,
            'has_played_supported_games': any(
                g.get('is_supported') for g in profile.recent_games
            )
        }
        
        # Score the verification
        score = 0
        if checks['has_trophies']:
            score += 30
        if checks['has_platinum']:
            score += 20
        if checks['account_age']:
            score += 20
        if checks['has_recent_games']:
            score += 15
        if checks['has_played_supported_games']:
            score += 15
        
        return {
            'verified': profile.is_real_gamer,
            'verification_score': score,
            'checks': checks,
            'profile': {
                'online_id': profile.online_id,
                'total_trophies': profile.total_trophies,
                'level': profile.level,
                'account_age_days': profile.account_age_days,
                'recent_games_count': len(profile.recent_games)
            },
            'is_real_gamer': profile.is_real_gamer
        }


# Export convenience functions
reader = PSNGameReader()


def verify_psn_identity(online_id: str) -> Dict:
    """Quick access to PSN identity verification"""
    return reader.verify_identity(online_id)


def check_recent_gameplay(online_id: str, game_type: str, hours_back: int = 2) -> Dict:
    """Quick access to recent gameplay check"""
    return reader.check_recent_gameplay(online_id, game_type, hours_back)


def get_psn_profile(online_id: str) -> Optional[PSNUserProfile]:
    """Quick access to full profile"""
    return reader.get_full_profile(online_id)


if __name__ == "__main__":
    # Test the reader
    import sys
    
    if len(sys.argv) > 1:
        test_id = sys.argv[1]
        print(f"Testing PSN Game Reader with ID: {test_id}\n")
        
        reader = PSNGameReader()
        
        # Test identity verification
        print("=== Identity Verification ===")
        identity = reader.verify_identity(test_id)
        print(json.dumps(identity, indent=2))
        
        # Test recent gameplay check
        print("\n=== Recent FIFA/FC Gameplay ===")
        gameplay = reader.check_recent_gameplay(test_id, 'FIFA24', hours_back=24)
        print(json.dumps(gameplay, indent=2))
    else:
        print("Usage: python psn_game_reader.py <online_id>")
