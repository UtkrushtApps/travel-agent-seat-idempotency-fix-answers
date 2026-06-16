"""Datastore access layer for the seat-selection agent.

Provides a thin connection helper plus read/write functions used by the tools.
Connection details are intentionally local-only and not exposed to candidates
via the README.
"""
import psycopg2
import psycopg2.extras

_DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 55432,
    "dbname": "seatdb",
    "user": "agent",
    "password": "agentpw",
}


def get_connection():
    conn = psycopg2.connect(**_DB_CONFIG)
    conn.autocommit = True
    return conn


def fetch_booking(conn, booking_ref):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT booking_ref, passenger_id, passenger_name, flight_number, status "
            "FROM bookings WHERE booking_ref = %s",
            (booking_ref,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def seat_is_available(conn, flight_number, seat):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT is_available FROM seat_inventory "
            "WHERE flight_number = %s AND seat = %s",
            (flight_number, seat),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return bool(row[0])


def find_existing_assignment(conn, booking_ref, flight_number, seat):
    """Return an existing assignment row for this exact logical request, if any.

    This lookup is the key idempotency check for replayed writes.  The logical
    request is the stable tuple produced by the planner for a passenger's seat
    selection: booking reference + flight + selected seat.  If the same tuple is
    seen again, the write was already completed and callers should return a
    structured already-done outcome instead of inserting a duplicate row.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, booking_ref, flight_number, seat, passenger_id "
            "FROM seat_assignments "
            "WHERE booking_ref = %s AND flight_number = %s AND seat = %s "
            "ORDER BY id ASC LIMIT 1",
            (booking_ref, flight_number, seat),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def insert_seat_assignment(conn, booking_ref, flight_number, seat, passenger_id):
    """Insert a new assignment and mark the inventory row unavailable.

    Idempotency is enforced by the tool before this function is called.  The
    database schema also includes a unique constraint on the logical request in
    fresh databases, and callers may catch uniqueness errors as a final guard
    for concurrent/replayed attempts.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "INSERT INTO seat_assignments (booking_ref, flight_number, seat, passenger_id) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (booking_ref, flight_number, seat, passenger_id),
        )
        new_id = cur.fetchone()["id"]
        cur.execute(
            "UPDATE seat_inventory SET is_available = FALSE "
            "WHERE flight_number = %s AND seat = %s",
            (flight_number, seat),
        )
        return new_id


def count_assignments(conn, booking_ref, flight_number, seat):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM seat_assignments "
            "WHERE booking_ref = %s AND flight_number = %s AND seat = %s",
            (booking_ref, flight_number, seat),
        )
        return int(cur.fetchone()[0])
