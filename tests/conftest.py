import pytest

from agent import db


@pytest.fixture()
def conn():
    connection = db.get_connection()
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def clean_dynamic_state(conn):
    """Reset seat assignments and inventory to the seeded baseline before each
    test so tests are independent and repeatable."""
    with conn.cursor() as cur:
        # Remove everything except the pre-seeded BK1002/AI305/7D assignment.
        cur.execute(
            "DELETE FROM seat_assignments "
            "WHERE NOT (booking_ref = 'BK1002' AND flight_number = 'AI305' "
            "AND seat = '7D')"
        )
        # Restore inventory baseline.
        cur.execute("UPDATE seat_inventory SET is_available = TRUE")
        cur.execute(
            "UPDATE seat_inventory SET is_available = FALSE "
            "WHERE flight_number = 'AI202' AND seat = '14C'"
        )
        cur.execute(
            "UPDATE seat_inventory SET is_available = FALSE "
            "WHERE flight_number = 'AI305' AND seat = '7D'"
        )
    yield
