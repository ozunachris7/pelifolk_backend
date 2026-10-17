-- Existing total-price incomes remain unchanged. Values used for kilogram pricing are retained.
ALTER TABLE incomes
  ADD COLUMN weight_event_id CHAR(36) NULL,
  ADD COLUMN sale_weight_kg DECIMAL(7,2) NULL,
  ADD COLUMN price_per_kg DECIMAL(12,2) NULL,
  ADD CONSTRAINT fk_income_weight FOREIGN KEY (weight_event_id) REFERENCES event_weights(event_id),
  ADD CONSTRAINT ck_income_weight_pricing CHECK (
    (weight_event_id IS NULL AND sale_weight_kg IS NULL AND price_per_kg IS NULL)
    OR (weight_event_id IS NOT NULL AND exit_event_id IS NOT NULL AND sale_weight_kg IS NOT NULL AND price_per_kg IS NOT NULL AND sale_weight_kg > 0 AND price_per_kg > 0)
  );
