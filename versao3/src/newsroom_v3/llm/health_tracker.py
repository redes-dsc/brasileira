from collections import defaultdict, deque
from dataclasses import dataclass
from time import time


@dataclass
class CallSample:
    success: bool
    latency_ms: int
    ts: float


class ProviderHealthTracker:
    def __init__(self, window_size: int = 20) -> None:
        self.window_size = window_size
        self.samples: dict[str, deque[CallSample]] = defaultdict(lambda: deque(maxlen=window_size))

    def record(self, model_id: str, success: bool, latency_ms: int) -> None:
        self.samples[model_id].append(CallSample(success=success, latency_ms=latency_ms, ts=time()))

    def calculate_health(self, model_id: str) -> float:
        recent = list(self.samples[model_id])
        if not recent:
            return 50.0
        total = len(recent)
        successes = sum(1 for x in recent if x.success)
        success_rate = successes / total
        avg_latency = sum(x.latency_ms for x in recent) / total
        avg_latency_factor = 1.0 - min(avg_latency / 30000.0, 1.0)

        last_error_ts = max((x.ts for x in recent if not x.success), default=0.0)
        error_recency_secs = max(time() - last_error_ts, 0.0) if last_error_ts else 300.0
        score = (success_rate * 50.0) + (avg_latency_factor * 30.0) + (min(error_recency_secs / 300.0, 1.0) * 20.0)
        return round(score, 2)
