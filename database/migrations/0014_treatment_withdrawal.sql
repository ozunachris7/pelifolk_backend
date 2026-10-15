-- Preserve the labeled period when a treatment is recorded.
-- Historical values are unknown; do not backfill from the current catalog.
ALTER TABLE event_treatments ADD COLUMN withdrawal_days INT NULL;
