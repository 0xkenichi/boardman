"""Self-custody passkey wallets (Circle Modular Wallets on Arc).

The player's wallet is an ERC-4337 smart account owned by a passkey on their
phone. Boardman only *prepares* transactions (an ``intent`` with exact calls)
and hands the player a one-time approve link; the browser signs and submits
the UserOperation; the backend advances a match only after it has read the
escrow's own event on chain. See docs/payments/SELF_CUSTODY_WALLETS.md.

Everything is off unless ``SELF_CUSTODY_WALLETS_ENABLED=1``.
"""
