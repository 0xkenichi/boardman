#!/usr/bin/env python3
"""
ClawStation Bot Service Wrapper
Runs Telegram bot + exposes health endpoint for Zo service management
"""

import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

# Health check server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "service": "clawstation-telegram-bot"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress health check logs

def run_health_server():
    port = int(os.getenv('PORT', 8090))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"[SERVICE] Health endpoint running on port {port}")
    server.serve_forever()

# Main bot runner
async def run_bot():
    from main import main as bot_main
    await bot_main()

if __name__ == "__main__":
    # Start health server in background thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # Run Telegram bot in main thread
    print("[SERVICE] Starting ClawStation Telegram Bot...")
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n[SERVICE] Shutting down...")