-- Auth-only fresh installation; alternative to schema.sql, not an additional step.
CREATE DATABASE IF NOT EXISTS pelifolk DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE pelifolk;

CREATE TABLE roles (
  id     CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name VARCHAR(60) NOT NULL UNIQUE,
  is_system BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE users (
  id            CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name        VARCHAR(120) NOT NULL,
  middle_name VARCHAR(120) DEFAULT NULL,
  paternal_lastname VARCHAR(120) NOT NULL,
  maternal_lastname VARCHAR(120) NOT NULL,
  email         VARCHAR(190) NOT NULL UNIQUE,          
  phone      VARCHAR(30),
  role_id        CHAR(36) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  token_version INT UNSIGNED NOT NULL DEFAULT 0,
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE TABLE audit_logs (
  id                 CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  user_id         CHAR(36),
  table_name              VARCHAR(64) NOT NULL,
  record_id        CHAR(36) NOT NULL,
  action             ENUM('INSERT','UPDATE','DELETE') NOT NULL,
  old_values JSON,
  new_values     JSON,
  date              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  KEY ix_audit_record (table_name, record_id),
  KEY ix_audit_date (date)
);

-- Action-based permissions for the implemented users and roles features.
CREATE TABLE role_permissions (
  role_id CHAR(36) NOT NULL,
  permission VARCHAR(80) NOT NULL,
  PRIMARY KEY (role_id, permission),
  FOREIGN KEY (role_id) REFERENCES roles(id)
);

INSERT INTO roles (id, name, is_system) VALUES
 ('00000000-0000-4000-8000-000000000001', 'owner', TRUE),
 ('00000000-0000-4000-8000-000000000002', 'administrator', TRUE),
 ('00000000-0000-4000-8000-000000000003', 'manager', TRUE),
 ('00000000-0000-4000-8000-000000000004', 'worker', TRUE),
 ('00000000-0000-4000-8000-000000000005', 'veterinarian', TRUE),
 ('00000000-0000-4000-8000-000000000006', 'livestock_technician', TRUE);

INSERT INTO role_permissions (role_id, permission)
SELECT roles.id, permissions.code FROM roles
CROSS JOIN (
 SELECT 'users:read' AS code UNION ALL SELECT 'users:write'
 UNION ALL SELECT 'roles:read' UNION ALL SELECT 'roles:write'
) permissions WHERE roles.name IN ('owner', 'administrator');
