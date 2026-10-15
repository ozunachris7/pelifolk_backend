-- Feeding reuses feeds, feed_prices and feedings from the initial schema.
INSERT INTO role_permissions (role_id, permission)
SELECT r.id, p.code FROM roles r
CROSS JOIN (SELECT 'feeding:read' AS code UNION ALL SELECT 'feeding:write') p
WHERE r.name IN ('owner', 'administrator') AND r.is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;

INSERT INTO units (code) VALUES ('kg'), ('lb'), ('bale'), ('bag')
ON DUPLICATE KEY UPDATE code = units.code;
