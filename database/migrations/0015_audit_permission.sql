-- Audit is read-only and exposes records across modules.
INSERT INTO role_permissions (role_id, permission)
SELECT id, 'audit:read' FROM roles
WHERE name IN ('owner', 'administrator') AND is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;
