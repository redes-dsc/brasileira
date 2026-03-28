from __future__ import annotations

import asyncio

from pauteiro.pauteiro import PauteiroAgent


class FakeKafka:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict, str | None]] = []

    async def send(self, topic: str, value: dict, key: str | None = None) -> None:
        self.messages.append((topic, value, key))


def test_pauteiro_parallel_and_non_blocking_entrypoint() -> None:
    async def _run() -> None:
        kafka = FakeKafka()
        agent = PauteiroAgent(kafka_client=kafka)

        raw_signals = [
            {
                "signal_id": "s1",
                "titulo": "Governo anuncia novo pacote econômico",
                "resumo": "Medidas fiscais e impacto no mercado",
                "editoria": "economia",
                "fonte": "portal-a",
                "score": 0.91,
                "url": "https://exemplo.com/1",
            },
            {
                "signal_id": "s2",
                "titulo": "Governo anuncia novo pacote econômico",
                "resumo": "Duplicado por título+url",
                "editoria": "economia",
                "fonte": "portal-b",
                "score": 0.88,
                "url": "https://exemplo.com/1",
            },
        ]

        pautas = await agent.run_cycle(raw_signals, cycle_id="c1")

        assert len(pautas) == 1
        assert kafka.messages
        topic, payload, key = kafka.messages[0]
        assert topic == "pautas-especiais"
        assert key == "economia"
        assert "raw-articles" not in str(payload)
        assert "classified-articles" not in str(payload)

    asyncio.run(_run())
