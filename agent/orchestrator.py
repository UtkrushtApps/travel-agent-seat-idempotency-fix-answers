"""Deterministic orchestration layer for the seat-selection agent.

The 'planner' here is a fixed local function (no live LLM). It mimics what an
LLM planner would do: look up the booking with a read-only tool, then call the
write tool to assign the seat. The orchestrator wraps the write step with a
bounded retry to tolerate transient upstream slowness.

The write tool is idempotent: if a retry/replay observes the same logical seat
selection was already persisted, it returns a structured already-done success
instead of inserting another row.
"""
import logging

from agent import tools
from agent.tools import ToolCode

logger = logging.getLogger("seat_agent")

MAX_WRITE_ATTEMPTS = 2


class FlakyUpstream:
    """Simulates a slow upstream where the first attempt 'times out' from the
    orchestrator's point of view even though the underlying write may already
    have proceeded.

    `fail_first` controls whether the first write attempt raises a transient
    error after the tool has performed its side effect.
    """

    def __init__(self, fail_first=False):
        self.fail_first = fail_first
        self.calls = 0

    def maybe_disrupt(self, did_write):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            # Transient failure surfaced to the orchestrator AFTER the write.
            raise TimeoutError("upstream seat service timed out")


def run_seat_selection(conn, request, upstream=None, request_id=None):
    """Run the agent turn for a seat-selection request.

    request: dict with booking_ref, seat (passenger derived from booking).
    Returns a structured agent response with a `trace` list of tool events.
    """
    upstream = upstream or FlakyUpstream()
    trace = []

    booking_ref = request.get("booking_ref")
    seat = request.get("seat")

    # Step 1: read-only tool.
    read_result = tools.get_booking(conn, booking_ref)
    trace.append({"tool": "get_booking", "result": read_result})
    if not read_result["ok"]:
        return {"ok": False, "code": read_result["code"],
                "message": read_result["message"], "trace": trace}

    booking = read_result["booking"]
    if booking["status"] != "CONFIRMED":
        return {"ok": False, "code": ToolCode.BOOKING_NOT_CONFIRMED,
                "message": "booking is not confirmed", "trace": trace}

    flight_number = booking["flight_number"]
    passenger_id = booking["passenger_id"]

    # Step 2: write tool, wrapped in a bounded retry for transient errors.
    last_result = None
    for attempt in range(1, MAX_WRITE_ATTEMPTS + 1):
        try:
            logger.info("write attempt %s request_id=%s seat=%s",
                        attempt, request_id, seat)
            # The orchestrator may be disrupted by the flaky upstream AFTER
            # the tool has already performed its side effect.  The write tool
            # must therefore be safe to call again for the same logical request.
            result = tools.book_seat_selection(
                conn, booking_ref, flight_number, seat, passenger_id
            )
            upstream.maybe_disrupt(did_write=result.get("ok", False))
            last_result = result
            trace.append({"tool": "book_seat_selection",
                          "attempt": attempt, "result": result})
            if result["ok"]:
                break
            # Business/validation failures are deterministic; only exceptions
            # from the simulated upstream are retried.
            break
        except TimeoutError as exc:
            logger.warning("transient write failure attempt=%s err=%s",
                           attempt, exc)
            trace.append({"tool": "book_seat_selection",
                          "attempt": attempt,
                          "result": {"ok": False, "code": "TRANSIENT",
                                     "message": str(exc)}})
            # Retry: the write may already have happened, so the tool must
            # detect and report an idempotent replay on the next attempt.
            continue

    if last_result and last_result.get("ok"):
        # Keep the top-level success code backward-compatible as OK so existing
        # happy-path consumers continue to work.  The exact tool outcome remains
        # machine-readable in both `outcome_code` and the trace, allowing a
        # planner to distinguish a fresh write from an already-done replay.
        return {"ok": True, "code": ToolCode.OK,
                "outcome_code": last_result["code"],
                "assignment_id": last_result["assignment_id"],
                "seat": seat, "flight_number": flight_number,
                "idempotent_replay": last_result.get("idempotent_replay", False),
                "trace": trace}

    return {"ok": False,
            "code": (last_result or {}).get("code", "WRITE_FAILED"),
            "message": (last_result or {}).get("message", "seat write failed"),
            "trace": trace}
