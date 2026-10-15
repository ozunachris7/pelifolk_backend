-- Preserve the recorded genealogical check; historical matings remain unknown.
ALTER TABLE event_matings ADD COLUMN kinship_snapshot JSON NULL;
