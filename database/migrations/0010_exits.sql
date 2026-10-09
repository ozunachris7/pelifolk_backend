-- Exit events and subtypes already exist in the initial schema.
INSERT INTO role_permissions (role_id, permission)
SELECT r.id, p.code FROM roles r
CROSS JOIN (SELECT 'exits:read' AS code UNION ALL SELECT 'exits:write') p
WHERE r.name IN ('owner', 'administrator') AND r.is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;
