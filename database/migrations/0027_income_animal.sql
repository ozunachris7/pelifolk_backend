-- Sale incomes retain their existing animal link through the exit event.
ALTER TABLE incomes
  ADD COLUMN animal_id CHAR(36) NULL,
  ADD CONSTRAINT fk_income_animal FOREIGN KEY (animal_id) REFERENCES animals(id),
  ADD CONSTRAINT ck_income_single_animal_source CHECK (exit_event_id IS NULL OR animal_id IS NULL);
