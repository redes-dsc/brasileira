from dataclasses import dataclass


@dataclass(frozen=True)
class TraceStep:
    trace_id: str
    step: str
    duration_ms: int
