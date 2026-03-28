from dataclasses import dataclass


@dataclass
class Scratchpad:
    agent: str
    cycle_id: str
    payload: dict
