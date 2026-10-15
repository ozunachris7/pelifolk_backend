CREATE TABLE IF NOT EXISTS event_weanings (
  event_id CHAR(36) PRIMARY KEY,
  animal_id CHAR(36) NOT NULL UNIQUE,
  mother_id CHAR(36),
  birth_date_snapshot DATE,
  notes TEXT,
  user_id CHAR(36) NOT NULL,
  role_id CHAR(36) NOT NULL,
  FOREIGN KEY (event_id) REFERENCES event_weights(event_id),
  FOREIGN KEY (animal_id) REFERENCES animals(id),
  FOREIGN KEY (mother_id) REFERENCES animals(id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (role_id) REFERENCES roles(id)
);
