"""How long a process that only *watches* remote work keeps trying before it gives up.

A connector owns no work of its own: the run it reports on lives on the provider and survives
this process. That asymmetry is what the budgets below encode. Dropping the watch costs a
container, a VPN session and a resumed attempt; the run itself keeps going and its log events
queue up on the provider. So a transport failure while a run is in flight is worth waiting out,
and only a provider that stays silent for minutes is worth reporting as unreachable.

Budgets are measured in **wall-clock time, not attempts**. An attempt count looks like patience
and is not: three attempts against a peer that refuses connections instantly is a two-second
budget, which is how a 103-minute watch once ended on a two-minute blip in the tunnel. Time is
the thing the caller actually wants to bound.

Nothing here knows about DAST, HTTP or httpx: the caller classifies its own failures and passes
the exception types it considers transient. A second watcher-style analyzer reuses this module as
it stands.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass


class RetryBudgetError(ValueError):
    """The declared budget could not produce a usable retry schedule."""


@dataclass(frozen=True, slots=True)
class RetryBudget:
    """A bounded window in which one call may be reattempted, and how fast it backs off."""

    window_seconds: float
    first_backoff_seconds: float
    max_backoff_seconds: float

    def __post_init__(self) -> None:
        if self.window_seconds < 0:
            raise RetryBudgetError("retry window must not be negative")
        if self.first_backoff_seconds <= 0:
            raise RetryBudgetError("first backoff must be positive")
        if self.max_backoff_seconds < self.first_backoff_seconds:
            raise RetryBudgetError("max backoff must not be shorter than the first backoff")


# No retry at all: for a call that is not safe to repeat. An empty window is the honest way to
# say that -- a caller reading `NO_RETRY` sees a decision, where `attempts=1` reads like a limit.
NO_RETRY = RetryBudget(window_seconds=0.0, first_backoff_seconds=0.1, max_backoff_seconds=0.1)
# Somebody is waiting for this call to come back: a cancellation, or the last look at a run the
# caller has already decided to abandon. Patience here is a delay in an operator's face and, on
# the abandon path, a pipeline that keeps its capacity lease while nobody watches it.
PROMPT = RetryBudget(window_seconds=15.0, first_backoff_seconds=0.5, max_backoff_seconds=5.0)
# Starting a run that does not exist yet. Nothing is lost by failing here, and the caller's own
# retry (a queued task, a scheduler) is the cheaper place to wait, so this stays short.
HANDSHAKE = RetryBudget(window_seconds=30.0, first_backoff_seconds=0.5, max_backoff_seconds=5.0)
# A run is in flight on the provider. This is the window that matters: it has to outlast an
# ordinary network or service blip (a tunnel renegotiation, a service reload) by a wide margin,
# because the alternative is discarding hours of remote work over seconds of transport.
IN_FLIGHT = RetryBudget(window_seconds=600.0, first_backoff_seconds=1.0, max_backoff_seconds=30.0)


@dataclass(frozen=True, slots=True)
class RetryPlan:
    """Which budget each kind of call gets, chosen once for the life of the process.

    One invocation of a watcher has one purpose -- watch a run, harvest a result, or cancel --
    so the plan is a property of the invocation, not of the call site.
    """

    handshake: RetryBudget
    in_flight: RetryBudget
    teardown: RetryBudget


# Watching a run: wait out blips on everything that concerns a run already accepted.
WATCH = RetryPlan(handshake=HANDSHAKE, in_flight=IN_FLIGHT, teardown=PROMPT)
# Harvesting or cancelling: the caller is on its way out and cannot be kept waiting.
IMPATIENT = RetryPlan(handshake=PROMPT, in_flight=PROMPT, teardown=PROMPT)


# How much of an exception chain is worth one log line: enough to reach the operating-system
# error under two layers of client wrapping, not enough to bury the line it is printed on.
_MAX_CAUSE_LINKS = 3


@dataclass(frozen=True, slots=True)
class RetryNotice:
    """What is about to be waited out, reported before the wait rather than after it.

    A watcher that silently absorbs a five-minute outage is indistinguishable from a hung one.
    """

    attempt: int
    cause: str
    delay_seconds: float
    remaining_seconds: float


class RetryClock:
    """One retry window, spent by a single call.

    Interruption is deliberately not sliced into wake-ups: a terminating signal already breaks
    ``time.sleep`` wherever the process installs a handler that raises, and the only other reason
    to stop early -- an execution deadline -- is checked before each wait. That bounds how far a
    wait can carry the process past such a deadline by one ``max_backoff_seconds``, which is
    nothing against the deadlines these runs carry.
    """

    def __init__(
        self,
        budget: RetryBudget,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        on_retry: Callable[[RetryNotice], None] | None = None,
    ):
        self._budget = budget
        self._sleep = sleep
        self._monotonic = monotonic
        self._on_retry = on_retry
        self._started = monotonic()
        self._attempts = 0

    @property
    def retries(self) -> int:
        """How many reattempts this clock has granted."""
        return self._attempts

    @property
    def elapsed_seconds(self) -> float:
        return self._monotonic() - self._started

    def wait(self, *, cause: str) -> bool:
        """Wait before another attempt, or report that this window is over.

        ``False`` means the caller must fail: the budget is spent, or something outside it (a
        deadline) says there is no point. The caller decides what failing means -- this class
        never raises, so it stays usable for both fatal and recoverable call sites.
        """
        remaining = self._budget.window_seconds - self.elapsed_seconds
        if remaining <= 0:
            return False
        # Never sleep past the end of the window: the last wait is trimmed so the final attempt
        # happens at the edge of the budget instead of beyond it.
        delay = min(self._backoff(), remaining)
        self._attempts += 1
        if self._on_retry is not None:
            self._on_retry(
                RetryNotice(
                    attempt=self._attempts,
                    cause=cause,
                    delay_seconds=delay,
                    remaining_seconds=remaining,
                ),
            )
        self._sleep(delay)
        return True

    def _backoff(self) -> float:
        # No jitter: a watcher is a single client against one endpoint, so there is no herd to
        # spread out, and a deterministic schedule is one that tests can state exactly.
        return min(
            self._budget.first_backoff_seconds * (2 ** self._attempts),
            self._budget.max_backoff_seconds,
        )


def describe_cause(exc: BaseException, *, redact: Iterable[str] = ()) -> str:
    """Render an exception chain into one line a log reader can act on.

    The message alone is not enough to tell a refused connection from a name that will not
    resolve from a read that timed out -- and those three call for entirely different repairs.
    The chain is followed because the useful half is usually the wrapped cause (``ConnectError``
    says nothing; the ``gaierror`` under it says everything).

    ``redact`` removes strings that must not reach a tenant-readable log -- the gateway URL and
    its hostname, which the surrounding error messages deliberately never carry.
    """
    secrets = sorted((str(item) for item in redact if item), key=len, reverse=True)
    links: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(links) < _MAX_CAUSE_LINKS:
        seen.add(id(current))
        detail = str(current).strip()
        for secret in secrets:
            detail = detail.replace(secret, "<gateway>")
        links.append(f"{type(current).__name__}: {detail}" if detail else type(current).__name__)
        current = current.__cause__
    return " <- ".join(links)
