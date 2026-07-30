#!/bin/sh
# Thin wrapper — prefer Python entrypoint (no bash required on slim images).
set -eu
cd /app
exec python /app/deploy/start_akash.py
