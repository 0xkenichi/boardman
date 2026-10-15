"""Telegram adapter: aiogram updates in, core messages rendered as HTML out.

Legacy handlers in ``src/bot`` stay registered; ``CHANNELS_CORE_FLOWS`` picks
which entry points the core takes over (strangler pattern, rollback = config).
"""
