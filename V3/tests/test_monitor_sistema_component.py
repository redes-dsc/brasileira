from __future__ import annotations

import asyncio

from monitor_sistema.adaptive_polling import AdaptivePolling
from monitor_sistema.config import MonitorSistemaConfig
from monitor_sistema.focas import FocasController
from monitor_sistema.throughput_tracker import ThroughputTracker


def test_throughput_thresholds() -> None:
    async def _run() -> None:
        tracker = ThroughputTracker(MonitorSistemaConfig())

        assert (await tracker.evaluate(45)).nivel == "saudavel"
        assert (await tracker.evaluate(20)).nivel == "alerta"
        assert (await tracker.evaluate(5)).nivel == "critico"

    asyncio.run(_run())


def test_focas_never_disables_and_never_dead_tier() -> None:
    async def _run() -> None:
        config = MonitorSistemaConfig()
        focas = FocasController(AdaptivePolling(config))

        decision = await focas.decide(
            {"id": 77, "polling_interval_min": 3000, "tier": "dead", "consecutive_failures": 4},
            throughput_level="saudavel",
        )

        assert decision.ativa is True
        assert decision.tier != "dead"
        assert decision.polling_interval_min <= 24 * 60

    asyncio.run(_run())
