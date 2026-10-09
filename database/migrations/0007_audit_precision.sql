-- Keep the order of successive audit entries recorded within the same second.
ALTER TABLE audit_logs MODIFY COLUMN date TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6);
