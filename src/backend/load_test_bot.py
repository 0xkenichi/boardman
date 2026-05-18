#!/usr/bin/env python3
"""
Load test script for sideQuest Telegram Bot
Simulates 5000 concurrent users to validate rate limiting and performance
"""

import asyncio
import aiohttp
import time
import logging
from typing import List
from dataclasses import dataclass
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    user_id: int
    chat_id: int
    command_count: int = 0
    error_count: int = 0
    last_request: float = 0


class BotLoadTester:
    def __init__(self, bot_token: str, num_users: int = 5000):
        self.bot_token = bot_token
        self.num_users = num_users
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.sessions: List[UserSession] = []
        self.metrics = defaultdict(int)
        self.start_time = None
        self.semaphore = asyncio.Semaphore(30)  # Global rate limit: 30/sec
        
    async def send_message(self, session: UserSession, text: str) -> bool:
        """Send a message respecting rate limits."""
        async with self.semaphore:
            # Per-chat rate limit: 1 msg/sec
            now = time.time()
            elapsed = now - session.last_request
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            
            session.last_request = time.time()
            session.command_count += 1
            
            try:
                async with aiohttp.ClientSession() as http_session:
                    async with http_session.post(
                        f"{self.base_url}/sendMessage",
                        json={
                            "chat_id": session.chat_id,
                            "text": text,
                            "parse_mode": "Markdown",
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 429:
                            # Rate limited - exponential backoff
                            retry_after = int(resp.headers.get('Retry-After', 2))
                            logger.warning(f"User {session.user_id}: rate limited, waiting {retry_after}s")
                            await asyncio.sleep(retry_after)
                            session.error_count += 1
                            self.metrics['rate_limited'] += 1
                            return False
                        elif resp.status == 403:
                            logger.info(f"User {session.user_id}: blocked bot")
                            session.error_count += 1
                            self.metrics['blocked'] += 1
                            return False
                        elif resp.status != 200:
                            logger.error(f"User {session.user_id}: HTTP {resp.status}")
                            session.error_count += 1
                            self.metrics['errors'] += 1
                            return False
                        
                        self.metrics['success'] += 1
                        return True
                        
            except asyncio.TimeoutError:
                logger.error(f"User {session.user_id}: timeout")
                session.error_count += 1
                self.metrics['timeouts'] += 1
                return False
            except Exception as e:
                logger.error(f"User {session.user_id}: {e}")
                session.error_count += 1
                self.metrics['exceptions'] += 1
                return False
    
    async def simulate_user(self, session: UserSession, duration: int = 60):
        """Simulate a single user's activity."""
        end_time = time.time() + duration
        commands = [
            "/start",
            "/wallet",
            "/profile",
            "/leaderboard",
        ]
        
        while time.time() < end_time:
            cmd = commands[session.command_count % len(commands)]
            success = await self.send_message(session, cmd)
            
            if not success:
                await asyncio.sleep(2)  # Back off on errors
            
            # Random delay between commands (0.5-3 seconds)
            await asyncio.sleep(0.5 + (hash(session.user_id) % 25) / 10)
    
    async def run_load_test(self, duration: int = 60):
        """Run load test with specified number of users."""
        logger.info(f"🚀 Starting load test: {self.num_users} users for {duration}s")
        
        # Create sessions (using fake chat IDs for testing)
        for i in range(self.num_users):
            session = UserSession(
                user_id=1000000 + i,
                chat_id=1000000 + i,
            )
            self.sessions.append(session)
        
        self.start_time = time.time()
        
        # Run users in batches to avoid overwhelming the system
        batch_size = 100
        for i in range(0, self.num_users, batch_size):
            batch = self.sessions[i:i+batch_size]
            logger.info(f"Starting batch {i//batch_size + 1}/{(self.num_users + batch_size - 1)//batch_size}")
            
            tasks = [self.simulate_user(session, duration) for session in batch]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Brief pause between batches
            if i + batch_size < self.num_users:
                await asyncio.sleep(5)
        
        elapsed = time.time() - self.start_time
        self.print_report(elapsed)
    
    def print_report(self, elapsed: float):
        """Print load test results."""
        total_requests = sum(s.command_count for s in self.sessions)
        total_errors = sum(s.error_count for s in self.sessions)
        
        logger.info("\n" + "="*60)
        logger.info("📊 LOAD TEST RESULTS")
        logger.info("="*60)
        logger.info(f"Duration:        {elapsed:.1f}s")
        logger.info(f"Total users:     {self.num_users}")
        logger.info(f"Total requests:  {total_requests}")
        logger.info(f"Requests/sec:    {total_requests/elapsed:.1f}")
        logger.info(f"Successful:      {self.metrics['success']}")
        logger.info(f"Rate limited:    {self.metrics['rate_limited']}")
        logger.info(f"Errors:          {self.metrics['errors']}")
        logger.info(f"Timeouts:        {self.metrics['timeouts']}")
        logger.info(f"Blocked:         {self.metrics['blocked']}")
        logger.info(f"Exceptions:      {self.metrics['exceptions']}")
        logger.info("="*60)
        
        # Per-user stats
        error_rates = [s.error_count / max(s.command_count, 1) for s in self.sessions]
        avg_error_rate = sum(error_rates) / len(error_rates) * 100
        logger.info(f"Avg error rate:  {avg_error_rate:.1f}%")
        logger.info("="*60)


async def main():
    import os
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return
    
    # Test with increasing user counts
    tester = BotLoadTester(bot_token, num_users=5000)
    await tester.run_load_test(duration=30)


if __name__ == "__main__":
    asyncio.run(main())