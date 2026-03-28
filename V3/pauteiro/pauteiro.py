"""Orquestrador do componente Pauteiro."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from shared.kafka_client import KafkaClient
from shared.memory import MemoryManager
from shared.schemas import LLMRequest

from .briefing_generator import BriefingGenerator
from .config import PauteiroConfig
from .schemas import PautaEspecial
from .signal_aggregator import SignalAggregator
from .trend_scanner import TrendScanner

logger = logging.getLogger(__name__)


class PauteiroAgent:
    """Gera pautas especiais em paralelo ao pipeline principal."""

    def __init__(self, kafka_client: KafkaClient, router=None, memory: MemoryManager | None = None, config: PauteiroConfig | None = None):
        self.kafka = kafka_client
        self.router = router
        self.memory = memory
        self.config = config or PauteiroConfig()
        self.scanner = TrendScanner()
        self.aggregator = SignalAggregator(config=self.config, memory=memory)
        self.briefing = BriefingGenerator(router=router)

    async def _analyze_signals(self, editoria: str, sinais: list[dict]) -> str:
        if self.router is None:
            return "analise_local"
        request = LLMRequest(
            task_type="trending_detection",
            messages=[
                {"role": "system", "content": "Resuma padrão de tendência em uma frase."},
                {"role": "user", "content": f"Editoria: {editoria}; sinais: {sinais[:5]}"},
            ],
            max_tokens=120,
            temperature=0.1,
        )
        try:
            response = await self.router.route_request(request)
            return response.content.strip()
        except Exception:
            logger.exception("Falha em análise padrão de sinais")
            return "analise_indisponivel"

    async def run_cycle(self, raw_signals: list[dict], cycle_id: str) -> list[PautaEspecial]:
        """Processa sinais e publica em pautas-especiais por editoria."""

        if not raw_signals:
            logger.info("Ciclo %s: nenhum sinal recebido, pulando processamento", cycle_id)
            return []

        logger.info("Ciclo %s: processando %d sinais brutos", cycle_id, len(raw_signals))
        parsed = await self.scanner.scan(raw_signals[: self.config.max_signals_per_cycle])
        logger.info("Ciclo %s: %d sinais normalizados pelo scanner", cycle_id, len(parsed))

        deduped = await self.aggregator.deduplicate(parsed, cycle_id=cycle_id)
        logger.info("Ciclo %s: %d sinais após deduplicação", cycle_id, len(deduped))

        if not deduped:
            logger.info("Ciclo %s: todos os sinais duplicados, nenhuma pauta gerada", cycle_id)
            return []

        grouped = await self.aggregator.group_by_editoria(deduped)
        logger.info("Ciclo %s: sinais agrupados em %d editorias", cycle_id, len(grouped))

        pautas: list[PautaEspecial] = []
        for editoria, sinais in grouped.items():
            try:
                analise = await self._analyze_signals(editoria, [s.model_dump(mode="json") for s in sinais])
                briefing = await self.briefing.generate(editoria, sinais)
                pauta = PautaEspecial(
                    pauta_id=f"{cycle_id}:{editoria}",
                    editoria=editoria,
                    titulo=f"Pauta especial: {editoria}",
                    briefing=f"{briefing}\n\nAnálise de sinais: {analise}",
                    sinais_ids=[s.signal_id for s in sinais],
                    prioridade="alta" if any(s.score >= 0.8 for s in sinais) else "normal",
                    criado_em=datetime.now(timezone.utc),
                )
                await self.kafka.send(
                    self.config.kafka_topic_pautas,
                    pauta.model_dump(mode="json"),
                    key=editoria,
                )
                pautas.append(pauta)
                logger.info("Ciclo %s: pauta gerada para editoria=%s (%d sinais, prioridade=%s)",
                            cycle_id, editoria, len(sinais), pauta.prioridade)
            except Exception:
                logger.exception("Ciclo %s: falha ao gerar pauta para editoria=%s", cycle_id, editoria)

        return pautas
