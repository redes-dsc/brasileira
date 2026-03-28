from dataclasses import dataclass


@dataclass
class ThroughputMetrics:
    published_per_hour: int
    sources_per_cycle: int
    llm_success_rate: float
    no_image_rate: float
