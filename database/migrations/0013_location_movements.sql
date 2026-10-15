-- Physical movements use existing events.location_id and existing location permissions.
INSERT INTO event_types (id, code, name) VALUES (9, 'location_movement', 'Location movement')
ON DUPLICATE KEY UPDATE code = VALUES(code), name = VALUES(name);
