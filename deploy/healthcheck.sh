#!/usr/bin/env bash
# ClawStation host-level health check.
#
# Run this from the VPS (e.g. via cron or a monitoring agent) to verify that
# the local API is responding and that Supabase is reachable. Exits non-zero
# on any failure so the caller can raise an alert.

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000/api/healthz}"

# 1. HTTP liveness check.
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}" || true)
if [ "${HTTP_STATUS}" != "200" ]; then
    echo "ERROR: API health endpoint returned HTTP ${HTTP_STATUS}"
    exit 1
fi
echo "OK: API health endpoint returned HTTP 200"

# 2. Supabase connectivity check via a Python one-liner using the project venv.
python3 - <<'PY'
import os, sys
from backend.supabase_client import get_supabase

try:
    sb = get_supabase()
    sb.table("profiles").select("id", count="exact").limit(1).execute()
    print("OK: Supabase query succeeded")
except Exception as exc:
    print(f"ERROR: Supabase query failed: {exc}", file=sys.stderr)
    sys.exit(1)
PY

echo "OK: All ClawStation health checks passed"
