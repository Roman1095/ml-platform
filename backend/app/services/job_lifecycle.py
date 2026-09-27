from __future__ import annotations


class JobStateError(ValueError):
    """Raised when a job status transition is not allowed."""


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {
        "preparing",
        "cancelled",
        "failed",
    },
    "preparing": {
        "running",
        "cancelled",
        "failed",
    },
    "running": {
        "evaluating",
        "cancelled",
        "failed",
    },
    "evaluating": {
        "exporting",
        "cancelled",
        "failed",
    },
    "exporting": {
        "completed",
        "cancelled",
        "failed",
    },
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


TERMINAL_STATES = {
    "completed",
    "failed",
    "cancelled",
}


CANCELLABLE_STATES = {
    "queued",
    "preparing",
    "running",
    "evaluating",
    "exporting",
}


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition_or_raise(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise JobStateError(
            f"Invalid job transition: {current} -> {target}"
        )


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATES


def is_cancellable(status: str) -> bool:
    return status in CANCELLABLE_STATES
