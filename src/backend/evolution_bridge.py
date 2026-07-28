"""
evolution_bridge.py — STUB (WhatsApp removed, Telegram-only)
All methods are no-ops. Kept so existing code that calls bridge.send_message() doesn't crash.
"""


class EvolutionBridge:
    def send_message(self, to: str, text: str, **kwargs):
        pass

    def send_interactive_buttons(self, to: str, text: str, buttons: list, **kwargs):
        pass

    def send_image(self, to: str, image_url: str, caption: str = "", **kwargs):
        pass
