"""Boardman on every chat app (docs/channels/CHANNELS_DESIGN.md).

``core`` holds the channel-agnostic pieces (identity, conversation state,
flows, notifications, the renderer contract). ``telegram``, ``whatsapp`` and
``fake`` are adapters. Nothing here changes Telegram behaviour unless a flag in
``config`` turns it on.
"""
