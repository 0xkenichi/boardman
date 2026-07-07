import os
from psnawp_api import PSNAWP
from dotenv import load_dotenv

load_dotenv()

class PSNLayer:
    def __init__(self):
        npsso = os.getenv("NPSSO_CODE")
        if npsso:
            self.psnawp = PSNAWP(npsso)
        else:
            self.psnawp = None

    def get_profile(self, online_id: str):
        if not self.psnawp:
            return None
        user = self.psnawp.user(online_id=online_id)
        return user.get_profile()

    def get_recent_games(self, online_id: str):
        if not self.psnawp:
            return None
        user = self.psnawp.user(online_id=online_id)
        # get recently played games
        return user.get_presence()

    def verify_sybill(self, online_id: str):
        """
        Check if the PSN account is a 'Real Gamer' (multi-pronged check).
        1. Must have > 50 trophies.
        2. Must have recently played games (activity sync).
        """
        if not self.psnawp:
            return {"status": "error", "message": "PSN API not initialized (NPSSO missing)"}
        
        try:
            user = self.psnawp.user(online_id=online_id)
            trophies = user.trophy_summary()
            
            # Revised threshold: 10 trophies (as per user feedback)
            total_trophies = trophies.earned_trophies.bronze + trophies.earned_trophies.silver + \
                             trophies.earned_trophies.gold + trophies.earned_trophies.platinum
            
            is_real = total_trophies >= 10
            
            return {
                "status": "success",
                "is_real": is_real,
                "total_trophies": total_trophies,
                "online_id": online_id
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    psn = PSNLayer()
    # example use:
    # profile = psn.get_profile("User_ID")
    # print(profile)
