-- Health observations and cases reuse existing tables.
INSERT INTO role_permissions (role_id, permission)
SELECT r.id, p.code FROM roles r
CROSS JOIN (SELECT 'health:read' AS code UNION ALL SELECT 'health:write') p
WHERE r.name IN ('owner', 'administrator') AND r.is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;
