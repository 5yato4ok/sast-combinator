"""What a watcher's patience is worth, stated in the terms the incident was measured in."""

import pytest
from pipeline.dast.resilience import (
    HANDSHAKE,
    IN_FLIGHT,
    NO_RETRY,
    PROMPT,
    RetryBudget,
    RetryBudgetError,
    RetryClock,
    describe_cause,
)


class _Clock:
    """A clock that moves only when something sleeps, so a budget is exact and instant in tests."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def _spend(budget: RetryBudget, *, notices=None) -> _Clock:
    """Fail instantly, over and over, until the clock refuses -- the shape of the real outage."""
    clock = _Clock()
    retry = RetryClock(
        budget,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        on_retry=None if notices is None else notices.append,
    )
    while retry.wait(cause="ConnectError: [Errno 111] Connection refused"):
        pass
    return clock


def test_an_instantly_refused_endpoint_still_gets_the_whole_window():
    """
    The regression this module exists for.

    Three attempts against a peer that refuses connections in microseconds is a two-second
    budget, and a two-minute outage in the tunnel ended a 103-minute watch. Counting time instead
    of attempts is what makes the declared patience the patience actually granted.
    """
    clock = _spend(IN_FLIGHT)

    assert sum(clock.sleeps) == pytest.approx(IN_FLIGHT.window_seconds)
    # Nothing about "how many" is promised, only that a blip of minutes is survivable.
    assert sum(clock.sleeps) > 120
    assert len(clock.sleeps) > 3


def test_backoff_climbs_to_its_cap_and_the_final_wait_is_trimmed_to_the_window():
    clock = _spend(IN_FLIGHT)

    assert clock.sleeps[:5] == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert max(clock.sleeps) == IN_FLIGHT.max_backoff_seconds
    # The last wait ends at the edge of the budget instead of overshooting it.
    assert sum(clock.sleeps) == pytest.approx(IN_FLIGHT.window_seconds)
    assert clock.sleeps[-1] <= IN_FLIGHT.max_backoff_seconds


def test_starting_a_run_is_not_worth_the_patience_of_watching_one():
    """Nothing is in flight yet, so the caller's own retry is the cheaper place to wait."""
    assert sum(_spend(HANDSHAKE).sleeps) == pytest.approx(HANDSHAKE.window_seconds)
    assert HANDSHAKE.window_seconds < IN_FLIGHT.window_seconds
    assert PROMPT.window_seconds < HANDSHAKE.window_seconds


def test_a_call_that_must_not_be_repeated_never_waits():
    assert _spend(NO_RETRY).sleeps == []


def test_every_wait_is_announced_before_it_starts():
    """A watcher absorbing an outage in silence is indistinguishable from a hung one."""
    notices = []
    _spend(HANDSHAKE, notices=notices)

    assert [notice.attempt for notice in notices[:3]] == [1, 2, 3]
    assert all("Connection refused" in notice.cause for notice in notices)
    assert notices[0].delay_seconds == HANDSHAKE.first_backoff_seconds
    # Every notice can answer "how much longer will this go on".
    assert notices[0].remaining_seconds == pytest.approx(HANDSHAKE.window_seconds)
    assert notices[-1].remaining_seconds < notices[0].remaining_seconds


def test_a_budget_that_could_not_schedule_a_retry_is_rejected_on_sight():
    with pytest.raises(RetryBudgetError):
        RetryBudget(window_seconds=-1.0, first_backoff_seconds=1.0, max_backoff_seconds=1.0)
    with pytest.raises(RetryBudgetError):
        RetryBudget(window_seconds=10.0, first_backoff_seconds=0.0, max_backoff_seconds=1.0)
    with pytest.raises(RetryBudgetError):
        RetryBudget(window_seconds=10.0, first_backoff_seconds=5.0, max_backoff_seconds=1.0)


def test_a_cause_names_the_error_under_the_client_wrapper():
    """"Connection refused", "name does not resolve" and "read timed out" need different repairs."""
    resolution = OSError("[Errno -2] Name or service not known")
    wrapped = ConnectionError("All connection attempts failed")
    wrapped.__cause__ = resolution

    rendered = describe_cause(wrapped)

    assert rendered == (
        "ConnectionError: All connection attempts failed <- OSError: [Errno -2] Name or service not known"
    )


def test_a_cause_keeps_the_deployment_hostname_out_of_a_tenant_readable_log():
    failure = ConnectionError("connection to sc-vm-security001.nxlocal:8443 refused")

    rendered = describe_cause(failure, redact=("https://sc-vm-security001.nxlocal:8443", "sc-vm-security001.nxlocal"))

    assert "sc-vm-security001" not in rendered
    assert "<gateway>" in rendered
    assert "refused" in rendered


def test_a_cause_chain_cannot_flood_the_line_it_is_printed_on():
    deepest = OSError("errno")
    middle = ConnectionError("middle")
    middle.__cause__ = deepest
    outer = RuntimeError("outer")
    outer.__cause__ = middle
    outermost = RuntimeError("outermost")
    outermost.__cause__ = outer

    assert describe_cause(outermost).count("<-") == 2


def test_a_cause_cycle_does_not_hang_the_renderer():
    first = RuntimeError("first")
    second = RuntimeError("second")
    first.__cause__ = second
    second.__cause__ = first

    assert describe_cause(first) == "RuntimeError: first <- RuntimeError: second"
