"""
supabase_client.py — Shared Supabase client singleton.
Import this instead of calling create_client() directly.
"""
import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_supabase():
    """Return a shared Supabase client (service role). Creates once, reuses forever."""
    from supabase import create_client
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    logger.info("[Supabase] Creating shared client")
    return create_client(url, key)


@lru_cache(maxsize=1)
def get_supabase_anon():
    """Return a shared Supabase anon client (for user-facing queries)."""
    from supabase import create_client
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        logger.error("SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set")
        raise RuntimeError("SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set")
    return create_client(url, key)
