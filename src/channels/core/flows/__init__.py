"""One module per flow. Each exposes ``start(ctx)``, ``on_button(ctx, act, arg)``
and, when it takes typed input, ``on_text(ctx, text)``. Flows call actions,
never channel APIs, and re-validate everything a stale button could carry.
"""
