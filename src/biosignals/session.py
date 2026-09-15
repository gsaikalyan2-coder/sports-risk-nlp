"""The neurofeedback session state machine. Pure, no Streamlit, no browser.

Why this is a separate module and not logic inside the panel
------------------------------------------------------------
V5 is the only feature in this phase that is an *intervention* rather than an
observation: a closed feedback loop changes the behaviour of the person inside
it. That makes its arithmetic the part most worth being able to test, and a
state machine living inside a Streamlit callback or an iframe script is a state
machine no test can reach. Same argument `src/dashboard/view.py` makes in its
first paragraph, applied to the one feature where being wrong has a person on
the other end of it.

So every number the V5 panel reports -- elapsed, time in target, longest hold --
is computed here, from a sequence of ratios, by code that has never heard of a
ring or a browser. `tests/test_biosignals.py` drives it with a hand-written
sequence and checks the counters against arithmetic done on paper.

# BLOCKED UNTIL ETHICS SIGN-OFF
This module does not know whether its ratios came from a simulator or a person,
and deliberately so -- a state machine that branched on the source would be a
state machine that behaves differently in the case nobody can test. The guard
lives where the source does, in `sources.py::require_simulated`, and the V5 page
calls it before it renders. Before this runs against any person it needs ethics
approval and a clinician in the loop.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class SessionState:
    """One tick's worth of session arithmetic. Frozen: a tick returns a new one.

    Immutable because the alternative -- mutating a session object in place --
    makes "what did the counters say three ticks ago" unanswerable, and that is
    exactly the question anybody reviewing a training session asks.
    """

    ticks: int = 0
    elapsed_s: float = 0.0
    in_target_s: float = 0.0
    longest_hold_s: float = 0.0
    current_hold_s: float = 0.0
    ratio: float = 0.0
    on_target: bool = False

    @property
    def in_target_fraction(self) -> float:
        """Share of the session spent above the target. 0.0 before the first tick."""
        return self.in_target_s / self.elapsed_s if self.elapsed_s > 0 else 0.0


@dataclass(frozen=True)
class NeurofeedbackSession:
    """A target threshold and a tick length. Holds no state itself.

    `target` is an explicit parameter with no default derived from data, because
    there is no data here to derive one from. A threshold that arrived from a
    percentile of the simulator's own output would be a number that looks fitted
    and is not, which is the failure mode `features.LOAD_WEIGHTS` avoids by
    naming its weights in the open.
    """

    target: float
    tick_s: float = 1.0

    def __post_init__(self) -> None:
        if self.tick_s <= 0:
            raise ValueError("tick_s must be positive.")
        if self.target <= 0:
            raise ValueError(
                "the target must be positive. A non-positive target is met by every "
                "possible ratio, so the ring would report a full session in target "
                "while showing nothing at all."
            )

    def start(self) -> SessionState:
        """A zeroed state. `reset` is the same call, named for what it is used for."""
        return SessionState()

    reset = start

    def tick(self, state: SessionState, ratio: float) -> SessionState:
        """Advance one tick against one ratio. The whole of V5's arithmetic.

        A tick counts as in-target when `ratio >= target`, inclusive, and the
        boundary is inclusive on purpose: with a strict comparison a ratio that
        sat exactly on the target would read as a miss, and the one value a
        participant would be trying hardest to hold is the one the counter would
        refuse to credit.
        """
        value = float(ratio)
        on_target = value >= self.target
        hold = state.current_hold_s + self.tick_s if on_target else 0.0
        return replace(
            state,
            ticks=state.ticks + 1,
            elapsed_s=state.elapsed_s + self.tick_s,
            in_target_s=state.in_target_s + (self.tick_s if on_target else 0.0),
            current_hold_s=hold,
            longest_hold_s=max(state.longest_hold_s, hold),
            ratio=value,
            on_target=on_target,
        )

    def run(self, ratios) -> SessionState:
        """Fold a whole sequence. Pure, so a test can check the end state."""
        state = self.start()
        for ratio in ratios:
            state = self.tick(state, ratio)
        return state

    def trace(self, ratios) -> tuple[SessionState, ...]:
        """Every intermediate state, for a panel that draws the session so far."""
        state = self.start()
        out = []
        for ratio in ratios:
            state = self.tick(state, ratio)
            out.append(state)
        return tuple(out)
