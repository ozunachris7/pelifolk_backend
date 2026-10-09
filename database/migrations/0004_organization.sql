-- Permissions for locations and animal groups; existing tables and history are reused.
INSERT INTO role_permissions (role_id, permission)
SELECT r.id, p.code FROM roles r
CROSS JOIN (
  SELECT 'locations:read' AS code UNION ALL SELECT 'locations:write'
  UNION ALL SELECT 'groups:read' UNION ALL SELECT 'groups:write'
) p WHERE r.name IN ('owner', 'administrator') AND r.is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;

INSERT INTO location_types (name) VALUES ('corral'), ('pasture'), ('barn'), ('other')
ON DUPLICATE KEY UPDATE name = location_types.name;
