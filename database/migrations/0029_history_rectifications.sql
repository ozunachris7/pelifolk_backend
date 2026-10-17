CREATE TABLE history_rectifications (
 id CHAR(36) PRIMARY KEY,
 animal_id CHAR(36) NOT NULL,
 entry_key VARCHAR(200) NOT NULL,
 source_ref CHAR(36) NOT NULL,
 module VARCHAR(20) NOT NULL,
 version INT NOT NULL CHECK (version > 0),
 mode VARCHAR(30) NOT NULL,
 reason TEXT NOT NULL,
 clarification TEXT,
 source_snapshot JSON NOT NULL,
 corrected_snapshot JSON,
 replacement_event_id CHAR(36) UNIQUE,
 user_id CHAR(36) NOT NULL,
 role_id CHAR(36) NOT NULL,
 recorded_by VARCHAR(500) NOT NULL,
 role_name VARCHAR(60) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_history_rectification_version (animal_id, entry_key, version),
 KEY ix_history_rectification_source (animal_id, source_ref),
 FOREIGN KEY (animal_id) REFERENCES animals(id),
 FOREIGN KEY (replacement_event_id) REFERENCES events(id),
 FOREIGN KEY (user_id) REFERENCES users(id),
 FOREIGN KEY (role_id) REFERENCES roles(id)
);

-- Rectification is deliberately separate from normal capture permissions.
INSERT INTO role_permissions (role_id, permission)
SELECT id, 'history:rectify' FROM roles WHERE name = 'owner' AND is_system = TRUE
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;
