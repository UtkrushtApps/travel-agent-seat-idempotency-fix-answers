CREATE TABLE flights (
    flight_number TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    travel_date DATE NOT NULL
);

CREATE TABLE bookings (
    booking_ref TEXT PRIMARY KEY,
    passenger_id TEXT NOT NULL,
    passenger_name TEXT NOT NULL,
    flight_number TEXT NOT NULL REFERENCES flights(flight_number),
    status TEXT NOT NULL
);

CREATE TABLE seat_assignments (
    id SERIAL PRIMARY KEY,
    booking_ref TEXT NOT NULL REFERENCES bookings(booking_ref),
    flight_number TEXT NOT NULL REFERENCES flights(flight_number),
    seat TEXT NOT NULL,
    passenger_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT seat_assignments_logical_request_uniq
        UNIQUE (booking_ref, flight_number, seat)
);

CREATE TABLE seat_inventory (
    flight_number TEXT NOT NULL REFERENCES flights(flight_number),
    seat TEXT NOT NULL,
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (flight_number, seat)
);

INSERT INTO flights (flight_number, origin, destination, travel_date) VALUES
    ('AI202', 'BLR', 'DEL', '2024-08-01'),
    ('AI305', 'DEL', 'BOM', '2024-08-02'),
    ('AI410', 'BOM', 'GOI', '2024-08-03');

INSERT INTO bookings (booking_ref, passenger_id, passenger_name, flight_number, status) VALUES
    ('BK1001', 'PX-501', 'Asha Rao', 'AI202', 'CONFIRMED'),
    ('BK1002', 'PX-502', 'Vivek Nair', 'AI305', 'CONFIRMED'),
    ('BK1003', 'PX-503', 'Meera Iyer', 'AI410', 'CONFIRMED'),
    ('BK1004', 'PX-504', 'Karan Shah', 'AI202', 'CANCELLED');

INSERT INTO seat_inventory (flight_number, seat, is_available) VALUES
    ('AI202', '12A', TRUE),
    ('AI202', '12B', TRUE),
    ('AI202', '14C', FALSE),
    ('AI305', '7D', TRUE),
    ('AI305', '7E', TRUE),
    ('AI410', '3A', TRUE),
    ('AI410', '3B', TRUE);

-- Pre-existing assignment so candidates can see real state.
INSERT INTO seat_assignments (booking_ref, flight_number, seat, passenger_id) VALUES
    ('BK1002', 'AI305', '7D', 'PX-502');
UPDATE seat_inventory SET is_available = FALSE WHERE flight_number = 'AI305' AND seat = '7D';
