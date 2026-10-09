-- Initial English schema, applied to the database selected by DATABASE_URL.
-- Versioned migration: do not edit after it has been applied.
CREATE TABLE IF NOT EXISTS units (
  id     SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(20) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS breeds (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS location_types (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS product_types (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS administration_routes (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS birth_types (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS expense_categories (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS income_categories (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS active_ingredients (
  id SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(120) NOT NULL UNIQUE
);


CREATE TABLE IF NOT EXISTS event_types (
  id     SMALLINT UNSIGNED PRIMARY KEY,
  code VARCHAR(30) NOT NULL UNIQUE,
  name VARCHAR(80) NOT NULL
);
INSERT INTO event_types (id, code, name) VALUES
 (1,'observation','Observation'), (2,'diagnosis','Diagnosis'),
 (3,'treatment','Treatment'), (4,'weight','Weight'),
 (5,'mating','Mating'),             (6,'pregnancy_diagnosis','Pregnancy diagnosis'),
 (7,'birth','Birth'),             (8,'exit','Exit')
ON DUPLICATE KEY UPDATE id = event_types.id;


CREATE TABLE IF NOT EXISTS roles (
  id     CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name VARCHAR(60) NOT NULL UNIQUE,
  is_system BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS users (
  id            CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name        VARCHAR(120) NOT NULL,
  paternal_lastname VARCHAR(120) NOT NULL,
  maternal_lastname VARCHAR(120) DEFAULT NULL,
  email         VARCHAR(190) NOT NULL UNIQUE,          
  phone      VARCHAR(30),
  role_id        CHAR(36) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  token_version INT UNSIGNED NOT NULL DEFAULT 0,
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE TABLE IF NOT EXISTS role_event_permissions (
  role_id         CHAR(36) NOT NULL,
  event_type_id SMALLINT UNSIGNED NOT NULL,
  allowed      BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (role_id, event_type_id),
  FOREIGN KEY (role_id) REFERENCES roles(id),
  FOREIGN KEY (event_type_id) REFERENCES event_types(id)
);


CREATE TABLE IF NOT EXISTS locations (
  id                CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name            VARCHAR(120) NOT NULL UNIQUE,
  location_type_id SMALLINT UNSIGNED NOT NULL,
  description       TEXT,
  active            BOOLEAN NOT NULL DEFAULT TRUE,
  FOREIGN KEY (location_type_id) REFERENCES location_types(id)
);

CREATE TABLE IF NOT EXISTS animal_groups (
  id          CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name      VARCHAR(120) NOT NULL UNIQUE,
  description TEXT,
  active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS animals (
  id               CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  siniiga          VARCHAR(30) UNIQUE,
  name           VARCHAR(100),
  sex             ENUM('male','female') NOT NULL,
  birth_date DATE,
  origin           ENUM('born_in_herd','purchased','donated','other') NOT NULL DEFAULT 'born_in_herd',
  mother_id         CHAR(36),
  father_id         CHAR(36),
  is_breeder      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (mother_id) REFERENCES animals(id),
  FOREIGN KEY (father_id) REFERENCES animals(id),
  CHECK (mother_id IS NULL OR mother_id <> id),
  CHECK (father_id IS NULL OR father_id <> id),
  CHECK (mother_id IS NULL OR father_id IS NULL OR mother_id <> father_id)
);

CREATE TABLE IF NOT EXISTS animal_breeds (
  animal_id  CHAR(36) NOT NULL,
  breed_id    SMALLINT UNSIGNED NOT NULL,
  percentage DECIMAL(5,2) NOT NULL CHECK (percentage > 0 AND percentage <= 100),
  PRIMARY KEY (animal_id, breed_id),
  FOREIGN KEY (animal_id) REFERENCES animals(id) ON DELETE CASCADE,
  FOREIGN KEY (breed_id)   REFERENCES breeds(id)
  
);

CREATE TABLE IF NOT EXISTS group_animals (
  group_id   CHAR(36) NOT NULL,
  animal_id CHAR(36) NOT NULL,
  start_date     DATE NOT NULL,
  end_date     DATE,
  PRIMARY KEY (group_id, animal_id, start_date),
  FOREIGN KEY (group_id)   REFERENCES animal_groups(id),
  FOREIGN KEY (animal_id) REFERENCES animals(id),
  CHECK (end_date IS NULL OR end_date >= start_date)
);


CREATE TABLE IF NOT EXISTS products (
  id                 CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name             VARCHAR(150) NOT NULL UNIQUE,
  product_type_id   SMALLINT UNSIGNED NOT NULL,
  unit_id          SMALLINT UNSIGNED NOT NULL,
  withdrawal_days INT NOT NULL DEFAULT 0 CHECK (withdrawal_days >= 0),
  active             BOOLEAN NOT NULL DEFAULT TRUE,
  FOREIGN KEY (product_type_id) REFERENCES product_types(id),
  FOREIGN KEY (unit_id)        REFERENCES units(id)
);

CREATE TABLE IF NOT EXISTS product_ingredients (
  product_id  CHAR(36) NOT NULL,
  ingredient_id SMALLINT UNSIGNED NOT NULL,
  PRIMARY KEY (product_id, ingredient_id),
  FOREIGN KEY (product_id)  REFERENCES products(id) ON DELETE CASCADE,
  FOREIGN KEY (ingredient_id) REFERENCES active_ingredients(id)
);

CREATE TABLE IF NOT EXISTS product_prices (
  product_id   CHAR(36) NOT NULL,
  effective_from DATE NOT NULL,
  cost         DECIMAL(12,2) NOT NULL CHECK (cost >= 0),
  PRIMARY KEY (product_id, effective_from),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS health_programs (
  id               CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name           VARCHAR(150) NOT NULL UNIQUE,
  product_id      CHAR(36) NOT NULL,
  interval_days   INT NOT NULL CHECK (interval_days > 0),
  minimum_age_days INT NOT NULL DEFAULT 0 CHECK (minimum_age_days >= 0),
  sex             ENUM('male','female') NULL,        
  notice_days       INT NOT NULL DEFAULT 0 CHECK (notice_days >= 0),
  active           BOOLEAN NOT NULL DEFAULT TRUE,
  FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS health_cases (
  id            CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  animal_id     CHAR(36) NOT NULL,
  reason        VARCHAR(255) NOT NULL,
  status        ENUM('open','under_treatment','closed') NOT NULL DEFAULT 'open',
  start_date  DATE NOT NULL,
  closed_date  DATE,
  notes TEXT,
  FOREIGN KEY (animal_id) REFERENCES animals(id),
  CHECK ((status = 'closed' AND closed_date IS NOT NULL)
      OR (status <> 'closed' AND closed_date IS NULL)),
  CHECK (closed_date IS NULL OR closed_date >= start_date)
);


CREATE TABLE IF NOT EXISTS events (
  id                    CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  animal_id             CHAR(36) NOT NULL,
  event_type_id        SMALLINT UNSIGNED NOT NULL,
  date                 DATETIME NOT NULL,
  user_id            CHAR(36) NOT NULL,
  role_id                CHAR(36) NOT NULL,             
  location_id          CHAR(36),
  reason                TEXT,
  replaced_event_id CHAR(36) UNIQUE,
  created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (animal_id)             REFERENCES animals(id),
  FOREIGN KEY (event_type_id)        REFERENCES event_types(id),
  FOREIGN KEY (user_id)            REFERENCES users(id),
  FOREIGN KEY (role_id)                REFERENCES roles(id),
  FOREIGN KEY (location_id)          REFERENCES locations(id),
  FOREIGN KEY (replaced_event_id) REFERENCES events(id),
  CHECK (replaced_event_id IS NULL OR replaced_event_id <> id),
  UNIQUE KEY uq_event_type (id, event_type_id),      
  KEY ix_events_animal_date (animal_id, date),
  KEY ix_events_type_date   (event_type_id, date)
);


CREATE TABLE IF NOT EXISTS event_observations (
  event_id      CHAR(36) PRIMARY KEY,
  event_type_id SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  observation    TEXT NOT NULL,
  CHECK (event_type_id = 1),
  FOREIGN KEY (event_id, event_type_id) REFERENCES events(id, event_type_id)
);

CREATE TABLE IF NOT EXISTS event_diagnoses (
  event_id         CHAR(36) PRIMARY KEY,
  event_type_id    SMALLINT UNSIGNED NOT NULL DEFAULT 2,
  health_case_id CHAR(36) NOT NULL,
  diagnosis       TEXT NOT NULL,
  severity          ENUM('mild','moderate','severe','critical') NOT NULL,
  CHECK (event_type_id = 2),
  FOREIGN KEY (event_id, event_type_id) REFERENCES events(id, event_type_id),
  FOREIGN KEY (health_case_id) REFERENCES health_cases(id)
);

CREATE TABLE IF NOT EXISTS event_treatments (
  event_id         CHAR(36) NOT NULL,
  product_id       CHAR(36) NOT NULL,
  event_type_id    SMALLINT UNSIGNED NOT NULL DEFAULT 3,
  health_case_id CHAR(36),
  program_id       CHAR(36),
  dose_value       DECIMAL(10,3) NOT NULL CHECK (dose_value > 0),
  dose_unit_id   SMALLINT UNSIGNED NOT NULL,
  route_id            SMALLINT UNSIGNED NOT NULL,
  frequency_hours  INT CHECK (frequency_hours > 0),
  duration_days     INT NOT NULL DEFAULT 1 CHECK (duration_days > 0),
  start_date      DATE NOT NULL,
  end_date         DATE GENERATED ALWAYS AS (DATE_ADD(start_date, INTERVAL duration_days DAY)) STORED,
  PRIMARY KEY (event_id, product_id),
  CHECK (event_type_id = 3),
  FOREIGN KEY (event_id, event_type_id) REFERENCES events(id, event_type_id),
  FOREIGN KEY (product_id)       REFERENCES products(id),
  FOREIGN KEY (health_case_id) REFERENCES health_cases(id),
  FOREIGN KEY (program_id)       REFERENCES health_programs(id),
  FOREIGN KEY (dose_unit_id)   REFERENCES units(id),
  FOREIGN KEY (route_id)            REFERENCES administration_routes(id)
);

CREATE TABLE IF NOT EXISTS event_weights (
  event_id      CHAR(36) PRIMARY KEY,
  event_type_id SMALLINT UNSIGNED NOT NULL DEFAULT 4,
  weight_kg        DECIMAL(7,2) NOT NULL CHECK (weight_kg > 0),
  CHECK (event_type_id = 4),
  FOREIGN KEY (event_id, event_type_id) REFERENCES events(id, event_type_id)
);

CREATE TABLE IF NOT EXISTS event_matings (
  event_id      CHAR(36) PRIMARY KEY,
  event_type_id SMALLINT UNSIGNED NOT NULL DEFAULT 5,
  male_id       CHAR(36) NOT NULL,
  CHECK (event_type_id = 5),
  FOREIGN KEY (event_id, event_type_id) REFERENCES events(id, event_type_id),
  FOREIGN KEY (male_id) REFERENCES animals(id)
);

CREATE TABLE IF NOT EXISTS event_pregnancy_diagnoses (
  event_id       CHAR(36) PRIMARY KEY,
  event_type_id  SMALLINT UNSIGNED NOT NULL DEFAULT 6,
  result       ENUM('pregnant','not_pregnant','uncertain') NOT NULL,
  mating_event_id CHAR(36),
  CHECK (event_type_id = 6),
  FOREIGN KEY (event_id, event_type_id) REFERENCES events(id, event_type_id),
  FOREIGN KEY (mating_event_id) REFERENCES event_matings(event_id)
);

CREATE TABLE IF NOT EXISTS event_births (
  event_id      CHAR(36) PRIMARY KEY,
  event_type_id SMALLINT UNSIGNED NOT NULL DEFAULT 7,
  birth_type_id  SMALLINT UNSIGNED NOT NULL,
  notes  TEXT,
  CHECK (event_type_id = 7),
  FOREIGN KEY (event_id, event_type_id) REFERENCES events(id, event_type_id),
  FOREIGN KEY (birth_type_id) REFERENCES birth_types(id)
);

CREATE TABLE IF NOT EXISTS event_birth_offspring (
  animal_id          CHAR(36) PRIMARY KEY,             
  event_id          CHAR(36) NOT NULL,
  alive               BOOLEAN NOT NULL DEFAULT TRUE,
  birth_weight_kg DECIMAL(5,2) CHECK (birth_weight_kg > 0),
  FOREIGN KEY (animal_id) REFERENCES animals(id),
  FOREIGN KEY (event_id) REFERENCES event_births(event_id)
);

CREATE TABLE IF NOT EXISTS exits (
  event_id      CHAR(36) PRIMARY KEY,
  event_type_id SMALLINT UNSIGNED NOT NULL DEFAULT 8,
  exit_type    ENUM('sale','death','slaughter','transfer','theft','other') NOT NULL,
  CHECK (event_type_id = 8),
  FOREIGN KEY (event_id, event_type_id) REFERENCES events(id, event_type_id)
);


CREATE TABLE IF NOT EXISTS suppliers (
  id        CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name    VARCHAR(150) NOT NULL UNIQUE,
  phone  VARCHAR(30),
  email     VARCHAR(190),
  address TEXT,
  active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS expenses (
  id                 CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  supplier_id       CHAR(36),
  expense_category_id SMALLINT UNSIGNED NOT NULL,
  amount              DECIMAL(12,2) NOT NULL CHECK (amount > 0),
  date              DATE NOT NULL,
  description        TEXT,
  FOREIGN KEY (supplier_id)       REFERENCES suppliers(id),
  FOREIGN KEY (expense_category_id) REFERENCES expense_categories(id)
);

CREATE TABLE IF NOT EXISTS expense_allocations (
  id                CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  expense_id          CHAR(36) NOT NULL,
  animal_id         CHAR(36),
  group_id           CHAR(36),
  health_case_id CHAR(36),
  percentage        DECIMAL(5,2) NOT NULL DEFAULT 100 CHECK (percentage > 0 AND percentage <= 100),
  FOREIGN KEY (expense_id)          REFERENCES expenses(id) ON DELETE CASCADE,
  FOREIGN KEY (animal_id)         REFERENCES animals(id),
  FOREIGN KEY (group_id)           REFERENCES animal_groups(id),
  FOREIGN KEY (health_case_id) REFERENCES health_cases(id),
  CHECK ((animal_id IS NOT NULL) + (group_id IS NOT NULL) + (health_case_id IS NOT NULL) = 1)
  
);

CREATE TABLE IF NOT EXISTS incomes (
  id                   CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  income_category_id SMALLINT UNSIGNED NOT NULL,
  amount                DECIMAL(12,2) NOT NULL CHECK (amount >= 0),
  date                DATE NOT NULL,
  exit_event_id     CHAR(36) UNIQUE,
  description          TEXT,
  FOREIGN KEY (income_category_id) REFERENCES income_categories(id),
  FOREIGN KEY (exit_event_id)     REFERENCES exits(event_id)
);


CREATE TABLE IF NOT EXISTS feeds (
  id        CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name    VARCHAR(150) NOT NULL UNIQUE,
  unit_id SMALLINT UNSIGNED NOT NULL,
  FOREIGN KEY (unit_id) REFERENCES units(id)
);

CREATE TABLE IF NOT EXISTS feed_prices (
  feed_id    CHAR(36) NOT NULL,
  effective_from  DATE NOT NULL,
  unit_cost DECIMAL(12,4) NOT NULL CHECK (unit_cost >= 0),
  PRIMARY KEY (feed_id, effective_from),
  FOREIGN KEY (feed_id) REFERENCES feeds(id)
);

CREATE TABLE IF NOT EXISTS feedings (
  id          CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  animal_id   CHAR(36),
  group_id     CHAR(36),
  date       DATE NOT NULL,
  feed_id CHAR(36) NOT NULL,
  quantity    DECIMAL(10,2) NOT NULL CHECK (quantity > 0),
  FOREIGN KEY (animal_id)   REFERENCES animals(id),
  FOREIGN KEY (group_id)     REFERENCES animal_groups(id),
  FOREIGN KEY (feed_id) REFERENCES feeds(id),
  CHECK ((animal_id IS NOT NULL) + (group_id IS NOT NULL) = 1),
  KEY ix_feeding_animal_date (animal_id, date),
  KEY ix_feeding_group_date   (group_id, date)
);


CREATE TABLE IF NOT EXISTS audit_logs (
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




DELIMITER $$


CREATE FUNCTION fn_case_same_animal(p_case CHAR(36), p_event CHAR(36))
RETURNS BOOLEAN READS SQL DATA
BEGIN
  DECLARE case_animal CHAR(36);
  DECLARE event_animal CHAR(36);
  IF p_case IS NULL THEN RETURN TRUE; END IF;
  SELECT animal_id INTO case_animal   FROM health_cases WHERE id = p_case;
  SELECT animal_id INTO event_animal FROM events          WHERE id = p_event;
  RETURN case_animal = event_animal;
END$$

CREATE TRIGGER trg_diagnosis_case_insert BEFORE INSERT ON event_diagnoses
FOR EACH ROW
BEGIN
  IF NOT fn_case_same_animal(NEW.health_case_id, NEW.event_id) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Case and event belong to different animals';
  END IF;
END$$

CREATE TRIGGER trg_diagnosis_case_update BEFORE UPDATE ON event_diagnoses
FOR EACH ROW
BEGIN
  IF NOT fn_case_same_animal(NEW.health_case_id, NEW.event_id) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Case and event belong to different animals';
  END IF;
END$$

CREATE TRIGGER trg_treatment_case_insert BEFORE INSERT ON event_treatments
FOR EACH ROW
BEGIN
  IF NOT fn_case_same_animal(NEW.health_case_id, NEW.event_id) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Case and event belong to different animals';
  END IF;
END$$

CREATE TRIGGER trg_treatment_case_update BEFORE UPDATE ON event_treatments
FOR EACH ROW
BEGIN
  IF NOT fn_case_same_animal(NEW.health_case_id, NEW.event_id) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Case and event belong to different animals';
  END IF;
END$$


CREATE TRIGGER trg_group_overlap_insert BEFORE INSERT ON group_animals
FOR EACH ROW
BEGIN
  IF EXISTS (SELECT 1 FROM group_animals la
             WHERE la.animal_id = NEW.animal_id
               AND la.start_date <= COALESCE(NEW.end_date, '9999-12-31')
               AND COALESCE(la.end_date, '9999-12-31') >= NEW.start_date) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Animal already belongs to a group in this period';
  END IF;
END$$

CREATE TRIGGER trg_group_overlap_update BEFORE UPDATE ON group_animals
FOR EACH ROW
BEGIN
  IF EXISTS (SELECT 1 FROM group_animals la
             WHERE la.animal_id = NEW.animal_id
               AND NOT (la.group_id = OLD.group_id AND la.animal_id = OLD.animal_id AND la.start_date = OLD.start_date)
               AND la.start_date <= COALESCE(NEW.end_date, '9999-12-31')
               AND COALESCE(la.end_date, '9999-12-31') >= NEW.start_date) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Animal already belongs to a group in this period';
  END IF;
END$$

DELIMITER ;


CREATE OR REPLACE VIEW v_current_animal AS
SELECT a.*,
       COALESCE(bj.exit_type, 'active') AS status,
       u.location_id
FROM animals a
LEFT JOIN LATERAL (
  SELECT s.exit_type FROM exits s JOIN events e ON e.id = s.event_id
  WHERE e.animal_id = a.id
  ORDER BY e.date DESC, e.created_at DESC, e.id DESC LIMIT 1
) bj ON TRUE
LEFT JOIN LATERAL (
  SELECT e.location_id FROM events e
  WHERE e.animal_id = a.id AND e.location_id IS NOT NULL
  ORDER BY e.date DESC, e.created_at DESC, e.id DESC LIMIT 1
) u ON TRUE;

CREATE OR REPLACE VIEW v_breed_composition AS
SELECT animal_id,
       CASE WHEN MAX(percentage) = 100 THEN 'pure' ELSE 'crossbred' END AS breed_classification
FROM animal_breeds GROUP BY animal_id;

CREATE OR REPLACE VIEW v_feeding_cost AS
SELECT al.*, al.quantity * p.unit_cost AS cost
FROM feedings al
LEFT JOIN LATERAL (
  SELECT ap.unit_cost FROM feed_prices ap
  WHERE ap.feed_id = al.feed_id AND ap.effective_from <= al.date
  ORDER BY ap.effective_from DESC LIMIT 1
) p ON TRUE;

-- Action-based permissions for the implemented users and roles features.
CREATE TABLE IF NOT EXISTS role_permissions (
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
 ('00000000-0000-4000-8000-000000000006', 'livestock_technician', TRUE)
ON DUPLICATE KEY UPDATE id = roles.id;

INSERT INTO role_permissions (role_id, permission)
SELECT roles.id, permissions.code FROM roles
CROSS JOIN (
 SELECT 'users:read' AS code UNION ALL SELECT 'users:write'
 UNION ALL SELECT 'roles:read' UNION ALL SELECT 'roles:write'
) permissions WHERE roles.name IN ('owner', 'administrator')
ON DUPLICATE KEY UPDATE role_id = role_permissions.role_id;
