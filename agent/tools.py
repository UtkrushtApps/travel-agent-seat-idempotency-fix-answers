"""Tool contracts for the seat-selection agent.

There are two tools the planner can call:
  - get_booking: read-only retrieval tool
  - book_seat_selection: write / side-effect tool that persists a seat assignment

Each tool returns a structured dict with an explicit `ok` flag. Read tools
return data; the write tool performs a side effect and reports the outcome.

Machine-readable error/outcome codes are defined in ToolCode.
"""
import psycopg2

from agent import db


class ToolCode:
    OK = "OK"
    ALREADY_ASSIGNED = "ALREADY_ASSIGNED"
    BOOKING_NOT_FOUND = "BOOKING_NOT_FOUND"
    BOOKING_NOT_CONFIRMED = "BOOKING_NOT_CONFIRMED"
    SEAT_UNKNOWN = "SEAT_UNKNOWN"
    SEAT_TAKEN = "SEAT_TAKEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"


def get_booking(conn, booking_ref):
    """Read-only tool: look up a booking by reference."""
    if not booking_ref or not isinstance(booking_ref, str):
        return {"ok": False, "code": ToolCode.VALIDATION_ERROR,
                "message": "booking_ref is required"}
    booking = db.fetch_booking(conn, booking_ref)
    if booking is None:
        return {"ok": False, "code": ToolCode.BOOKING_NOT_FOUND,
                "message": f"No booking for {booking_ref}"}
    return {"ok": True, "code": ToolCode.OK, "booking": booking}


def _already_assigned_result(existing, seat, flight_number):
    return {
        "ok": True,
        "code": ToolCode.ALREADY_ASSIGNED,
        "assignment_id": existing["id"],
        "seat": seat,
        "flight_number": flight_number,
        "idempotent_replay": True,
        "message": "seat selection was already recorded",
    }


def book_seat_selection(conn, booking_ref, flight_number, seat, passenger_id):
    """Write / side-effect tool: persist a seat assignment idempotently.

    The logical idempotency key for this tool is:
        (booking_ref, flight_number, seat)

    If an orchestration retry or replay calls the tool with the same logical
    request after the first attempt already wrote the row, the tool returns a
    structured `ALREADY_ASSIGNED` success instead of performing another INSERT.
    That makes the side effect safe under retries and gives the planner a
    machine-readable way to distinguish "already done" from a real failure.
    """
    # Basic argument validation.
    if not all([booking_ref, flight_number, seat, passenger_id]):
        return {"ok": False, "code": ToolCode.VALIDATION_ERROR,
                "message": "missing required arguments"}

    # Idempotency check must happen before the availability check.  On a replay,
    # the first successful write has already marked the seat unavailable, so an
    # availability-first implementation incorrectly reports SEAT_TAKEN for its
    # own completed request.
    existing = db.find_existing_assignment(conn, booking_ref, flight_number, seat)
    if existing is not None:
        if existing["passenger_id"] != passenger_id:
            return {"ok": False, "code": ToolCode.VALIDATION_ERROR,
                    "message": "existing assignment passenger does not match request"}
        return _already_assigned_result(existing, seat, flight_number)

    available = db.seat_is_available(conn, flight_number, seat)
    if available is None:
        return {"ok": False, "code": ToolCode.SEAT_UNKNOWN,
                "message": f"seat {seat} not on {flight_number}"}

    if not available:
        return {"ok": False, "code": ToolCode.SEAT_TAKEN,
                "message": f"seat {seat} is taken"}

    try:
        new_id = db.insert_seat_assignment(
            conn, booking_ref, flight_number, seat, passenger_id
        )
    except psycopg2.errors.UniqueViolation:
        # Final guard for databases that have the unique idempotency constraint
        # and receive two concurrent/replayed attempts.  If another attempt won
        # the race, surface it as the same structured already-done success.
        existing = db.find_existing_assignment(conn, booking_ref, flight_number, seat)
        if existing is not None and existing["passenger_id"] == passenger_id:
            return _already_assigned_result(existing, seat, flight_number)
        return {"ok": False, "code": ToolCode.SEAT_TAKEN,
                "message": f"seat {seat} is taken"}

    return {"ok": True, "code": ToolCode.OK, "assignment_id": new_id,
            "seat": seat, "flight_number": flight_number,
            "idempotent_replay": False}
