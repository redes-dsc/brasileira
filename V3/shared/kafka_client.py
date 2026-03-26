"""Cliente Kafka reutilizável para producer/consumer."""

from __future__ import annotations

import json
from typing import Any, Optional


class KafkaClient:
    """Wrapper simples para aiokafka com serialização JSON."""

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer = None

    async def start_producer(self) -> None:
        """Inicializa producer assíncrono."""

        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            compression_type="lz4",
            linger_ms=10,
            batch_size=32768,
            acks=1,
        )
        await self._producer.start()

    async def stop_producer(self) -> None:
        """Fecha producer se existir."""

        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def send(self, topic: str, value: dict[str, Any], key: Optional[str] = None) -> None:
        """Publica uma mensagem JSON no tópico informado."""

        if self._producer is None:
            raise RuntimeError("Producer Kafka não iniciado")
        await self._producer.send(topic, value=value, key=key)

    def build_consumer(self, topic: str, group_id: str):
        """Constrói consumer (chamador gerencia start/stop)."""

        from aiokafka import AIOKafkaConsumer

        return AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
            auto_commit_interval_ms=5000,
        )
