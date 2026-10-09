-- Initial catalogs; preserve existing entries and identifiers.
INSERT INTO units (code) VALUES ('ml'), ('mg'), ('g'), ('tablet'), ('dose')
ON DUPLICATE KEY UPDATE code = units.code;
INSERT INTO product_types (name) VALUES ('medicine'), ('vaccine'), ('antiparasitic'), ('supplement'), ('other')
ON DUPLICATE KEY UPDATE name = product_types.name;
INSERT INTO administration_routes (name) VALUES ('oral'), ('intramuscular'), ('subcutaneous'), ('topical'), ('intravenous'), ('other')
ON DUPLICATE KEY UPDATE name = administration_routes.name;
