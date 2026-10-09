-- Use the finance tables already present in the initial schema.
INSERT INTO role_permissions (role_id, permission)
SELECT r.id, p.code FROM roles r
CROSS JOIN (SELECT 'finance:read' AS code UNION ALL SELECT 'finance:write') p
WHERE r.name IN ('owner', 'administrator') AND r.is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;

INSERT INTO expense_categories (name) VALUES
('feed'), ('veterinary'), ('maintenance'), ('transport'), ('other')
ON DUPLICATE KEY UPDATE name = expense_categories.name;

INSERT INTO income_categories (name) VALUES ('animal_sales'), ('other')
ON DUPLICATE KEY UPDATE name = income_categories.name;
