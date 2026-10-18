"""Naira on/off-ramp through Paycrest (https://docs.paycrest.io), bridged to Arc.

Modules: ``config`` (flags, limits), ``client`` (Sender API v2), ``models``,
``store`` (orders + state machine, webhook dedupe, Base wallets, bridge
legs), ``quotes``, ``onramp``, ``offramp``, ``events`` (webhook/poll
updates), ``reconcile`` (worker). Everything is off unless
``PAYCREST_ENABLED=1`` and ``REAL_MONEY_ENABLED=1``. See
docs/payments/PAYCREST.md.
"""
