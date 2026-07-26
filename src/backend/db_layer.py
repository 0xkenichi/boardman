"""
db_layer.py — Compatibility shim.

All methods have been moved to backend/repositories/*.  This file re-exports
them as a DBLayer instance so existing callers
    from db_layer import DBLayer
    db = DBLayer()
    db.get_profile_by_id(...)
continue to work without modification.

DO NOT add new logic here.  All real implementation lives in repositories/.
"""
import os
import re
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase_client import get_supabase
from dotenv import load_dotenv

# ─── Import all repository functions as private names ─────────────────────────
from repositories.profiles import (
    get_profile_by_platform as _get_profile_by_platform,
    get_profile_by_email as _get_profile_by_email,
    get_profile_by_circle_wallet as _get_profile_by_circle_wallet,
    get_or_create_profile as _get_or_create_profile,
    link_platform_to_profile as _link_platform_to_profile,
    link_email_to_profile as _link_email_to_profile,
    get_all_profiles as _get_all_profiles,
    get_profile_by_id as _get_profile_by_id,
    get_profile_by_uuid as _get_profile_by_uuid,
    get_profile_by_flw_tx_ref_prefix as _get_profile_by_flw_tx_ref_prefix,
    update_profile_field as _update_profile_field,
    create_profile as _create_profile,
    update_profile as _update_profile,
    increment_public_stats as _increment_public_stats,
    add_creator_badge as _add_creator_badge,
    set_content_creator as _set_content_creator,
    set_verified as _set_verified,
    set_whitelisted as _set_whitelisted,
    get_whitelist_count as _get_whitelist_count,
    get_user_count as _get_user_count,
    get_early_adopter_count as _get_early_adopter_count,
)
from repositories.quests import (
    create_friend_circle as _create_friend_circle,
    get_user_circles as _get_user_circles,
    get_circle_by_id as _get_circle_by_id,
    add_member_to_circle as _add_member_to_circle,
    remove_member_from_circle as _remove_member_from_circle,
    get_circle_members as _get_circle_members,
    update_circle_visibility as _update_circle_visibility,
    delete_friend_circle as _delete_friend_circle,
    get_all_bets as _get_all_bets,
    get_bets_by_user as _get_bets_by_user,
    create_bet as _create_bet,
    get_open_bets as _get_open_bets,
    get_public_challenges as _get_public_challenges,
    match_bet as _match_bet,
    approve_bet as _approve_bet,
    resolve_bet as _resolve_bet,
    cancel_bet as _cancel_bet,
    get_bet as _get_bet,
    create_challenge as _create_challenge,
    get_challenge as _get_challenge,
    accept_challenge as _accept_challenge,
    decline_challenge as _decline_challenge,
    expire_challenge as _expire_challenge,
    get_active_challenges as _get_active_challenges,
    get_player_challenges as _get_player_challenges,
    create_session as _create_session,
    get_session as _get_session,
    update_session_status as _update_session_status,
    get_sessions_by_player as _get_sessions_by_player,
    get_all_tags as _get_all_tags,
    get_user_tags as _get_user_tags,
    add_user_tag as _add_user_tag,
    remove_user_tag as _remove_user_tag,
)
from repositories.escrow import (
    get_match_reports as _get_match_reports,
    create_report as _create_report,
    get_reports_for_bet as _get_reports_for_bet,
    create_escrow_entry as _create_escrow_entry,
    get_escrow_entries_by_bet as _get_escrow_entries_by_bet,
    get_escrow_entries_by_user as _get_escrow_entries_by_user,
    update_escrow_entry_status as _update_escrow_entry_status,
    get_locked_escrow_amount_for_bet as _get_locked_escrow_amount_for_bet,
    lock_funds as _lock_funds,
    unlock_funds as _unlock_funds,
)
from repositories.wallet import (
    update_balance as _update_balance,
    award_play_points as _award_play_points,
    get_available_balance as _get_available_balance,
    get_play_points as _get_play_points,
    link_wallet as _link_wallet,
    create_withdrawal as _create_withdrawal,
    confirm_withdrawal as _confirm_withdrawal,
    get_withdrawals_by_user as _get_withdrawals_by_user,
    get_virtual_account as _get_virtual_account,
    save_virtual_account as _save_virtual_account,
    has_flw_tx_been_processed as _has_flw_tx_been_processed,
    mark_flw_tx_processed as _mark_flw_tx_processed,
    has_crypto_tx_been_processed as _has_crypto_tx_been_processed,
    mark_crypto_tx_processed as _mark_crypto_tx_processed,
    update_bet_on_chain_tx as _update_bet_on_chain_tx,
    set_bet_on_chain_pool_id as _set_bet_on_chain_pool_id,
)
from repositories.analytics import (
    get_top10_qualified as _get_top10_qualified,
    is_top10_player as _is_top10_player,
    get_player_reputation as _get_player_reputation,
    get_game_leaderboard as _get_game_leaderboard,
    get_region_leaderboard as _get_region_leaderboard,
    get_tier_leaderboard as _get_tier_leaderboard,
    get_leaderboard_by_state as _get_leaderboard_by_state,
    create_proof_of_play as _create_proof_of_play,
    get_proof_of_play as _get_proof_of_play,
    create_base_market as _create_base_market,
    get_base_market as _get_base_market,
    update_base_market_status as _update_base_market_status,
    get_active_base_markets as _get_active_base_markets,
    get_total_users as _get_total_users,
    get_active_users as _get_active_users,
    get_total_volume_usd as _get_total_volume_usd,
    get_total_staked_usdc as _get_total_staked_usdc,
    get_retention_rate as _get_retention_rate,
    get_daily_user_growth as _get_daily_user_growth,
    get_daily_volume_breakdown as _get_daily_volume_breakdown,
    log_activity as _log_activity,
    get_activity_logs as _get_activity_logs,
    log_fee as _log_fee,
    get_system_config as _get_system_config,
    set_system_config as _set_system_config,
)

