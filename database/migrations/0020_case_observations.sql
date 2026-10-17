CREATE TABLE IF NOT EXISTS health_case_observations (
  observation_event_id CHAR(36) PRIMARY KEY,
  health_case_id CHAR(36) NOT NULL,
  user_id CHAR(36) NOT NULL,
  role_id CHAR(36) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (observation_event_id) REFERENCES event_observations(event_id),
  FOREIGN KEY (health_case_id) REFERENCES health_cases(id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (role_id) REFERENCES roles(id)
);
