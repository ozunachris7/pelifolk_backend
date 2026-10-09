-- Reproductive management uses the existing event tables.
INSERT INTO role_permissions (role_id,permission)
SELECT r.id,p.code FROM roles r
CROSS JOIN (SELECT 'breeding:read' AS code UNION ALL SELECT 'breeding:write') p
WHERE r.name IN ('owner','administrator') AND r.is_system=TRUE
ON DUPLICATE KEY UPDATE role_id=role_permissions.role_id;
INSERT INTO birth_types (name) VALUES ('natural'),('assisted'),('cesarean'),('other')
ON DUPLICATE KEY UPDATE name=birth_types.name;
