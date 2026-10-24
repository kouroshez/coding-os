-- migrations/NNN_<short_description>.sql
-- ---------------------------------------------------------------------
-- Migration template — copy this when authoring a new schema change.
--
-- Phase: <expand | migrate | contract>
-- Backward compatible with previous release: <yes | no, blocker: ...>
-- Lock duration estimate: <e.g., <100ms ACCESS EXCLUSIVE>
-- Rewrites table: <yes | no>
-- Backfill: <none | inline | background-job NAME>
-- Rollback path: <new migration NNN+k that reverses>
-- ---------------------------------------------------------------------

-- Fail fast if we cannot acquire locks promptly.
SET LOCK_TIMEOUT = '5s';
SET STATEMENT_TIMEOUT = '60s';

BEGIN;

-- ============================================================
-- 1. SCHEMA CHANGES (DDL) — keep each statement short
-- ============================================================

-- Example: add a new column (instant on PG 11+ with constant default).
ALTER TABLE orders
    ADD COLUMN coupon_code TEXT;

-- Example: add NOT VALID constraint (no full-table scan now).
-- ALTER TABLE orders
--     ADD CONSTRAINT orders_coupon_format
--     CHECK (coupon_code ~ '^[A-Z0-9]{4,16}$') NOT VALID;

-- ============================================================
-- 2. NEW INDEXES (must be CONCURRENTLY, NOT inside transaction)
-- ============================================================
-- IMPORTANT: CREATE INDEX CONCURRENTLY cannot run inside BEGIN.
-- Some migration runners (sqitch, dbmate) support marking a migration as
-- "no-transaction" — use that flag and put concurrent ops in a separate
-- migration file.

-- See: migrations/NNN+1_create_idx_orders_coupon_code.sql

COMMIT;

-- ============================================================
-- 3. POST-DEPLOY (separate migration file, after app rolls out)
-- ============================================================
--   - Validate constraints: ALTER TABLE ... VALIDATE CONSTRAINT ...
--   - Drop old columns (only after a full deploy soak)
--   - Backfill (separate background job, not inline DDL)
