from __future__ import annotations

import asyncio

from editor_chefe.editor_chefe import EditorChefeObserver


class FakeKafka:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict, str | None]] = []

    async def send(self, topic: str, value: dict, key: str | None = None) -> None:
        self.messages.append((topic, value, key))


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value


def test_editor_chefe_no_gate_and_gap_output() -> None:
    async def _run() -> None:
        observer = EditorChefeObserver(kafka_client=FakeKafka(), redis_client=FakeRedis())

        for forbidden in ("review_article", "quality_gate", "reject", "kill", "hold"):
            assert not hasattr(observer, forbidden)

        weights = await observer.run_cycle(
            [
                {"categoria": "economia", "idade_horas": 0.2},
                {"categoria": "economia", "idade_horas": 0.5},
                {"categoria": "politica", "idade_horas": 2.0},
            ]
        )

        assert len(weights) == 16
        assert all(0.5 <= value <= 2.0 for value in weights.values())
        assert any(topic == "pautas-gap" for topic, _, _ in observer.kafka.messages)
        assert any(key.startswith("editorial:pesos:") for key in observer.redis.values.keys())

    asyncio.run(_run())
