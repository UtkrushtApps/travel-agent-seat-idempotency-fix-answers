# Solution Steps

1. Identify the retry flaw: `book_seat_selection` checked seat availability before checking whether the same logical request had already succeeded, so a replay saw its own seat as unavailable or inserted another row.

2. Define an explicit machine-readable outcome for an already-completed write, e.g. `ToolCode.ALREADY_ASSIGNED`, while keeping the existing `OK` and validation/business error codes.

3. Add an idempotency lookup before the availability check in `book_seat_selection`. Use the stable logical request tuple `(booking_ref, flight_number, seat)` to find an existing assignment.

4. If an existing matching assignment is found for the same passenger, return `ok: True` with code `ALREADY_ASSIGNED`, the existing `assignment_id`, and an `idempotent_replay` marker. Do not insert another row.

5. Only when no existing assignment is found should the tool check inventory, return `SEAT_UNKNOWN` or `SEAT_TAKEN` as before, and insert a new assignment on the happy path.

6. Add a database uniqueness constraint on `(booking_ref, flight_number, seat)` in the initialization schema as a defensive data-integrity guard for fresh databases.

7. Catch a possible `UniqueViolation` around the insert and translate it into the same structured already-done result if another attempt inserted the row first.

8. Update the orchestrator to treat any `ok: True` write-tool result, including `ALREADY_ASSIGNED`, as a successful turn. Preserve the top-level `code: OK` for backward compatibility and expose the exact tool result through `outcome_code` and the trace.

9. Keep existing structured validation/business errors unchanged so unknown seats and invalid bookings remain machine-readable failures.

10. Run `docker compose up -d` and then `python -m pytest -q` to verify the happy path, retry idempotency, replay idempotency, and structured error tests all pass.

