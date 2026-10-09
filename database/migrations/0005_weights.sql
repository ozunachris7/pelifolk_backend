-- Access to the existing weight event tables.
INSERT INTO role_permissions (role_id, permission)
SELECT r.id, p.code FROM roles r
CROSS JOIN (SELECT 'weights:read' AS code UNION ALL SELECT 'weights:write') p
WHERE r.name IN ('owner', 'administrator') AND r.is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;
