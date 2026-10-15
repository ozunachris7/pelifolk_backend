CREATE TABLE IF NOT EXISTS health_case_followups (
  id CHAR(36) PRIMARY KEY,
  health_case_id CHAR(36) NOT NULL,
  user_id CHAR(36) NOT NULL,
  role_id CHAR(36) NOT NULL,
  date DATE NOT NULL,
  evolution VARCHAR(20) NOT NULL,
  treatment_result VARCHAR(25) NOT NULL,
  notes TEXT NOT NULL,
  next_review_date DATE,
  created_at DATETIME(6) NOT NULL,
  FOREIGN KEY (health_case_id) REFERENCES health_cases(id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (role_id) REFERENCES roles(id),
  CHECK (next_review_date IS NULL OR next_review_date >= date),
  CHECK (evolution IN ('improved','unchanged','worsened','recovered')),
  CHECK (treatment_result IN ('not_assessed','effective','partially_effective','not_effective')),
  KEY ix_followups_case_date (health_case_id, date, created_at, id)
);
