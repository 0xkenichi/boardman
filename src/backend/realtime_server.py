"""
realtime_server.py - WebSocket Server with Socket.io + Redis Pub/Sub Event Bus
Handles real-time connections, presence, chat, and notification fan-out.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Any

import redis.asyncio as redis
import socketio
from supabase import create_async_client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Environment ────────────────────────────────────────────────────────────────
SERVICE_PORT = int(os.getenv("REALTIME_PORT", os.getenv("PORT", 8001)))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase credentials for realtime server")

# ─── Clients ────────────────────────────────────────────────────────────────────
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=[
        "https://playingsidequest.fun",
        "https://staging.playingsidequest.fun",
        "https://app.playingsidequest.fun",
        "http://localhost:3000"
    ],
    logger=True,
    engineio_logger=True
)

sio_app = socketio.ASGIApp(sio)

redis_client: redis.Redis = None
db = None  # Will hold AsyncClient

# ─── Connection Tracking ────────────────────────────────────────────────────────
# profile_id -> set of socket IDs
connected_profiles: Dict[str, Set[str]] = {}
# socket ID -> profile metadata
socket_metadata: Dict[str, Dict[str, Any]] = {}

# ─── Initialization ─────────────────────────────────────────────────────────────
async def initialize():
    global redis_client, db
    redis_client = await redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    db = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Realtime server initialized (Redis + Supabase async)")

# ─── Event Bus (Redis Pub/Sub) ──────────────────────────────────────────────────
async def publish_event(event_type: str, payload: dict, recipient_id: str = None):
    """
    Publish an event to Redis channels.
    Events are fanned-out to: WebSocket targets, notification queues, external services.
    """
    event = {
        "type": event_type,
        "payload": payload,
        "recipient_id": recipient_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # 1. Persist to event_bus_log for audit/debug
    try:
        await db.table("event_bus_log").insert({
            "event_type": event_type,
            "event_key": payload.get("event_key"),
            "payload": event,
            "status": "pending"
        }).execute()
    except Exception as e:
        logger.warning(f"Event bus log insert failed: {e}")
    
    # 2. Publish to Redis pub/sub channels
    channels = []
    
    # Global channel for all connected clients
    channels.append("sidequest:global")
    
    # Per-user channel for targeted notifications
    if recipient_id:
        channels.append(f"sidequest:user:{recipient_id}")
    
    # Type-specific channel (e.g., for chat, notifications)
    channels.append(f"sidequest:type:{event_type}")
    
    for channel in channels:
        try:
            await redis_client.publish(channel, json.dumps(event))
        except Exception as e:
            logger.error(f"Redis publish to {channel} failed: {e}")

# ─── Socket.IO Event Handlers ───────────────────────────────────────────────────

@sio.event
async def connect(sid: str, environ: dict, auth: dict = None):
    """
    Client connects. Authenticate via token, track presence.
    """
    try:
        # Extract auth token from query params or auth dict
        token = auth.get("token") if auth else environ.get("token")
        if not token:
            # Try extracting from query string
            query_string = environ.get("QUERY_STRING", "")
            for part in query_string.split("&"):
                if part.startswith("token="):
                    token = part.split("=", 1)[1]
                    break
        
        if not token:
            logger.warning(f"Unauthenticated connection attempt: {sid}")
            return False  # Reject connection
        
        # Verify token and get profile
        # Note: In production, verify JWT from Supabase Auth
        profile = await verify_token_and_get_profile(token)
        if not profile:
            logger.warning(f"Invalid token for connection {sid}")
            return False
        
        profile_id = str(profile["id"])
        
        # Track connection
        if profile_id not in connected_profiles:
            connected_profiles[profile_id] = set()
        connected_profiles[profile_id].add(sid)
        
        socket_metadata[sid] = {
            "profile_id": profile_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "user_agent": environ.get("HTTP_USER_AGENT"),
            "ip_address": environ.get("REMOTE_ADDR")
        }
        
        # Update presence to online (with TTL heartbeat)
        await update_presence(profile_id, "online", {
            "platform": "web" if "Mobile" not in (environ.get("HTTP_USER_AGENT") or "") else "mobile",
            "app_version": None,  # Extract from user-agent or client handshake
            "device_id": None
        })
        
        logger.info(f"Client connected: profile={profile_id}, socket={sid}")
        
        # Broadcast presence update to friends
        await publish_event("user.online", {"profile_id": profile_id}, recipient_id=None)
        
        return True
        
    except Exception as e:
        logger.error(f"Connection handler error: {e}", exc_info=True)
        return False

@sio.event
async def disconnect(sid: str):
    """
    Client disconnects. Update presence, clean up.
    """
    try:
        meta = socket_metadata.get(sid)
        if not meta:
            return
        
        profile_id = meta["profile_id"]
        
        # Remove from tracking
        if profile_id in connected_profiles:
            connected_profiles[profile_id].discard(sid)
            if not connected_profiles[profile_id]:
                # No more connections for this user - mark offline
                await update_presence(profile_id, "offline")
                del connected_profiles[profile_id]
        
        del socket_metadata[sid]
        
        logger.info(f"Client disconnected: profile={profile_id}, socket={sid}")
        
        # Broadcast offline status to friends
        await publish_event("user.offline", {"profile_id": profile_id}, recipient_id=None)
        
    except Exception as e:
        logger.error(f"Disconnect handler error: {e}")

@sio.event
async def heartbeat(sid: str, data: dict = None):
    """
    Client heartbeat to keep presence alive.
    """
    meta = socket_metadata.get(sid)
    if meta:
        profile_id = meta["profile_id"]
        # Refresh presence last_seen
        try:
            await db.table("presence") \
                .update({"last_seen": datetime.now(timezone.utc).isoformat()}) \
                .eq("profile_id", profile_id).execute()
        except Exception as e:
            logger.warning(f"Heartbeat update failed: {e}")
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

# ─── Chat ────────────────────────────────────────────────────────────────────────

@sio.event
async def join_chat(sid: str, data: dict):
    """
    Join a quest chat room.
    """
    chat_id = data.get("chat_id")
    if not chat_id:
        return {"error": "chat_id required"}
    
    # Verify user is participant (optional - can be done client-side too)
    await sio.enter_room(sid, f"chat:{chat_id}")
    return {"status": "joined", "room": f"chat:{chat_id}"}

@sio.event
async def leave_chat(sid: str, data: dict):
    """
    Leave a quest chat room.
    """
    chat_id = data.get("chat_id")
    if chat_id:
        await sio.leave_room(sid, f"chat:{chat_id}")
    return {"status": "left"}

@sio.event
async def send_message(sid: str, data: dict):
    """
    Broadcast a chat message to all participants in the room.
    """
    try:
        chat_id = data.get("chat_id") or data.get("room_id")
        content = data.get("content")
        
        if not chat_id or not content:
            return {"error": "chat_id (or room_id) and content required"}
        
        meta = socket_metadata.get(sid)
        if not meta:
            return {"error": "unauthenticated"}
        
        profile_id = meta["profile_id"]
        
        # Resolve room type (quest room vs DM)
        room_check = await db.table("chat_rooms").select("id").eq("id", chat_id).maybe_single().execute()
        is_room = bool(room_check.data)
        
        # Store message in DB (chat_messages table — migration 015 schema)
        result = await db.table("chat_messages").insert({
            "room_id":     chat_id if is_room else None,
            "dm_room_id":  None if is_room else chat_id,
            "sender_id":   profile_id,
            "message_type": data.get("message_type", "text"),
            "body":        content,
            "metadata":    data.get("metadata", {})
        }).execute()
        
        message = result.data[0] if result.data else None
        if not message:
            return {"error": "failed to store message"}
        
        # Fetch sender profile for display name
        profile_res = await db.table("profiles") \
            .select("display_name, avatar_url") \
            .eq("id", profile_id).single().execute()
        profile = profile_res.data if profile_res.data else {}
        
        # Prepare message payload
        msg_payload = {
            "id": message["id"],
            "room_id": message.get("room_id"),
            "dm_room_id": message.get("dm_room_id"),
            "sender_id": profile_id,
            "display_name": profile.get("display_name"),
            "avatar_url": profile.get("avatar_url"),
            "body": content,
            "message_type": message["message_type"],
            "created_at": message["created_at"]
        }
        
        # Broadcast to room
        await sio.emit("new_message", msg_payload, room=f"chat:{chat_id}")
        
        # Also emit to sender (confirmation)
        await sio.emit("message_sent", msg_payload, to=sid)
        
        return {"success": True, "message": msg_payload}
        
    except Exception as e:
        logger.error(f"Send message error: {e}")
        return {"error": str(e)}

# ─── Notifications ───────────────────────────────────────────────────────────────

@sio.event
async def subscribe_notifications(sid: str, data: dict):
    """
    Subscribe to personal notifications room.
    """
    meta = socket_metadata.get(sid)
    if not meta:
        return {"error": "unauthenticated"}
    
    profile_id = meta["profile_id"]
    room_name = f"notifications:{profile_id}"
    await sio.enter_room(sid, room_name)
    
    # Also subscribe to global announcements
    await sio.enter_room(sid, "notifications:global")
    
    return {"status": "subscribed", "rooms": [room_name, "notifications:global"]}

@sio.event
async def mark_notification_read(sid: str, data: dict):
    """
    Mark notification as read.
    """
    notification_id = data.get("notification_id")
    meta = socket_metadata.get(sid)
    if not meta or not notification_id:
        return {"error": "invalid"}
    
    profile_id = meta["profile_id"]
    
    # Verify ownership
    result = await db.table("notifications") \
        .update({"status": "read", "read_at": datetime.now(timezone.utc).isoformat()}) \
        .eq("id", notification_id) \
        .eq("recipient_id", profile_id) \
        .execute()
    
    if result.data:
        await sio.emit("notification_read", {"notification_id": notification_id}, room=f"notifications:{profile_id}")
        return {"success": True}
    return {"error": "not found or unauthorized"}

# ─── Presence ────────────────────────────────────────────────────────────────────

@sio.event
async def update_status(sid: str, data: dict):
    """
    Manually update presence status (idle, invisible, etc.)
    """
    meta = socket_metadata.get(sid)
    if not meta:
        return {"error": "unauthenticated"}
    
    profile_id = meta["profile_id"]
    new_status = data.get("status")
    if new_status not in ("online", "offline", "idle", "invisible"):
        return {"error": "invalid status"}
    
    await db.table("presence") \
        .update({"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}) \
        .eq("profile_id", profile_id).execute()
    
    # Broadcast to friends if status change is significant
    if new_status in ("online", "offline"):
        await publish_event("user.presence_update", {
            "profile_id": profile_id,
            "status": new_status
        }, recipient_id=None)
    
    return {"status": new_status}

# ─── Helper Functions ────────────────────────────────────────────────────────────

async def verify_token_and_get_profile(token: str) -> Optional[dict]:
    """
    Verify JWT token from Supabase Auth and return profile.
    Uses proper JWT signature verification via Supabase JWKS.
    """
    try:
        from utils.auth import verify_supabase_token
        import jwt

        # Try HS256 with backend JWT_SECRET_KEY first
        jwt_secret = os.getenv("JWT_SECRET_KEY")
        if jwt_secret:
            try:
                decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
                user_id = decoded.get("sub")
                if user_id:
                    res = await db.table("profiles") \
                        .select("*") \
                        .eq("id", user_id) \
                        .maybe_single() \
                        .execute()
                    if res.data:
                        return res.data
            except jwt.InvalidTokenError:
                pass

        # Try RS256 with Supabase JWKS
        try:
            user_id = verify_supabase_token(token)
            if user_id:
                res = await db.table("profiles") \
                    .select("*") \
                    .eq("linked_supabase_uid", user_id) \
                    .maybe_single() \
                    .execute()
                if res.data:
                    return res.data

                # Also try by id if token uses UUID directly
                res2 = await db.table("profiles") \
                    .select("*") \
                    .eq("id", user_id) \
                    .maybe_single() \
                    .execute()
                if res2.data:
                    return res2.data
        except Exception:
            pass

        return None

    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return None

async def update_presence(profile_id: str, status: str, device_info: dict = None):
    """
    Upsert presence record. Uses Redis TTL for auto-expiry.
    """
    try:
        data = {
            "profile_id": profile_id,
            "status": status,
            "last_seen": datetime.now(timezone.utc).isoformat()
        }
        if device_info:
            data["device_info"] = device_info
        
        # UPSERT
        await db.table("presence") \
            .upsert(data, on_conflict="profile_id") \
            .execute()
        
        # Set Redis TTL key for heartbeat tracking (optional cache layer)
        ttl_key = f"presence:ttl:{profile_id}"
        await redis_client.setex(ttl_key, 120, status)  # 2-min TTL
        
    except Exception as e:
        logger.error(f"Presence update failed for {profile_id}: {e}")

# ─── Start Redis Listener for Cross-Process Events ──────────────────────────────

async def start_redis_listener():
    """
    Subscribe to Redis channels and relay events to connected Socket.IO clients.
    This allows cross-process event broadcasting if multiple server instances.
    """
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("sidequest:global")
    
    logger.info("Redis event listener started")
    
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        
        try:
            data = json.loads(message["data"])
            event_type = data.get("type")
            payload = data.get("payload", {})
            
            # Emit to appropriate Socket.IO rooms
            if event_type == "user.online":
                # Broadcast online status to all interested clients
                await sio.emit("user_online", payload, room="presence:global")
            elif event_type == "user.offline":
                await sio.emit("user_offline", payload, room="presence:global")
            elif event_type.startswith("notification."):
                # Fan-out to specific user
                recipient_id = data.get("recipient_id")
                if recipient_id:
                    await sio.emit("notification", payload, room=f"notifications:{recipient_id}")
            elif event_type.startswith("chat."):
                chat_id = payload.get("chat_id")
                if chat_id:
                    await sio.emit("chat_event", payload, room=f"chat:{chat_id}")
                    
        except Exception as e:
            logger.error(f"Redis listener error: {e}")

# ─── Graceful Shutdown ──────────────────────────────────────────────────────────

async def shutdown():
    await redis_client.close()
    logger.info("Realtime server shutdown complete")
