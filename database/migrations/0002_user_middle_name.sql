-- Keep the first name and optional middle name in separate columns.
-- Existing names are preserved; do not guess how to split personal names.
DELIMITER $$
CREATE PROCEDURE migrate_user_middle_name()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
      AND COLUMN_NAME = 'middle_name'
  ) THEN
    ALTER TABLE users ADD COLUMN middle_name VARCHAR(120) NULL AFTER name;
  END IF;
END$$
DELIMITER ;
CALL migrate_user_middle_name();
DROP PROCEDURE IF EXISTS migrate_user_middle_name;
