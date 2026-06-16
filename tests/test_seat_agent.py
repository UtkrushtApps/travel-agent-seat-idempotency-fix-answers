"""Tests for the seat-selection agent.

- The happy-path test must always pass (preserve existing behaviour).
- The idempotency/retry test currently FAILS because a retried write creates
  a duplicate seat_assignments row and does not surface a structured
  already-done outcome. It must pass after the fix.
"""
from agent import db
from agent.orchestrator import run_seat_selection, FlakyUpstream
from agent.tools import ToolCode


def test_happy_path_first_seat_selection(conn):
    """A brand-new seat selection succeeds and writes exactly one row."""
    request = {"booking_ref": "BK1001", "seat": "12A"}
    resp = run_seat_selection(conn, request, upstream=FlakyUpstream(),
                              request_id="req-happy-1")

    assert resp["ok"] is True
    assert resp["code"] == ToolCode.OK
    assert resp["seat"] == "12A"
    assert resp["flight_number"] == "AI202"
    assert "assignment_id" in resp

    count = db.count_assignments(conn, "BK1001", "AI202", "12A")
    assert count == 1


def test_retry_does_not_duplicate_seat_assignment(conn):
    """When the upstream disrupts the first write attempt and the orchestrator
    retries the SAME logical request, only one seat assignment must exist and
    the outcome must be a structured success/already-done, not an opaque
    failure or a duplicate."""
    request = {"booking_ref": "BK1001", "seat": "12B"}
    # fail_first=True simulates a transient disruption AFTER the side effect,
    # forcing the orchestrator to retry the write step.
    upstream = FlakyUpstream(fail_first=True)
    resp = run_seat_selection(conn, request, upstream=upstream,
                              request_id="req-retry-1")

    # Exactly one assignment row for this logical request.
    count = db.count_assignments(conn, "BK1001", "AI202", "12B")
    assert count == 1, f"expected 1 assignment, found {count} (duplicate write)"

    # The overall turn should report a structured, machine-readable outcome
    # that the planner can interpret (success or an explicit already-done
    # code), never an opaque failure.
    assert resp["ok"] is True, f"expected safe replay success, got {resp}"
    assert resp["code"] in (ToolCode.OK,), f"unexpected code {resp['code']}"


def test_repeated_identical_request_is_idempotent(conn):
    """Calling the same seat-selection turn twice (e.g. a client/agent replay)
    must not create a second row and must return a structured outcome."""
    request = {"booking_ref": "BK1003", "seat": "3A"}

    first = run_seat_selection(conn, request, upstream=FlakyUpstream(),
                               request_id="req-idem-1")
    assert first["ok"] is True

    second = run_seat_selection(conn, request, upstream=FlakyUpstream(),
                                request_id="req-idem-1")

    count = db.count_assignments(conn, "BK1003", "AI410", "3A")
    assert count == 1, f"replay created duplicate rows: {count}"
    assert second["ok"] is True
    assert second["code"] in (ToolCode.OK,)


def test_unknown_seat_returns_structured_error(conn):
    """Validation/business errors stay structured and machine-readable."""
    request = {"booking_ref": "BK1001", "seat": "99Z"}
    resp = run_seat_selection(conn, request, upstream=FlakyUpstream(),
                              request_id="req-bad-seat")
    assert resp["ok"] is False
    assert resp["code"] == ToolCode.SEAT_UNKNOWN
