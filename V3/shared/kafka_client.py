"""Cliente Kafka reutilizável para producer/consumer."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class KafkaClient:
    """Wrapper para aiokafka com serialização JSON, lz4, e manual commit."""

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer = None

    async def start_producer(self) -> None:
        """Inicializa producer assíncrono com lz4 e acks=all."""
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            compression_type="lz4",
            linger_ms=10,
            batch_size=32768,
            acks="all",
        )
        await self._producer.start()

    async def stop_producer(self) -> None:
        """Fecha producer se existir."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def send(self, topic: str, value: dict[str, Any], key: Optional[str] = None) -> None:
        """Publica mensagem JSON com confirmação de entrega."""
        if self._producer is None:
            raise RuntimeError("Producer Kafka não iniciado. Chame start_producer() primeiro.")
        await self._producer.send_and_wait(topic, value=value, key=key)

    def build_consumer(
        self,
        topic: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = False,
    ):
        """Constrói consumer com manual commit e offset earliest por padrão."""
        from aiokafka import AIOKafkaConsumer

        return AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=enable_auto_commit,
            max_poll_records=50,
        )

    @staticmethod
    async def commit_safe(consumer) -> None:
        """Commit manual com tratamento de erro."""
        try:
            await consumer.commit()
        except Exception:
            logger.warning("Falha no commit Kafka, será retentado no próximo ciclo", exc_info=True)
