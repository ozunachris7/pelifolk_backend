CREATE TABLE IF NOT EXISTS physical_evaluations (
  id CHAR(36) PRIMARY KEY,
  animal_id CHAR(36) NOT NULL,
  date DATE NOT NULL,
  evaluated_by VARCHAR(190) NOT NULL,
  rubric_version VARCHAR(40) NOT NULL,
  findings JSON NOT NULL,
  notes TEXT,
  user_id CHAR(36) NOT NULL,
  role_id CHAR(36) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (animal_id) REFERENCES animals(id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (role_id) REFERENCES roles(id),
  KEY ix_physical_animal_date (animal_id, date),
  KEY ix_physical_date (date)
);
