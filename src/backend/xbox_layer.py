import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

class XboxLayer:
    def __init__(self):
        self.api_key = os.getenv("XBL_IO_KEY")
        self.base_url = "https://xbl.io/api/v2"
        self.headers = {
            "X-Authorization": self.api_key,
            "Content-Type": "application/json"
        }

    async def get_xuid(self, gamertag: str):
        """
        Search for a gamertag and return the XUID.
        """
        if not self.api_key:
            return None
            
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/search/{gamertag}"
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # The search endpoint returns a list of results
                    for result in data.get("people", []):
                        if result.get("gamertag").lower() == gamertag.lower():
                            return result.get("xuid")
                return None

    async def get_profile(self, xuid: str):
        """
        Get profile details for a given XUID.
        """
        if not self.api_key:
            return None

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/player/{xuid}"
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("people", [{}])[0]
                return None

    async def verify_sybill(self, gamertag: str):
        """
        Check if the Xbox account is a 'Real Gamer'.
        1. Must have > 500 Gamerscore.
        """
        if not self.api_key:
            return {"status": "error", "message": "Xbox API key missing (XBL_IO_KEY)"}

        try:
            xuid = await self.get_xuid(gamertag)
            if not xuid:
                return {"status": "error", "message": f"Gamertag '{gamertag}' not found."}

            profile = await self.get_profile(xuid)
            if not profile:
                return {"status": "error", "message": "Could not retrieve profile data."}

            # Gamerscore is a good metric for account age/activity
            gamerscore = int(profile.get("gamerScore", 0))
            is_real = gamerscore >= 500

            return {
                "status": "success",
                "is_real": is_real,
                "gamerscore": gamerscore,
                "gamertag": gamertag,
                "xuid": xuid
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import asyncio
    async def test():
        xl = XboxLayer()
        res = await xl.verify_sybill("Major Nelson")
        print(res)
    # asyncio.run(test())