logger = logging.getLogger(__name__)

load_dotenv()

# ─── Allowed values for enum-like fields ─────────────────────────────────────
VALID_PLATFORMS = frozenset([
    "whatsapp_id", "telegram_id", "google_id", "psn_id", "xbox_id"
])
VALID_EVENT_TYPES = frozenset([
    "DEPOSIT", "STAKE", "WIN", "FEE", "WITHDRAWAL",
    "WITHDRAWAL_REQUEST", "PAYOUT_CONFIRMED", "FEE_COLLECTED"
])


def _validate_uuid(value: str, field_name: str = "id"):
    """Raise ValueError if value is not a valid UUID string."""
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid UUID for field '{field_name}': {value}")


def _validate_positive_amount(amount, field_name: str = "amount"):
    """Raise ValueError if amount is not a positive number."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid amount for field '{field_name}': {amount}")
    if val <= 0:
        raise ValueError(f"Amount '{field_name}' must be positive, got: {val}")
    return val


class DBLayer:
    """Compatibility shim — all methods delegate to repositories/. """

    def __init__(self):
        self.supabase = get_supabase()

    # ─── Profile helpers ──────────────────────────────────────────────────────

    def get_profile_by_platform(self, platform: str, platform_id: str):
        return _get_profile_by_platform(platform, platform_id)

    def get_profile_by_email(self, email: str):
        return _get_profile_by_email(email)

    def get_profile_by_circle_wallet(self, circle_wallet_id: str):
        return _get_profile_by_circle_wallet(circle_wallet_id)

    def get_or_create_profile(self, platform: str, platform_id: str):
        return _get_or_create_profile(platform, platform_id)

    def link_platform_to_profile(self, profile_id: str, platform: str, platform_id: str):
        return _link_platform_to_profile(profile_id, platform, platform_id)

    def link_email_to_profile(self, profile_id: str, email: str):
        return _link_email_to_profile(profile_id, email)

    def get_all_profiles(self):
        return _get_all_profiles()

    def get_profile_by_id(self, profile_id: str):
        return _get_profile_by_id(profile_id)

    def get_profile_by_uuid(self, profile_id: str):
        return _get_profile_by_uuid(profile_id)

    # ─── Friend Circles ────────────────────────────────────────────────────────

    def create_friend_circle(self, user_id: str, name: str, description: str = ""):
        return _create_friend_circle(user_id, name, description)

    def get_user_circles(self, user_id: str):
        return _get_user_circles(user_id)

    def get_circle_by_id(self, circle_id: str):
        return _get_circle_by_id(circle_id)

    def add_member_to_circle(self, circle_id: str, member_id: str):
        return _add_member_to_circle(circle_id, member_id)

    def remove_member_from_circle(self, circle_id: str, member_id: str):
        return _remove_member_from_circle(circle_id, member_id)

    def get_circle_members(self, circle_id: str):
        return _get_circle_members(circle_id)

    def update_circle_visibility(self, circle_id: str, visibility: str):
        return _update_circle_visibility(circle_id, visibility)

    def delete_friend_circle(self, circle_id: str):
        return _delete_friend_circle(circle_id)

    # ─── Bets ─────────────────────────────────────────────────────────────────

    def get_all_bets(self):
        return _get_all_bets()

    def get_bets_by_user(self, user_id: str):
        return _get_bets_by_user(user_id)

    def get_match_reports(self, bet_id: str = None):
        return _get_match_reports(bet_id)

    def get_withdrawals_by_user(self, user_id: str):
        return _get_withdrawals_by_user(user_id)

    def get_activity_logs(self, user_id: str = None, limit: int = 100):
        return _get_activity_logs(user_id, limit)

    # ─── Balance ─────────────────────────────────────────────────────────────

    def update_balance(self, profile_id: str, amount: float):
        return _update_balance(profile_id, amount)

    def award_play_points(self, profile_id: str, amount: float):
        return _award_play_points(profile_id, amount)

    def get_available_balance(self, profile_id: str):
        return _get_available_balance(profile_id)

    def lock_funds(self, profile_id: str, amount: float):
        return _lock_funds(profile_id, amount)

    def unlock_funds(self, profile_id: str, amount: float):
        return _unlock_funds(profile_id, amount)

    def get_play_points(self, profile_id: str):
        return _get_play_points(profile_id)

    # ─── Bets CRUD ───────────────────────────────────────────────────────────

    def create_bet(self, creator_uuid: str, amount, game_type: str,
                   is_on_chain: bool = False, on_chain_pool_id: int = None,
                   challenge_type: str = "private", is_public: bool = False,
                   session_id: str = None):
        return _create_bet(creator_uuid, amount, game_type, is_on_chain,
                           on_chain_pool_id, challenge_type, is_public, session_id)

    def get_open_bets(self, public_only: bool = False):
        return _get_open_bets(public_only)

    def get_public_challenges(self, limit: int = 50):
        return _get_public_challenges(limit)

    def match_bet(self, bet_id: str, opponent_uuid: str):
        return _match_bet(bet_id, opponent_uuid)

    def approve_bet(self, bet_id: str, creator_uuid: str):
        return _approve_bet(bet_id, creator_uuid)

    def resolve_bet(self, bet_id: str, winner_uuid: str):
        return _resolve_bet(bet_id, winner_uuid)

    def cancel_bet(self, bet_id: str):
        return _cancel_bet(bet_id)

    def get_bet(self, bet_id: str):
        return _get_bet(bet_id)

    # ─── Whitelist / counts ──────────────────────────────────────────────────

    def set_whitelisted(self, profile_id: str, status: bool = True):
        return _set_whitelisted(profile_id, status)

    def get_whitelist_count(self):
        return _get_whitelist_count()

    def get_user_count(self):
        return _get_user_count()

    def get_early_adopter_count(self):
        return _get_early_adopter_count()

    # ─── Withdrawals ─────────────────────────────────────────────────────────

    def create_withdrawal(self, profile_id: str, amount):
        return _create_withdrawal(profile_id, amount)

    def confirm_withdrawal(self, withdrawal_id: str):
        return _confirm_withdrawal(withdrawal_id)

    # ─── Match Reports ───────────────────────────────────────────────────────

    def create_report(self, bet_id: str, reporter_id: str, score: str,
                      proof_url: str = None):
        return _create_report(bet_id, reporter_id, score, proof_url)

    def get_reports_for_bet(self, bet_id: str):
        return _get_reports_for_bet(bet_id)

    # ─── Wallet ──────────────────────────────────────────────────────────────

    def link_wallet(self, profile_id: str, wallet_address: str):
        return _link_wallet(profile_id, wallet_address)

    # ─── Virtual Accounts (Flutterwave) ─────────────────────────────────────

    def get_virtual_account(self, profile_id: str):
        return _get_virtual_account(profile_id)

    def save_virtual_account(self, profile_id: str, account_number: str,
                             bank_name: str, account_name: str, flw_ref: str):
        return _save_virtual_account(profile_id, account_number, bank_name,
                                     account_name, flw_ref)

    def get_profile_by_flw_tx_ref_prefix(self, prefix: str):
        return _get_profile_by_flw_tx_ref_prefix(prefix)

    def has_flw_tx_been_processed(self, flw_tx_id: str) -> bool:
        return _has_flw_tx_been_processed(flw_tx_id)

    def mark_flw_tx_processed(self, flw_tx_id: str, profile_id: str,
                               amount_usd: float):
        return _mark_flw_tx_processed(flw_tx_id, profile_id, amount_usd)

    def has_crypto_tx_been_processed(self, tx_hash: str) -> bool:
        return _has_crypto_tx_been_processed(tx_hash)

    def mark_crypto_tx_processed(self, tx_hash: str, profile_id: str,
                                  amount_usd: float):
        return _mark_crypto_tx_processed(tx_hash, profile_id, amount_usd)

    def update_bet_on_chain_tx(self, bet_id: str, tx_hash: str):
        return _update_bet_on_chain_tx(bet_id, tx_hash)

    def set_bet_on_chain_pool_id(self, bet_id: str, pool_id: int):
        return _set_bet_on_chain_pool_id(bet_id, pool_id)

    # ─── Audit / Logs ────────────────────────────────────────────────────────

    def log_activity(self, user_id, event_type: str, amount_usd=0,
                     details: dict = None):
        return _log_activity(user_id, event_type, amount_usd, details)

    def log_fee(self, bet_id: str, amount_usd: float):
        return _log_fee(bet_id, amount_usd)

    # ─── Escrow & Circle Wallet Methods ─────────────────────────────────────

    ALLOWED_PROFILE_FIELDS = frozenset([
        "display_name", "username", "avatar_url", "avatar_config",
        "bio", "location_city", "location_visible", "tos_accepted",
        "notification_prefs", "category_affinity_vector",
    ])

    def update_profile_field(self, profile_id: str, field: str, value):
        return _update_profile_field(profile_id, field, value)

    def create_profile(self, profile_id: str, profile_data: dict):
        return _create_profile(profile_id, profile_data)

    ALLOWED_UPDATE_FIELDS = frozenset([
        "display_name", "username", "avatar_url", "avatar_config",
        "bio", "location_city", "location_visible", "tos_accepted",
        "notification_prefs", "category_affinity_vector",
        "is_content_creator", "creator_badges", "is_verified",
    ])

    def update_profile(self, profile_id: str, update_data: dict):
        return _update_profile(profile_id, update_data)

    # ─── Tag Methods ───────────────────────────────────────────────────────

    def get_all_tags(self):
        return _get_all_tags()

    def get_user_tags(self, user_id: str):
        return _get_user_tags(user_id)

    def add_user_tag(self, user_id: str, tag_id: str, pinned: bool = False):
        return _add_user_tag(user_id, tag_id, pinned)

    def remove_user_tag(self, user_id: str, tag_id: str):
        return _remove_user_tag(user_id, tag_id)

    # ─── Escrow Entries ─────────────────────────────────────────────────────

    def create_escrow_entry(self, entry_data: dict) -> str:
        return _create_escrow_entry(entry_data)

    def get_escrow_entries_by_bet(self, bet_id: str) -> list:
        return _get_escrow_entries_by_bet(bet_id)

    def get_escrow_entries_by_user(self, user_id: str) -> list:
        return _get_escrow_entries_by_user(user_id)

    def update_escrow_entry_status(self, bet_id: str, new_status: str) -> bool:
        return _update_escrow_entry_status(bet_id, new_status)

    def get_locked_escrow_amount_for_bet(self, bet_id: str) -> float:
        return _get_locked_escrow_amount_for_bet(bet_id)

    # ─── Profile Updates ─────────────────────────────────────────────────────

    def increment_public_stats(self, profile_id: str, result: str):
        return _increment_public_stats(profile_id, result)

    def add_creator_badge(self, profile_id: str, badge: str):
        return _add_creator_badge(profile_id, badge)

    def set_content_creator(self, profile_id: str, is_creator: bool = True):
        return _set_content_creator(profile_id, is_creator)

    def set_verified(self, profile_id: str, is_verified: bool = True):
        return _set_verified(profile_id, is_verified)

    # ─── Top 10 / Reputation ─────────────────────────────────────────────────

    def get_top10_qualified(self, limit: int = 10):
        return _get_top10_qualified(limit)

    def is_top10_player(self, profile_id: str) -> bool:
        return _is_top10_player(profile_id)

    def get_player_reputation(self, profile_id: str):
        return _get_player_reputation(profile_id)

    def _is_player_in_receipt(self, receipt: dict, profile_id: str) -> bool:
        # Delegates to the analytics repository implementation
        return _get_player_reputation.__self__._is_player_in_receipt(receipt, profile_id) \
            if hasattr(_get_player_reputation, '__self__') else \
            __import__('repositories.analytics', fromlist=['_is_player_in_receipt'])._is_player_in_receipt(receipt, profile_id)

    # ─── Leaderboard ─────────────────────────────────────────────────────────

    def get_game_leaderboard(self, game_type: str, limit: int = 50) -> list:
        return _get_game_leaderboard(game_type, limit)

    def get_region_leaderboard(self, region: str, limit: int = 50) -> list:
        return _get_region_leaderboard(region, limit)

    def get_tier_leaderboard(self, tier: str, limit: int = 50) -> list:
        return _get_tier_leaderboard(tier, limit)

    def get_leaderboard_by_state(self, state_type: str = "global",
                                  state_value: str = None, limit: int = 50,
                                  min_reputation: int = 0):
        return _get_leaderboard_by_state(state_type, state_value, limit,
                                         min_reputation)

    # ─── Sessions ─────────────────────────────────────────────────────────────

    def create_session(self, host_id: str, guest_id: str = None, title: str = "",
                       description: str = "", game_type: str = "",
                       status: str = "scheduled"):
        return _create_session(host_id, guest_id, title, description,
                               game_type, status)

    def get_session(self, session_id: str):
        return _get_session(session_id)

    def update_session_status(self, session_id: str, status: str):
        return _update_session_status(session_id, status)

    def get_sessions_by_player(self, player_id: str):
        return _get_sessions_by_player(player_id)

    # ─── Challenges ──────────────────────────────────────────────────────────

    def create_challenge(self, issuer_id: str, game_type: str,
                         stake_amount: float, target_id: str = None,
                         message: str = "", theme: str = ""):
        return _create_challenge(issuer_id, game_type, stake_amount,
                                  target_id, message, theme)

    def get_challenge(self, challenge_id: str):
        return _get_challenge(challenge_id)

    def accept_challenge(self, challenge_id: str, bet_id: str = None):
        return _accept_challenge(challenge_id, bet_id)

    def decline_challenge(self, challenge_id: str):
        return _decline_challenge(challenge_id)

    def expire_challenge(self, challenge_id: str):
        return _expire_challenge(challenge_id)

    def get_active_challenges(self, target_id: str = None):
        return _get_active_challenges(target_id)

    def get_player_challenges(self, player_id: str):
        return _get_player_challenges(player_id)

    # ─── Base Markets ────────────────────────────────────────────────────────

    def create_base_market(self, bet_id: str = None, session_id: str = None,
                           market_type: str = "match_winner", question: str = "",
                           outcomes: list = None, liquidity_usdc: float = 0,
                           spread_fee_pct: float = 0.05):
        return _create_base_market(bet_id, session_id, market_type, question,
                                    outcomes, liquidity_usdc, spread_fee_pct)

    def get_base_market(self, market_id: str = None, bet_id: str = None):
        return _get_base_market(market_id, bet_id)

    def update_base_market_status(self, market_id: str, status: str,
                                   market_id_external: str = None):
        return _update_base_market_status(market_id, status, market_id_external)

    def get_active_base_markets(self):
        return _get_active_base_markets()

    # ─── Proof of Play ──────────────────────────────────────────────────────

    def create_proof_of_play(self, bet_id: str, session_id: str = None,
                             tx_hash: str = "", chain: str = "base",
                             block_number: int = None,
                             verification_data: dict = None):
        return _create_proof_of_play(bet_id, session_id, tx_hash, chain,
                                      block_number, verification_data)

    def get_proof_of_play(self, bet_id: str = None, session_id: str = None):
        return _get_proof_of_play(bet_id, session_id)

    # ─── System Config ──────────────────────────────────────────────────────

    def get_system_config(self, key: str) -> Optional[dict]:
        return _get_system_config(key)

    def set_system_config(self, key: str, value: str):
        return _set_system_config(key, value)

    # ─── Admin Analytics ─────────────────────────────────────────────────────

    def get_total_users(self) -> int:
        return _get_total_users()

    def get_active_users(self, days: int = 7) -> int:
        return _get_active_users(days)

    def get_total_volume_usd(self) -> float:
        return _get_total_volume_usd()

    def get_total_staked_usdc(self) -> float:
        return _get_total_staked_usdc()

    def get_retention_rate(self, cohort_days: int = 30) -> float:
        return _get_retention_rate(cohort_days)

    def get_daily_user_growth(self, days: int = 30) -> list:
        return _get_daily_user_growth(days)

    def get_daily_volume_breakdown(self, days: int = 30) -> list:
        return _get_daily_volume_breakdown(days)

    # ─── Blockchain / Transactions ──────────────────────────────────────────

    @staticmethod
    def _run_async(coro):
        """Run an async coroutine safely from sync context."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    def get_transaction_by_hash(self, tx_hash: str) -> Optional[dict]:
        from db_layer_blockchain import get_transaction_by_hash
        return self._run_async(get_transaction_by_hash(tx_hash))

    def record_transaction(self, data: dict):
        from db_layer_blockchain import record_transaction
        return self._run_async(record_transaction(data))

    def record_unattributed_deposit(self, data: dict):
        from db_layer_blockchain import record_unattributed_deposit
        return self._run_async(record_unattributed_deposit(data))

    def get_user_by_wallet(self, wallet_address: str) -> Optional[dict]:
        from db_layer_blockchain import get_user_by_wallet
        return self._run_async(get_user_by_wallet(wallet_address))

    def get_recent_transactions(self, limit: int = 100) -> list:
        from db_layer_blockchain import get_recent_transactions
        return self._run_async(get_recent_transactions(limit))

    def flag_transaction_reorg(self, tx_hash: str):
        from db_layer_blockchain import flag_transaction_reorg
        return self._run_async(flag_transaction_reorg(tx_hash))

    def credit_wallet(self, user_id: str, amount: float, tx_hash: str,
                       source: str = "crypto_deposit"):
        from db_layer_blockchain import credit_wallet
        return self._run_async(credit_wallet(user_id, amount, tx_hash, source))

    def debit_wallet(self, user_id: str, amount: float) -> bool:
        from db_layer_blockchain import debit_wallet
        return self._run_async(debit_wallet(user_id, amount))

    def get_wallet_balance(self, user_id: str) -> float:
        from db_layer_blockchain import get_wallet_balance
        return self._run_async(get_wallet_balance(user_id))

    # ─── Zero-Knowledge Proof (ZKP) Age Verification ───────────────────────

    def create_zkp_challenge(self, profile_id: str,
                               rarimo_user_id: str = None) -> dict:
        _validate_uuid(profile_id, "profile_id")
        import secrets
        import hashlib

        challenge_id = "zkp_" + hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:32]
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        data = {
            "profile_id": profile_id,
            "challenge_id": challenge_id,
            "expires_at": expires_at.isoformat(),
            "used": False
        }
        if rarimo_user_id:
            data["rarimo_user_id"] = rarimo_user_id

        res = self.supabase.table("zkp_challenges").insert(data).execute()
        return res.data[0] if res.data else None

    def get_zkp_challenge_by_rarimo_id(self, rarimo_user_id: str) -> Optional[dict]:
        res = self.supabase.table("zkp_challenges").select("*").eq(
            "rarimo_user_id", rarimo_user_id
        ).single().execute()
        return res.data if res.data else None

    def get_zkp_challenge(self, challenge_id: str) -> Optional[dict]:
        res = self.supabase.table("zkp_challenges").select("*").eq(
            "challenge_id", challenge_id
        ).single().execute()
        return res.data if res.data else None

    def mark_challenge_used(self, challenge_id: str):
        self.supabase.table("zkp_challenges").update(
            {"used": True}
        ).eq("challenge_id", challenge_id).execute()

    def update_challenge_verification_data(self, challenge_id: str,
                                            verification_data: dict):
        self.supabase.table("zkp_challenges").update({
            "verification_data": verification_data,
            "used": True
        }).eq("challenge_id", challenge_id).execute()

    def verify_nullifier_available(self, nullifier_hash: str) -> bool:
        res = self.supabase.table("profiles").select("id").eq(
            "zkp_nullifier_hash", nullifier_hash
        ).execute()
        return len(res.data) == 0

    def set_zkp_verified(self, profile_id: str, nullifier_hash: str,
                          circuit_version: str = "age_verification_v2"):
        _validate_uuid(profile_id, "profile_id")
        if not self.verify_nullifier_available(nullifier_hash):
            raise ValueError(
                "ZKP nullifier already used - proof may be a replay attack"
            )
        update_data = {
            "is_over_18": True,
            "zkp_nullifier_hash": nullifier_hash,
            "zkp_verified_at": datetime.now(timezone.utc).isoformat(),
            "zkp_circuit_version": circuit_version
        }
        res = self.supabase.table("profiles").update(update_data).eq(
            "id", profile_id
        ).execute()
        return res.data[0] if res.data else None

    def is_zkp_verified(self, profile_id: str) -> bool:
        _validate_uuid(profile_id, "profile_id")
        res = self.supabase.table("profiles").select("is_over_18").eq(
            "id", profile_id
        ).single().execute()
        return res.data.get("is_over_18", False) if res.data else False