-- Preserve explicitly assigned health access as individual actions, including custom roles.
-- Existing migration files remain unchanged. Re-running after a partial application is safe.
INSERT INTO role_permissions (role_id, permission)
SELECT legacy.role_id, actions.code FROM role_permissions legacy
CROSS JOIN (
SELECT 'health:read' AS code
UNION ALL
SELECT 'health:observations:create'
UNION ALL
SELECT 'health:cases:write'
UNION ALL
SELECT 'health:diagnoses:create'
UNION ALL
SELECT 'health:treatments:create'
UNION ALL
SELECT 'health:doses:create'
UNION ALL
SELECT 'health:followups:create'
UNION ALL
SELECT 'health:products:write'
UNION ALL
SELECT 'health:programs:write'
UNION ALL
SELECT 'health:program_applications:create'
UNION ALL
SELECT 'health:reactions:write'
UNION ALL
SELECT 'health:incidents:write'
) actions
WHERE legacy.permission = 'health:write'
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;

DELETE FROM role_permissions WHERE permission = 'health:write';
