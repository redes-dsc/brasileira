"""Worker Pool unificado (RSS + Scraper) com dedup e health tracking."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .rss_fetcher import RSSFetcher
from .scraper_engine import ScraperEngine

logger = logging.getLogger(__name__)

TOPIC_ASSIGNMENTS = "fonte-assignments"
TOPIC_RAW_ARTICLES = "raw-articles"
CONSUMER_GROUP = "ingestion-workers"
DEFAULT_NUM_WORKERS = 30


@dataclass
class SourceHealthRecord:
    fonte_id: int
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    total_successes: int = 0
    total_failures: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_error_type: Optional[str] = None
    avg_latency_ms: float = 0.0
    articles_last_cycle: int = 0


class SourceHealthTracker:
    """Health por fonte para adaptive polling."""

    def __init__(self, redis_client=None, db_pool=None):
        self.redis = redis_client
        self.db_pool = db_pool
        self._local_cache: dict[int, SourceHealthRecord] = {}

    def get_source_health(self, fonte_id: int) -> Optional[SourceHealthRecord]:
        return self._local_cache.get(fonte_id)

    def record_success(self, fonte_id: int, latency_ms: float = 0.0, articles_count: int = 0) -> None:
        record = self._local_cache.setdefault(fonte_id, SourceHealthRecord(fonte_id=fonte_id))
        record.consecutive_successes += 1
        record.consecutive_failures = 0
        record.total_successes += 1
        record.last_success = datetime.now(timezone.utc)
        record.articles_last_cycle = articles_count
        record.avg_latency_ms = latency_ms if record.avg_latency_ms == 0 else record.avg_latency_ms * 0.8 + latency_ms * 0.2

    def record_failure(self, fonte_id: int, error_type: str = "unknown") -> None:
        record = self._local_cache.setdefault(fonte_id, SourceHealthRecord(fonte_id=fonte_id))
        record.consecutive_failures += 1
        record.consecutive_successes = 0
        record.total_failures += 1
        record.last_failure = datetime.now(timezone.utc)
        record.last_error_type = error_type

    async def persist_to_postgres(self) -> None:
        if self.db_pool is None:
            return
        async with self.db_pool.acquire() as conn:
            for fonte_id, record in self._local_cache.items():
                await conn.execute(
                    """
                    UPDATE fontes SET
                        ultimo_sucesso = COALESCE($2, ultimo_sucesso),
                        ultimo_erro = $3
                    WHERE id = $1
                    """,
                    fonte_id,
                    record.last_success,
                    record.last_error_type,
                )

    async def persist_to_redis(self) -> None:
        if self.redis is None:
            return
        for fonte_id, record in self._local_cache.items():
            await self.redis.hset(
                f"source:health:{fonte_id}",
                mapping={
                    "consecutive_failures": record.consecutive_failures,
                    "consecutive_successes": record.consecutive_successes,
                    "last_success": record.last_success.isoformat() if record.last_success else "",
                    "last_error_type": record.last_error_type or "",
                    "avg_latency_ms": str(round(record.avg_latency_ms, 2)),
                    "articles_last_cycle": record.articles_last_cycle,
                },
            )
            await self.redis.expire(f"source:health:{fonte_id}", 7200)


class DeduplicationEngine:
    """Deduplicação em camadas Redis URL + SHA + SimHash."""

    def __init__(self, redis_client=None, db_pool=None):
        import hashlib
        import re
        import unicodedata

        self.redis = redis_client
        self.db_pool = db_pool
        self.hashlib = hashlib
        self.re = re
        self.unicodedata = unicodedata
        self._simhash_index: dict[int, str] = {}

    def normalize_url(self, url: str) -> str:
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        parsed = urlparse(url)
        netloc = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.rstrip("/")
        tracking_params = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "fbclid",
            "gclid",
            "ref",
            "source",
            "amp",
        }
        query = ""
        if parsed.query:
            params = parse_qs(parsed.query)
            cleaned = {k: v for k, v in params.items() if k.lower() not in tracking_params}
            if cleaned:
                query = urlencode(cleaned, doseq=True)
        return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))

    def normalize_title(self, titulo: str) -> str:
        titulo = titulo.lower().strip()
        titulo = self.unicodedata.normalize("NFKD", titulo)
        titulo = "".join(ch for ch in titulo if not self.unicodedata.combining(ch))
        titulo = self.re.sub(r"[^a-z0-9\s]", "", titulo)
        titulo = self.re.sub(r"\s+", " ", titulo).strip()
        return titulo

    def compute_content_hash(self, titulo: str, dominio_fonte: str, data: Optional[str]) -> str:
        payload = f"{self.normalize_title(titulo)}|{dominio_fonte}|{(data or '')[:10]}"
        return self.hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compute_simhash(self, text: str, hashbits: int = 64) -> int:
        normalized = self.normalize_title(text)
        tokens = normalized.split()
        if len(tokens) < 3:
            return 0
        shingles = [" ".join(tokens[idx : idx + 3]) for idx in range(len(tokens) - 2)]
        vector = [0] * hashbits
        for shingle in shingles:
            hashed = int(self.hashlib.md5(shingle.encode("utf-8")).hexdigest(), 16)
            for bit in range(hashbits):
                vector[bit] += 1 if (hashed & (1 << bit)) else -1
        value = 0
        for bit, score in enumerate(vector):
            if score >= 0:
                value |= 1 << bit
        return value

    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        return bin(hash1 ^ hash2).count("1")

    async def check_and_register(self, article: dict) -> bool:
        from urllib.parse import urlparse

        url = article.get("url", "")
        titulo = article.get("titulo", "")
        url_hash = article.get("url_hash", "")
        if not url or not url_hash:
            return False

        url_norm = self.normalize_url(url)
        if self.redis is not None:
            is_new = await self.redis.sadd("dedup:urls", url_norm)
            if not is_new:
                return False
            await self.redis.expire("dedup:urls", 259200)

        if self.db_pool is not None and titulo:
            domain = urlparse(url).netloc
            content_hash = self.compute_content_hash(titulo, domain, article.get("data_publicacao"))
            async with self.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    INSERT INTO artigos (url_hash, titulo, url_fonte, editoria)
                    VALUES ($1,$2,$3,$4)
                    ON CONFLICT (url_hash) DO NOTHING
                    """,
                    content_hash,
                    titulo,
                    url,
                    article.get("grupo", "geral"),
                )
                if result == "INSERT 0 0":
                    return False

        if titulo:
            simhash = self.compute_simhash(titulo)
            if simhash:
                for existing, existing_url_hash in self._simhash_index.items():
                    if self.hamming_distance(simhash, existing) <= 3:
                        article["near_duplicate"] = True
                        article["near_duplicate_of"] = existing_url_hash
                        break
                self._simhash_index[simhash] = url_hash
        return True

    async def rebuild_simhash_index(self) -> None:
        if self.db_pool is None:
            return
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT titulo, url_hash FROM artigos
                WHERE publicado_em >= NOW() - INTERVAL '72 hours'
                ORDER BY publicado_em DESC
                LIMIT 10000
                """
            )
        self._simhash_index = {}
        for row in rows:
            title = row["titulo"]
            if not title:
                continue
            simhash = self.compute_simhash(title)
            if simhash:
                self._simhash_index[simhash] = row["url_hash"]


class WorkerPool:
    """Pool de workers assíncronos para coleta de fontes."""

    def __init__(self, kafka_bootstrap: str, num_workers: int = DEFAULT_NUM_WORKERS, db_pool=None, redis_client=None):
        self.kafka_bootstrap = kafka_bootstrap
        self.num_workers = num_workers
        self.db_pool = db_pool
        self.redis = redis_client
        self.dedup = DeduplicationEngine(redis_client=redis_client, db_pool=db_pool)
        self.health_tracker = SourceHealthTracker(redis_client=redis_client, db_pool=db_pool)
        self.rss_fetcher = RSSFetcher(redis_client=redis_client)
        self.scraper_engine = ScraperEngine()
        self.producer: Optional[AIOKafkaProducer] = None
        self._workers: list[asyncio.Task] = []
        self._running = True
        self._stats = {
            "articles_collected": 0,
            "articles_deduped": 0,
            "sources_processed": 0,
            "sources_failed": 0,
        }

    async def start(self) -> None:
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda value: json.dumps(value, default=str).encode("utf-8"),
            key_serializer=lambda key: key.encode("utf-8") if key else None,
            compression_type="lz4",
            linger_ms=10,
            batch_size=32768,
            acks=1,
        )
        await self.producer.start()
        await self.scraper_engine.start()

        for idx in range(self.num_workers):
            task = asyncio.create_task(
                self._worker_loop(worker_id=f"worker-{idx:03d}"),
                name=f"ingestion-worker-{idx:03d}",
            )
            self._workers.append(task)

    async def stop(self) -> None:
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        await self.scraper_engine.stop()
        await self.rss_fetcher.close()
        if self.producer is not None:
            await self.producer.stop()

    async def _worker_loop(self, worker_id: str) -> None:
        consumer = AIOKafkaConsumer(
            TOPIC_ASSIGNMENTS,
            bootstrap_servers=self.kafka_bootstrap,
            group_id=CONSUMER_GROUP,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
            auto_commit_interval_ms=5000,
            max_poll_records=1,
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
        )
        await consumer.start()
        try:
            async for msg in consumer:
                if not self._running:
                    break
                assignment = msg.value
                fonte_id = assignment["fonte_id"]
                fonte_nome = assignment.get("nome", "desconhecido")
                start = datetime.now(timezone.utc)
                try:
                    articles = await self._process_source(worker_id, assignment)
                    new_articles = 0
                    for article in articles:
                        is_new = await self.dedup.check_and_register(article)
                        if is_new:
                            await self.producer.send(TOPIC_RAW_ARTICLES, key=str(fonte_id), value=article)
                            new_articles += 1
                            self._stats["articles_collected"] += 1
                        else:
                            self._stats["articles_deduped"] += 1
                    self._stats["sources_processed"] += 1
                    latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                    self.health_tracker.record_success(
                        fonte_id, latency_ms=latency_ms, articles_count=len(articles)
                    )
                    logger.info(
                        "[%s] fonte=%s coletados=%d novos=%d dedup=%d",
                        worker_id,
                        fonte_nome,
                        len(articles),
                        new_articles,
                        len(articles) - new_articles,
                    )
                except asyncio.TimeoutError:
                    self._stats["sources_failed"] += 1
                    self.health_tracker.record_failure(fonte_id, "timeout")
                except Exception as exc:
                    self._stats["sources_failed"] += 1
                    self.health_tracker.record_failure(fonte_id, type(exc).__name__)
                    logger.exception("[%s] erro em fonte=%s", worker_id, fonte_nome)
        except asyncio.CancelledError:
            logger.info("[%s] cancelado", worker_id)
        finally:
            await consumer.stop()

    async def _process_source(self, worker_id: str, assignment: dict) -> list[dict]:
        fonte_tipo = assignment.get("tipo", "rss")
        if fonte_tipo == "rss":
            coro = self.rss_fetcher.collect(
                feed_url=assignment["url"],
                fonte_id=assignment["fonte_id"],
                fonte_nome=assignment.get("nome", ""),
                grupo=(assignment.get("config_scraper") or {}).get("grupo", ""),
            )
            return await asyncio.wait_for(coro, timeout=15)
        if fonte_tipo == "scraper":
            config = assignment.get("config_scraper") or {}
            timeout = 60 if config.get("needs_javascript", False) else 30
            coro = self.scraper_engine.collect(source_config=assignment)
            return await asyncio.wait_for(coro, timeout=timeout)
        logger.warning("[%s] tipo desconhecido=%s", worker_id, fonte_tipo)
        return []
