CREATE TABLE IF NOT EXISTS animal_decisions (
  id CHAR(36) PRIMARY KEY,
  animal_id CHAR(36) NOT NULL,
  user_id CHAR(36) NOT NULL,
  role_id CHAR(36) NOT NULL,
  kind VARCHAR(30) NOT NULL,
  reason TEXT NOT NULL,
  date DATE NOT NULL,
  created_at DATETIME(6) NOT NULL,
  FOREIGN KEY (animal_id) REFERENCES animals(id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (role_id) REFERENCES roles(id),
  CHECK (kind IN ('retain_breeding','exclude_breeding','separate','sale_planned','purchase_reason','other')),
  KEY ix_decisions_animal_date (animal_id, date, created_at, id)
);
