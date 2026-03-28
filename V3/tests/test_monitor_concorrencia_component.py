from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from monitor_concorrencia.monitor import MonitorConcorrencia
from monitor_concorrencia.portais import PORTAIS_PADRAO
from monitor_concorrencia.schemas import PortalArticle


class FakeKafka:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict, str | None]] = []

    async def send(self, topic: str, value: dict, key: str | None = None) -> None:
        self.messages.append((topic, value, key))


class FakeScanner:
    async def scan_portal(
        self,
        portal_name: str,
        portal_url: str,
        requires_browser: bool = False,
        selectors: list[str] | None = None,
    ) -> list[PortalArticle]:
        return [
            PortalArticle(
                portal=portal_name,
                titulo="Concorrente destaca alerta de clima extremo no sudeste",
                url=f"{portal_url}/noticia",
                coletado_em=datetime.now(timezone.utc),
            )
        ]


def test_monitor_concorrencia_routes_only_allowed_topics() -> None:
    async def _run() -> None:
        kafka = FakeKafka()
        monitor = MonitorConcorrencia(kafka_client=kafka)
        monitor.scanner = FakeScanner()

        published = await monitor.run_cycle(["Mercado reage a pacote econômico do governo"])

        assert published >= 1
        topics = {topic for topic, _, _ in kafka.messages}
        assert "pautas-especiais" not in topics
        assert topics.issubset({"pautas-gap", "consolidacao", "breaking-candidate"})

    asyncio.run(_run())


def test_monitor_concorrencia_has_8_required_portals() -> None:
    names = {portal.nome for portal in PORTAIS_PADRAO}
    required = {"g1", "uol", "folha", "estadao", "cnn_brasil", "r7", "terra", "metropoles"}
    assert names == required
