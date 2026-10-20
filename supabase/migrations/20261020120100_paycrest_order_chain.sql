-- Boardman money realms: tag every Paycrest order with its settlement chain.
-- Generated from src/backend/services/paycrest/store.py (UPGRADES).

BEGIN;

ALTER TABLE paycrest_orders ADD COLUMN IF NOT EXISTS chain TEXT;

COMMIT;
