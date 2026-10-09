-- Existing animal tables are reused. Grant the new feature to the initial administrators.
INSERT INTO role_permissions (role_id, permission)
SELECT r.id, p.code FROM roles r
CROSS JOIN (
  SELECT 'animals:read' AS code UNION ALL SELECT 'animals:write'
) p WHERE r.name IN ('owner', 'administrator') AND r.is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;
