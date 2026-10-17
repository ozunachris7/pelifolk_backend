-- Keep 0029 immutable: precision is an independent, data-preserving schema change.
ALTER TABLE history_rectifications
 MODIFY COLUMN created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6);
