# Briefing Completo para IA — Worker Pool de Coletores V3

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #2 (Prioridade Alta)
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / asyncio / aiokafka / HTTPX / Playwright / feedparser / Redis / PostgreSQL
**Componente:** `brasileira/ingestion/` — worker pool, coletores RSS, coletores scraper, scheduler, deduplicação
**Dependência:** SmartLLMRouter V3 (Componente #1) — já implementado ou em implementação paralela

---

## LEIA ISTO PRIMEIRO — Por que este é o Componente #2

O Worker Pool de Coletores é o **sistema de alimentação de todo o pipeline editorial da brasileira.news V3**. Sem ele, nenhum artigo entra no sistema. Se ele trava, a produção para. Se ele é lento, o portal perde cobertura. Se ele falha silenciosamente, matérias importantes passam despercebidas.

**Volume de produção:** O sistema deve processar **648+ fontes** (RSS + scrapers) a cada ciclo de 15-30 minutos, gerando **1.000+ artigos/dia** para o pipeline downstream. O volume atual do site já ultrapassa 100 matérias/dia, e o sistema deve ser robusto para pelo menos **10x esse fluxo** — ou seja, capacidade para 10.000+ artigos/dia sem degradação.

**Problema central da V2:** Hoje existem **dois processos completamente separados** — `motor_rss_v2.py` e `motor_scrapers_v2.py` — que processam fontes de forma sequencial, com hard caps de 20 artigos/ciclo, sem paralelismo real, sem Kafka, sem deduplicação robusta, e com isolamento de falhas inexistente. Um erro em qualquer ponto trava tudo.

**Este briefing contém TUDO que você precisa para implementar o Worker Pool de Coletores do zero.** Não consulte outros documentos. Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ QUEBRADO NA V2

### 1.1 Dois Processos Separados Sem Coordenação

A V2 divide a ingestão em dois processos Python completamente independentes:

**Processo 1: `motor_rss/motor_rss_v2.py` (652 linhas) — "Raia 1"**
**Processo 2: `motor_scrapers/motor_scrapers_v2.py` (1.267 linhas) — "Raia 2"**

Não existe coordenação entre eles. Ambos acessam o mesmo banco MariaDB para deduplicação, mas sem transações atômicas. Ambos publicam diretamente no WordPress. A race condition entre Raia 1 e Raia 2 publicando o mesmo artigo é um bug crítico documentado.

### 1.2 Processamento Sequencial (motor_rss_v2.py)

```python
# motor_rss_v2.py — LOOP SEQUENCIAL (linha ~509)
feeds_ciclo = selecionar_feeds_ciclo(all_feeds)  # Apenas 60 de 648+
for feed in feeds_ciclo:                          # SEQUENCIAL
    try:
        entries = process_feed(feed)              # feedparser SÍNCRONO
        for entry in entries[:MAX_ARTICLES_PER_CYCLE]:  # MAX = 20
            process_article(entry)                # requests.get SÍNCRONO
    except Exception as e:
        logger.error(...)
        continue
```

**Problemas fatais:**
1. **`selecionar_feeds_ciclo` só seleciona 60 feeds/ciclo** de 648+ — 90,7% das fontes são ignoradas a cada execução
2. **Fórmula de blocos é quebrada:** `bloco = (datetime.now().hour * 2 + datetime.now().minute // 30) % num_blocos` — feeds em blocos acima de `num_blocos` nunca são visitados se `total % FEEDS_POR_CICLO != 0`
3. **Loop `for feed in feeds_ciclo` é 100% sequencial** — se um feed leva 30s para timeout, os outros 59 esperam
4. **`MAX_ARTICLES_PER_CYCLE = 20`** — hard cap absurdo para 1.000+ artigos/dia (precisaria 50+ ciclos/dia só no RSS)
5. **`requests.get` síncrono** — cada HTTP GET bloqueia a thread inteira
6. **Sem ETag/If-Modified-Since** — redownloada 100% do conteúdo de cada feed a cada ciclo
7. **Cutoff fixo de 24h** — feeds governamentais que publicam com atraso perdem artigos
8. **Double fetch por artigo:** `extract_full_content(url)` + `extract_html_content(url)` = 2x download do mesmo HTML

### 1.3 Motor de Scrapers Semi-Paralelo (motor_scrapers_v2.py)

```python
# motor_scrapers_v2.py — PSEUDO-PARALELISMO (linhas 1065-1109)
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:  # MAX_WORKERS = 5
    futures = {}
    for fonte in fontes:
        # DELAY SÍNCRONO antes de submeter ao pool!
        elapsed = time.time() - domain_last_request.get(domain, 0)
        if elapsed < DOMAIN_DELAY_MIN:
            time.sleep(DOMAIN_DELAY_MIN - elapsed)  # BLOQUEIA O LOOP PRINCIPAL
        future = executor.submit(coletar_links_fonte, fonte)
        futures[future] = fonte
```

**Problemas fatais:**
1. **`ThreadPoolExecutor(max_workers=5)`** — apenas 5 threads para centenas de fontes scraper
2. **`time.sleep()` no loop de submissão** — o delay por domínio bloqueia a THREAD PRINCIPAL que submete tarefas ao pool, serializando o que deveria ser paralelo
3. **`cloudscraper.create_scraper()` dentro de `_fetch_with_retry`** — cria nova instância Cloudscraper a cada chamada (memory leak: sessions HTTP, certificados TLS, objetos JS)
4. **`MAX_ARTICLES_PER_CYCLE = 20`** e **`MAX_ARTICLES_PER_SOURCE = 10`** — caps idênticos ao motor RSS
5. **Sem Playwright** — sites JavaScript-heavy (SPAs, Next.js) dependem de extração heurística de `__NEXT_DATA__` que falha frequentemente
6. **`nest_asyncio` hack** em `scrapers_nativos.py` — wrapping de async em sync para contornar o event loop bloqueado
7. **Processamento de artigos SEQUENCIAL** após coleta: `for artigo in selected: processar_artigo(artigo)` — inclui chamada LLM + WordPress publish, um por um
8. **Sem Kafka** — escrita direta no MariaDB e publish direto no WordPress dentro do coletor

### 1.4 Deduplicação Frágil

```python
# motor_scrapers_v2.py — DEDUPLICAÇÃO (linhas 842-874)
def deduplicar_artigos(artigos):
    published_urls = db.get_published_urls_last_24h()  # SELECT sem LIMIT!
    published_normalized = {_normalizar_url(u) for u in published_urls}
    seen_urls = set()
    for artigo in artigos:
        url_norm = _normalizar_url(url)
        if url_norm in seen_urls or url_norm in published_normalized:
            continue
        if titulo and db.post_exists(url, titulo):  # QUERY SQL por artigo!
            continue
        seen_urls.add(url_norm)
        unique.append(artigo)
```

**Problemas fatais:**
1. **Apenas URL-based** — artigos com mesma matéria mas URLs diferentes (utm_params, www vs sem-www, http vs https) passam como "novos"
2. **`get_published_urls_last_24h` sem LIMIT** — com 1.000+ artigos/dia, carrega milhares de URLs em memória a cada ciclo
3. **`db.post_exists()` faz query SQL individual por artigo** — N+1 problem: 200 artigos = 200 queries SQL
4. **Sem hash de conteúdo** — dois artigos com títulos diferentes sobre a mesma notícia (rewrite de agência) passam ambos
5. **Sem SimHash** — near-duplicates (artigos que mudam 2-3 palavras) nunca são detectados
6. **Race condition entre Raia 1 e Raia 2** — padrão check-then-act não-atômico: ambas checam `post_exists`, ambas passam, ambas publicam
7. **Tabela `rss_control` sem índice UNIQUE em `source_url`** — o banco não impede inserções duplicadas

### 1.5 Bugs Críticos Adicionais (da Auditoria)

| Bug | Severidade | Impacto |
|-----|-----------|---------|
| `sys.path.insert(0, ...)` dentro de `process_article` — chamado por artigo, sys.path cresce infinitamente | CRÍTICO | Memory leak progressivo, crash do processo |
| `cloudscraper.create_scraper()` por chamada — sessões HTTP nunca liberadas | CRÍTICO | Crash do LightSail por OOM |
| Pool MariaDB `maxconnections=10` compartilhado entre 3 motores | CRÍTICO | 30 conexões simultâneas, esgota pool MariaDB |
| Circuit breaker do LLM não é thread-safe (`+=` não-atômico) | CRÍTICO | Contador de falhas subestimado, circuit breaker não dispara |
| `_key_index` do LLM round-robin não é thread-safe | CRÍTICO | Mesma key usada por múltiplas threads, outras nunca usadas |
| Cache de categorias/tags WP nunca expira | CRÍTICO | Categorias criadas no admin nunca aparecem, artigos vão para "Uncategorized" |
| `_request_with_retry` do WP ignora HTTP 429 (rate limit) | ALTO | Artigos falham silenciosamente sob carga |
| Slugs de categorias removem acentos do português (regex `[^a-z0-9]+`) | ALTO | Categorias duplicadas no WordPress |
| Gemini concatena system+user no `contents` em vez de `system_instruction` | ALTO | JSON malformado, mais retries, maior custo |
| `generate_article` trunca conteúdo em 6000 CHARS (não tokens/palavras) | ALTO | Contexto cortado no meio da frase |
| Cursor não fechado em exceção em `post_exists` | ALTO | Cursor leak sob carga |

### 1.6 O Que DEVE Mudar na V3

| V2 (Atual) | V3 (Alvo) | Razão |
|-------------|-----------|-------|
| 2 processos separados (RSS + Scrapers) | Worker Pool UNIFICADO com N workers independentes | Eliminação de race conditions, coordenação via Kafka |
| Sequencial (`for feed in feeds`) | Totalmente async (`asyncio` + `aiokafka`) | 648+ fontes processadas em paralelo por ciclo |
| `requests.get` síncrono | `httpx.AsyncClient` com connection pool | Centenas de conexões simultâneas sem bloqueio |
| Sem Playwright | Playwright headless para sites JS-heavy | SPAs, Next.js, infinite scroll |
| `feedparser.parse(url)` direto | `httpx` fetch com ETag → `feedparser.parse(content)` | Economia de banda, respeito a 304 Not Modified |
| MAX_ARTICLES = 20/ciclo | Sem cap — fluxo contínuo via Kafka | Throughput ilimitado, regulado por consumers downstream |
| Dedup só por URL (SQL) | 4 camadas: ETag + Redis SET + SHA-256 + SimHash | Near-duplicate detection, O(1) lookup |
| MariaDB direto | PostgreSQL + Redis + Kafka | Durabilidade, replay, multiple consumer groups |
| `ThreadPoolExecutor(5)` | 30-50 workers async independentes | Isolamento total, falha de 1 não afeta outros |
| Publish direto no WordPress | Produce para `raw-articles` Kafka topic | Desacoplamento: coletor NÃO sabe o que acontece depois |

---

## PARTE II — ARQUITETURA DO WORKER POOL V3

### 2.1 Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        WORKER POOL DE COLETORES V3                              │
│                                                                                 │
│  ┌─────────────┐     Kafka: fonte-assignments     ┌───────────────────────┐     │
│  │   FEED       │──────────────────────────────────▶│  WORKER POOL          │     │
│  │   SCHEDULER  │    (particionado por fonte_id)   │  (30-50 workers)      │     │
│  │              │                                   │                       │     │
│  │  - Carrega   │     ┌──────────────────────┐      │  Worker #1 (RSS)     │     │
│  │    648+ fontes│     │  Redis               │      │  Worker #2 (Scraper) │     │
│  │  - Prioriza   │     │  - dedup:urls SET    │      │  Worker #3 (RSS)     │     │
│  │    por tier   │     │  - source:etag:*     │      │  Worker #4 (Scraper) │     │
│  │  - Distribui  │     │  - source:health:*   │      │  ...                 │     │
│  │    round-robin│     └──────┬───────────────┘      │  Worker #50 (RSS)    │     │
│  └──────┬────────┘            │                      └──────────┬──────────┘     │
│         │                     │                                  │                │
│         │              ┌──────┴──────┐                           │                │
│         │              │ DEDUP LAYER │                           │                │
│         │              │ (4 camadas) │                           │                │
│         │              └──────┬──────┘                           │                │
│         │                     │                                  │                │
│         │                     ▼                                  │                │
│         │              Kafka: raw-articles ◀─────────────────────┘                │
│         │              (particionado por publisher_id)                            │
│         │                     │                                                   │
│         ▼                     ▼                                                   │
│  ┌─────────────┐     ┌──────────────────┐                                        │
│  │  HEALTH      │     │  CLASSIFICADOR   │  (consumer downstream — fora deste    │
│  │  TRACKER     │     │  (ML/LLM)        │   componente, aqui só para contexto)  │
│  │              │     └──────────────────┘                                        │
│  │  - Métricas  │                                                                │
│  │    por fonte │     ┌──────────────────────────────────────────────┐            │
│  │  - Adaptive  │     │  PostgreSQL                                  │            │
│  │    polling   │     │  - tabela `fontes` (648+ registros)         │            │
│  │  - Alertas   │     │  - tabela `artigos` (dedup SHA-256)        │            │
│  └─────────────┘     │  - tabela `coleta_metricas` (observabilidade)│            │
│                       └──────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Componentes Internos

O Worker Pool de Coletores V3 é composto por **6 módulos** dentro de `brasileira/ingestion/`:

| Módulo | Arquivo | Responsabilidade |
|--------|---------|-----------------|
| **FeedScheduler** | `scheduler.py` | Carrega fontes de PostgreSQL, prioriza por tier, distribui via Kafka `fonte-assignments` |
| **WorkerPool** | `worker_pool.py` | Gerencia N workers async, spawn/kill, health monitoring |
| **RSSCollector** | `collectors/rss_collector.py` | Processa feeds RSS/Atom com feedparser + HTTPX + ETag |
| **ScraperCollector** | `collectors/scraper_collector.py` | Processa sites via HTTPX (estático) ou Playwright (JS-heavy) |
| **DeduplicationEngine** | `dedup.py` | 4 camadas de deduplicação: ETag → Redis URL → SHA-256 → SimHash |
| **SourceHealthTracker** | `health.py` | Métricas por fonte, adaptive polling, alertas |

### 2.3 Fluxo de Dados Completo

```
1. FeedScheduler.schedule_cycle()
   │
   ├── Carrega todas as fontes de PostgreSQL (tabela `fontes`)
   ├── Ordena por tier: VIP > padrão > secundário
   ├── Para cada fonte: produce mensagem para Kafka `fonte-assignments`
   │   Mensagem: { fonte_id, nome, tipo, url, config_scraper, tier, polling_interval }
   │
   └── Após timeout do ciclo: verifica não-processadas → re-envia com prioridade HIGH

2. WorkerPool (30-50 workers, cada um consome de `fonte-assignments`)
   │
   ├── Worker recebe assignment do Kafka
   ├── Determina tipo: RSS → RSSCollector, Scraper → ScraperCollector
   ├── Executa coleta com timeout (15s RSS, 30s HTTP scraper, 60s Playwright)
   ├── Para cada artigo coletado:
   │   ├── DeduplicationEngine.check_all_layers(artigo)
   │   │   ├── Camada 1: ETag/304 (já aplicada no fetch)
   │   │   ├── Camada 2: Redis SET `dedup:urls` (O(1))
   │   │   ├── Camada 3: SHA-256 hash em PostgreSQL
   │   │   └── Camada 4: SimHash LSH (near-duplicate)
   │   │
   │   └── Se novo → produce para Kafka `raw-articles`
   │       Mensagem: { titulo, url, url_fonte, conteudo_resumo, data_publicacao,
   │                    og_image, fonte_id, fonte_nome, grupo_editorial, score_preliminar }
   │
   └── SourceHealthTracker.record_result(fonte_id, success/fail, latency)

3. Kafka `raw-articles` → Consumido pelo Classificador (FORA deste componente)
```

---

## PARTE III — ESPECIFICAÇÃO: FEED SCHEDULER

### 3.1 Responsabilidade

O FeedScheduler é o **orquestrador** que decide QUANDO e EM QUE ORDEM as fontes são processadas. Ele NÃO processa fontes diretamente — apenas distribui assignments via Kafka para os workers.

### 3.2 Implementação OBRIGATÓRIA

```python
# brasileira/ingestion/scheduler.py
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from aiokafka import AIOKafkaProducer
from brasileira.ingestion.health import SourceHealthTracker
from brasileira.db.postgres import get_async_pool

TOPIC_ASSIGNMENTS = "fonte-assignments"
CYCLE_TIMEOUT_SECONDS = 900  # 15 minutos por ciclo
DEFAULT_CYCLE_INTERVAL = 1800  # 30 minutos entre ciclos

class FeedScheduler:
    """
    Distribui TODAS as fontes para os workers a cada ciclo.
    
    Princípios:
    1. TODAS as 648+ fontes são processadas a cada ciclo — sem caps, sem blocos
    2. Fontes VIP primeiro (governo, reguladores, grandes portais)
    3. Adaptive polling: fontes que falham recebem backoff, mas NUNCA são desativadas
    4. Fontes não-processadas no timeout são re-enviadas com prioridade HIGH
    """

    def __init__(
        self,
        kafka_bootstrap: str,
        db_pool,  # asyncpg pool
        health_tracker: SourceHealthTracker,
        cycle_interval: int = DEFAULT_CYCLE_INTERVAL,
    ):
        self.kafka_bootstrap = kafka_bootstrap
        self.db_pool = db_pool
        self.health_tracker = health_tracker
        self.cycle_interval = cycle_interval
        self.producer: Optional[AIOKafkaProducer] = None
        self._running = True
        # Tracking de quais fontes foram processadas neste ciclo
        self._cycle_processed: set[int] = set()
        self._cycle_total: int = 0

    async def start(self):
        """Inicializa producer Kafka e inicia loop de scheduling."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            compression_type="lz4",
            linger_ms=10,
            batch_size=32768,
            acks=1,
        )
        await self.producer.start()

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        if self.producer:
            await self.producer.stop()

    async def load_all_sources(self) -> list[dict]:
        """
        Carrega TODAS as fontes ativas do PostgreSQL.
        NUNCA filtra por número — todas as fontes são processadas.
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    id, nome, url, tipo, tier,
                    config_scraper, polling_interval_min,
                    ultimo_sucesso, ultimo_erro, ativa
                FROM fontes
                WHERE ativa = TRUE
                ORDER BY 
                    CASE tier 
                        WHEN 'vip' THEN 1 
                        WHEN 'padrao' THEN 2 
                        WHEN 'secundario' THEN 3 
                        ELSE 4 
                    END,
                    ultimo_sucesso ASC NULLS FIRST  -- Fontes nunca processadas têm prioridade
            """)
        return [dict(row) for row in rows]

    def _should_process_source(self, source: dict) -> bool:
        """
        Verifica se a fonte deve ser processada neste ciclo com base no 
        polling_interval adaptativo. Fontes VIP sempre são processadas.
        """
        if source["tier"] == "vip":
            return True  # VIP = sempre processa

        if source["ultimo_sucesso"] is None:
            return True  # Nunca processada = processa agora

        health = self.health_tracker.get_source_health(source["id"])
        
        # Backoff adaptativo baseado em saúde
        interval = source.get("polling_interval_min", 30)
        if health and health.consecutive_failures > 0:
            # Backoff exponencial: 30min, 60min, 120min, max 360min
            backoff_factor = min(2 ** health.consecutive_failures, 12)
            interval = min(interval * backoff_factor, 360)

        last_success = source["ultimo_sucesso"]
        elapsed = (datetime.now(timezone.utc) - last_success).total_seconds() / 60
        return elapsed >= interval

    async def schedule_cycle(self):
        """
        Executa UM ciclo completo de scheduling:
        1. Carrega todas as fontes
        2. Filtra por polling interval
        3. Envia assignments via Kafka
        4. Espera timeout
        5. Re-envia fontes não processadas
        """
        sources = await self.load_all_sources()
        to_process = [s for s in sources if self._should_process_source(s)]
        
        self._cycle_processed = set()
        self._cycle_total = len(to_process)

        for source in to_process:
            if not self._running:
                break
            
            assignment = {
                "fonte_id": source["id"],
                "nome": source["nome"],
                "url": source["url"],
                "tipo": source["tipo"],  # 'rss' ou 'scraper'
                "tier": source["tier"],
                "config_scraper": source.get("config_scraper"),
                "polling_interval_min": source.get("polling_interval_min", 30),
                "priority": "high" if source["tier"] == "vip" else "normal",
                "scheduled_at": datetime.now(timezone.utc).isoformat(),
            }
            
            await self.producer.send(
                TOPIC_ASSIGNMENTS,
                key=str(source["id"]),
                value=assignment,
            )

        # Espera timeout do ciclo, depois verifica não-processadas
        await asyncio.sleep(CYCLE_TIMEOUT_SECONDS)
        await self._reschedule_missed()

    async def _reschedule_missed(self):
        """Re-envia fontes que não foram processadas dentro do timeout."""
        all_ids = set(range(self._cycle_total))  # simplificado
        missed = all_ids - self._cycle_processed
        
        if missed:
            # Busca dados completos das fontes perdidas
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM fontes WHERE id = ANY($1)", list(missed)
                )
            for row in rows:
                source = dict(row)
                assignment = {
                    "fonte_id": source["id"],
                    "nome": source["nome"],
                    "url": source["url"],
                    "tipo": source["tipo"],
                    "tier": source["tier"],
                    "config_scraper": source.get("config_scraper"),
                    "polling_interval_min": source.get("polling_interval_min", 30),
                    "priority": "high",  # Re-scheduled = alta prioridade
                    "scheduled_at": datetime.now(timezone.utc).isoformat(),
                    "retry": True,
                }
                await self.producer.send(
                    TOPIC_ASSIGNMENTS,
                    key=str(source["id"]),
                    value=assignment,
                )

    def mark_processed(self, fonte_id: int):
        """Chamado pelo WorkerPool quando um worker completa uma fonte."""
        self._cycle_processed.add(fonte_id)

    async def run_forever(self):
        """Loop principal do scheduler."""
        await self.start()
        while self._running:
            try:
                await self.schedule_cycle()
                await asyncio.sleep(self.cycle_interval - CYCLE_TIMEOUT_SECONDS)
            except Exception as e:
                # Scheduler NUNCA morre — loga erro e continua
                import logging
                logging.getLogger(__name__).error(
                    "Erro no ciclo do scheduler: %s", e, exc_info=True
                )
                await asyncio.sleep(60)  # espera 1 min antes de retry
```

### 3.3 Princípios do Scheduler

1. **TODAS as fontes são processadas** — sem blocos rotativos, sem caps. Se uma fonte está ativa, ela entra no ciclo.
2. **Adaptive polling via backoff** — fontes que falham aumentam seu intervalo, mas NUNCA são desativadas. Voltam ao normal após sucesso.
3. **VIP sempre processadas** — fontes tier "vip" (governo, reguladores, grandes portais) ignoram o polling interval e são processadas a cada ciclo.
4. **Re-scheduling de perdidas** — após o timeout do ciclo, fontes que não foram processadas por nenhum worker são re-enviadas com prioridade alta.
5. **Desacoplamento total** — o scheduler não sabe quantos workers existem. Se há 10 ou 50, funciona igual. Kafka faz o balanceamento.

---

## PARTE IV — ESPECIFICAÇÃO: WORKER POOL

### 4.1 Responsabilidade

O WorkerPool gerencia N workers async independentes. Cada worker é um consumer Kafka que processa uma fonte por vez, isolado dos demais. Se um worker trava, os outros continuam.

### 4.2 Implementação OBRIGATÓRIA

```python
# brasileira/ingestion/worker_pool.py
import asyncio
import json
import logging
import signal
from typing import Optional
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from brasileira.ingestion.collectors.rss_collector import RSSCollector
from brasileira.ingestion.collectors.scraper_collector import ScraperCollector
from brasileira.ingestion.dedup import DeduplicationEngine
from brasileira.ingestion.health import SourceHealthTracker

logger = logging.getLogger(__name__)

TOPIC_ASSIGNMENTS = "fonte-assignments"
TOPIC_RAW_ARTICLES = "raw-articles"
CONSUMER_GROUP = "ingestion-workers"
DEFAULT_NUM_WORKERS = 30

class WorkerPool:
    """
    Pool de workers de coleta. Cada worker é uma coroutine asyncio independente
    que consome de Kafka, processa fontes, e produz raw-articles.
    
    Princípios:
    1. Cada worker é INDEPENDENTE — crash de #3 não afeta #1,#2,#4...#50
    2. Workers NÃO fazem processamento LLM — apenas COLETAM e DEDUPLICAM
    3. Resultado vai para Kafka `raw-articles` — desacoplamento total
    4. Falhas são logadas e a fonte é marcada para retry — NUNCA para o worker
    """

    def __init__(
        self,
        kafka_bootstrap: str,
        num_workers: int = DEFAULT_NUM_WORKERS,
        db_pool=None,  # asyncpg
        redis_client=None,  # aioredis
    ):
        self.kafka_bootstrap = kafka_bootstrap
        self.num_workers = num_workers
        self.db_pool = db_pool
        self.redis_client = redis_client
        
        # Componentes compartilhados (thread-safe / async-safe)
        self.dedup = DeduplicationEngine(redis_client=redis_client, db_pool=db_pool)
        self.health_tracker = SourceHealthTracker(redis_client=redis_client, db_pool=db_pool)
        self.rss_collector = RSSCollector(redis_client=redis_client)
        self.scraper_collector = ScraperCollector()
        
        self.producer: Optional[AIOKafkaProducer] = None
        self._workers: list[asyncio.Task] = []
        self._running = True
        self._stats = {
            "articles_collected": 0,
            "articles_deduped": 0,
            "sources_processed": 0,
            "sources_failed": 0,
        }

    async def start(self):
        """Inicializa producer Kafka, coletores e inicia workers."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            compression_type="lz4",
            linger_ms=10,
            batch_size=32768,
            acks=1,
        )
        await self.producer.start()
        await self.scraper_collector.start()  # Inicializa Playwright browser
        
        # Spawn workers
        for i in range(self.num_workers):
            task = asyncio.create_task(
                self._worker_loop(worker_id=f"worker-{i:03d}"),
                name=f"ingestion-worker-{i:03d}",
            )
            self._workers.append(task)
        
        logger.info(
            "WorkerPool iniciado: %d workers, kafka=%s",
            self.num_workers, self.kafka_bootstrap,
        )

    async def stop(self):
        """Graceful shutdown de todos os workers."""
        self._running = False
        
        # Cancela todos os workers
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        
        # Cleanup
        await self.scraper_collector.stop()
        if self.producer:
            await self.producer.stop()
        
        logger.info(
            "WorkerPool encerrado. Stats: %s", self._stats
        )

    async def _worker_loop(self, worker_id: str):
        """
        Loop infinito de um worker individual.
        
        NUNCA para. NUNCA bloqueia outros workers.
        Cada iteração: consume assignment → coleta → dedup → produce.
        """
        consumer = AIOKafkaConsumer(
            TOPIC_ASSIGNMENTS,
            bootstrap_servers=self.kafka_bootstrap,
            group_id=CONSUMER_GROUP,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
            auto_commit_interval_ms=5000,
            max_poll_records=1,  # Um assignment por vez por worker
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
        )
        await consumer.start()
        
        logger.info("[%s] Worker iniciado, consumindo de %s", worker_id, TOPIC_ASSIGNMENTS)
        
        try:
            async for msg in consumer:
                if not self._running:
                    break
                
                assignment = msg.value
                fonte_id = assignment["fonte_id"]
                fonte_nome = assignment.get("nome", "desconhecido")
                fonte_tipo = assignment.get("tipo", "rss")
                
                try:
                    articles = await self._process_source(
                        worker_id=worker_id,
                        assignment=assignment,
                    )
                    
                    # Dedup e produce para raw-articles
                    new_articles = 0
                    for article in articles:
                        is_new = await self.dedup.check_and_register(article)
                        if is_new:
                            await self.producer.send(
                                TOPIC_RAW_ARTICLES,
                                key=str(fonte_id),
                                value=article,
                            )
                            new_articles += 1
                            self._stats["articles_collected"] += 1
                        else:
                            self._stats["articles_deduped"] += 1
                    
                    self._stats["sources_processed"] += 1
                    self.health_tracker.record_success(fonte_id)
                    
                    logger.info(
                        "[%s] fonte=%s | coletados=%d | novos=%d | deduplicados=%d",
                        worker_id, fonte_nome, len(articles), new_articles,
                        len(articles) - new_articles,
                    )
                    
                except asyncio.TimeoutError:
                    self._stats["sources_failed"] += 1
                    self.health_tracker.record_failure(fonte_id, "timeout")
                    logger.warning(
                        "[%s] TIMEOUT em fonte=%s (%s)",
                        worker_id, fonte_nome, assignment.get("url", "")[:80],
                    )
                
                except Exception as e:
                    self._stats["sources_failed"] += 1
                    self.health_tracker.record_failure(fonte_id, str(type(e).__name__))
                    logger.error(
                        "[%s] ERRO em fonte=%s: %s",
                        worker_id, fonte_nome, e, exc_info=True,
                    )
                    # Worker NÃO morre — continua para a próxima fonte
                    continue
        
        except asyncio.CancelledError:
            logger.info("[%s] Worker cancelado (shutdown)", worker_id)
        finally:
            await consumer.stop()

    async def _process_source(
        self, worker_id: str, assignment: dict
    ) -> list[dict]:
        """
        Processa uma fonte individual. Determina tipo e delega para o coletor adequado.
        Timeout enforced por tipo de fonte.
        """
        fonte_tipo = assignment.get("tipo", "rss")
        
        if fonte_tipo == "rss":
            timeout = 15  # 15 segundos para RSS
            collector_coro = self.rss_collector.collect(
                feed_url=assignment["url"],
                fonte_id=assignment["fonte_id"],
                fonte_nome=assignment.get("nome", ""),
                grupo=assignment.get("config_scraper", {}).get("grupo", ""),
            )
        elif fonte_tipo == "scraper":
            config = assignment.get("config_scraper") or {}
            needs_js = config.get("needs_javascript", False)
            timeout = 60 if needs_js else 30  # 60s Playwright, 30s HTTP
            collector_coro = self.scraper_collector.collect(
                source_config=assignment,
            )
        else:
            logger.warning("[%s] Tipo de fonte desconhecido: %s", worker_id, fonte_tipo)
            return []
        
        # Timeout enforced — NUNCA deixa um coletor travar o worker indefinidamente
        articles = await asyncio.wait_for(collector_coro, timeout=timeout)
        return articles or []
```

### 4.3 Princípios do Worker Pool

1. **Cada worker é uma coroutine independente** — não compartilha estado mutável com outros workers (exceto componentes async-safe: dedup, health tracker, producer)
2. **Workers NÃO fazem processamento LLM** — apenas coletam, deduplicam e produzem para Kafka. O processamento editorial (reescrita, SEO, imagem) é responsabilidade de componentes downstream (Reporter, Fotógrafo, etc.)
3. **Timeout obrigatório** — cada coleta tem timeout: 15s RSS, 30s HTTP scraper, 60s Playwright. NUNCA um coletor trava o worker
4. **Sem hard caps** — não existe `MAX_ARTICLES_PER_CYCLE`. O fluxo é contínuo. O Kafka e os consumers downstream regulam a vazão
5. **Consumer group Kafka** — todos os workers compartilham o mesmo `group_id`. Kafka distribui partições automaticamente. Se um worker morre, Kafka rebalanceia para os demais
6. **Graceful shutdown** — workers respondem a sinais SIGTERM/SIGINT, terminam o artigo atual e encerram limpamente

---

## PARTE V — ESPECIFICAÇÃO: COLETOR RSS

### 5.1 Responsabilidade

Processa feeds RSS/Atom. Stateless. Para cada feed, retorna uma lista de artigos novos com metadados básicos.

### 5.2 Implementação OBRIGATÓRIA

```python
# brasileira/ingestion/collectors/rss_collector.py
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse, urljoin
import feedparser
import httpx

logger = logging.getLogger(__name__)

# Timeouts para fetch HTTP de feeds
FEED_FETCH_TIMEOUT = 12.0  # segundos
# Janela de tempo para considerar artigos (configurável por fonte)
DEFAULT_CUTOFF_HOURS = 48
# User-Agent respeitoso
USER_AGENT = "BrasileiraNewsBot/3.0 (+https://brasileira.news/bot)"

class RSSCollector:
    """
    Coletor de feeds RSS/Atom com:
    - ETag / If-Modified-Since para economia de banda
    - feedparser para parsing robusto de XML
    - HTTPX async para fetch non-blocking
    - Sem hard caps — retorna TODOS os artigos novos do feed
    """

    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Retorna client HTTPX com connection pool reutilizável."""
        if self.http_client is None or self.http_client.is_closed:
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(FEED_FETCH_TIMEOUT),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=50,
                ),
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                http2=True,  # HTTP/2 quando disponível
            )
        return self.http_client

    async def _get_cached_etag(self, fonte_id: int) -> tuple[Optional[str], Optional[str]]:
        """
        Recupera ETag e Last-Modified do Redis para esta fonte.
        Retorna (etag, last_modified) ou (None, None).
        """
        if not self.redis_client:
            return None, None
        
        etag = await self.redis_client.get(f"source:etag:{fonte_id}")
        last_modified = await self.redis_client.get(f"source:last_modified:{fonte_id}")
        
        return (
            etag.decode("utf-8") if etag else None,
            last_modified.decode("utf-8") if last_modified else None,
        )

    async def _store_etag(
        self, fonte_id: int, etag: Optional[str], last_modified: Optional[str]
    ):
        """Armazena ETag e Last-Modified no Redis com TTL de 24h."""
        if not self.redis_client:
            return
        
        if etag:
            await self.redis_client.set(
                f"source:etag:{fonte_id}", etag, ex=86400  # 24h
            )
        if last_modified:
            await self.redis_client.set(
                f"source:last_modified:{fonte_id}", last_modified, ex=86400
            )

    async def collect(
        self,
        feed_url: str,
        fonte_id: int,
        fonte_nome: str = "",
        grupo: str = "",
        cutoff_hours: int = DEFAULT_CUTOFF_HOURS,
    ) -> list[dict]:
        """
        Coleta artigos de um feed RSS/Atom.
        
        Fluxo:
        1. Busca ETag/Last-Modified do Redis
        2. Faz GET com If-None-Match / If-Modified-Since
        3. Se 304 Not Modified → retorna []
        4. Se 200 → parse com feedparser → extrai artigos
        5. Armazena novo ETag/Last-Modified no Redis
        
        Retorna lista de dicts com:
        { titulo, url, data_publicacao, resumo, og_image, fonte_id, fonte_nome, grupo }
        """
        client = await self._get_http_client()
        
        # 1. Headers condicionais
        headers = {}
        cached_etag, cached_last_modified = await self._get_cached_etag(fonte_id)
        if cached_etag:
            headers["If-None-Match"] = cached_etag
        if cached_last_modified:
            headers["If-Modified-Since"] = cached_last_modified
        
        # 2. Fetch
        try:
            response = await client.get(feed_url, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as e:
            logger.warning(
                "RSS fetch falhou para %s (%s): %s",
                fonte_nome, feed_url[:80], e,
            )
            return []

        # 3. 304 Not Modified — feed não mudou
        if response.status_code == 304:
            logger.debug("RSS 304 Not Modified: %s", fonte_nome)
            return []
        
        if response.status_code >= 400:
            logger.warning(
                "RSS HTTP %d para %s (%s)",
                response.status_code, fonte_nome, feed_url[:80],
            )
            return []

        # 4. Armazena novos ETags
        new_etag = response.headers.get("ETag")
        new_last_modified = response.headers.get("Last-Modified")
        await self._store_etag(fonte_id, new_etag, new_last_modified)

        # 5. Parse com feedparser
        content = response.text
        parsed = feedparser.parse(content)
        
        if parsed.bozo and not parsed.entries:
            logger.warning(
                "RSS parse error para %s: %s",
                fonte_nome, getattr(parsed, "bozo_exception", "unknown"),
            )
            return []
        
        # 6. Extrair artigos
        cutoff = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)
        articles = []
        
        for entry in parsed.entries:
            article = self._parse_entry(
                entry=entry,
                feed_url=feed_url,
                fonte_id=fonte_id,
                fonte_nome=fonte_nome,
                grupo=grupo,
                cutoff=cutoff,
            )
            if article:
                articles.append(article)
        
        logger.info(
            "RSS coletado: %s | entries=%d | artigos_validos=%d",
            fonte_nome, len(parsed.entries), len(articles),
        )
        return articles

    def _parse_entry(
        self,
        entry,
        feed_url: str,
        fonte_id: int,
        fonte_nome: str,
        grupo: str,
        cutoff: datetime,
    ) -> Optional[dict]:
        """Parse de uma entry individual do feedparser."""
        titulo = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        
        if not titulo or not link or len(titulo) < 10:
            return None
        
        # Normalizar URL
        if not link.startswith("http"):
            link = urljoin(feed_url, link)
        
        # Data de publicação
        data_publicacao = None
        for date_field in ("published_parsed", "updated_parsed", "created_parsed"):
            parsed_time = entry.get(date_field)
            if parsed_time:
                try:
                    from calendar import timegm
                    timestamp = timegm(parsed_time)
                    data_publicacao = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    break
                except (ValueError, OverflowError):
                    continue
        
        # Filtro de cutoff (se temos data)
        if data_publicacao and data_publicacao < cutoff:
            return None
        
        # Resumo
        resumo = ""
        if entry.get("summary"):
            from html import unescape
            resumo = unescape(entry.summary)
            # Strip HTML tags básico
            import re
            resumo = re.sub(r"<[^>]+>", "", resumo).strip()[:500]
        
        # og:image via enclosures ou media:content
        og_image = ""
        if entry.get("media_content"):
            for media in entry.media_content:
                if media.get("medium") == "image" or (
                    media.get("type", "").startswith("image/")
                ):
                    og_image = media.get("url", "")
                    break
        elif entry.get("media_thumbnail"):
            og_image = entry.media_thumbnail[0].get("url", "")
        elif entry.get("enclosures"):
            for enc in entry.enclosures:
                if enc.get("type", "").startswith("image/"):
                    og_image = enc.get("href", "")
                    break
        
        # Hash para deduplicação downstream
        url_hash = hashlib.sha256(link.encode("utf-8")).hexdigest()
        
        return {
            "titulo": titulo,
            "url": link,
            "url_hash": url_hash,
            "data_publicacao": data_publicacao.isoformat() if data_publicacao else None,
            "resumo": resumo,
            "og_image": og_image,
            "fonte_id": fonte_id,
            "fonte_nome": fonte_nome,
            "grupo": grupo,
            "tipo_coleta": "rss",
            "coletado_em": datetime.now(timezone.utc).isoformat(),
        }

    async def close(self):
        """Fecha o client HTTP."""
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
```

### 5.3 Diferenças Críticas vs V2

| Aspecto | V2 | V3 |
|---------|-----|-----|
| HTTP fetch | `feedparser.parse(url)` direto (síncrono, sem headers) | HTTPX async com ETag/If-Modified-Since |
| Parsing | feedparser faz fetch + parse juntos | HTTPX faz fetch → feedparser parseia conteúdo já baixado |
| Connection pool | Nova conexão por feed | `httpx.AsyncClient` com pool de 100 conexões |
| Cutoff | 24h fixo para todos | 48h default, configurável por fonte |
| Caps | MAX_ARTICLES_PER_SOURCE = 10, MAX_ARTICLES_PER_CYCLE = 20 | Sem caps — todos os artigos válidos são retornados |
| Imagem | Não extrai do feed | Extrai de `media:content`, `media:thumbnail`, `enclosures` |
| ETag caching | Inexistente | Redis com TTL 24h |

---

## PARTE VI — ESPECIFICAÇÃO: COLETOR SCRAPER

### 6.1 Responsabilidade

Processa sites que NÃO oferecem feeds RSS adequados. Usa HTTPX para sites estáticos e Playwright headless para sites JavaScript-heavy (SPAs, Next.js, React, infinite scroll).

### 6.2 Decisão HTTP vs Playwright

```
                    ┌─ config_scraper.needs_javascript == true ─── Playwright
                    │
Fonte chega ────────┤
                    │
                    └─ config_scraper.needs_javascript == false ── HTTPX
                         (default)
```

**Regra:** O campo `needs_javascript` na tabela `fontes.config_scraper` (JSONB) determina o método. Fontes que usam client-side rendering (React, Next.js, Vue, Angular, infinite scroll, lazy loading) devem ter `needs_javascript: true`. A decisão é feita na configuração da fonte, NÃO em runtime com auto-detecção (auto-detecção é frágil e lenta).

### 6.3 Implementação OBRIGATÓRIA

```python
# brasileira/ingestion/collectors/scraper_collector.py
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

USER_AGENT = "BrasileiraNewsBot/3.0 (+https://brasileira.news/bot)"

# Playwright config
PLAYWRIGHT_MAX_CONTEXTS = 5  # Limite de contextos simultâneos (RAM ~1-2GB cada)
PLAYWRIGHT_PAGE_TIMEOUT = 45_000  # 45s timeout para navegação
PLAYWRIGHT_IDLE_TIMEOUT = 5_000  # 5s após network idle

# HTTP config
HTTP_TIMEOUT = 20.0  # 20 segundos
HTTP_MAX_CONNECTIONS = 50

# Seletores fallback quando config_scraper não define seletores
FALLBACK_SELECTORS = [
    ("article h2 a", "article h3 a"),
    (".news-list a", ".news-item a"),
    (".noticias h2 a", ".noticias h3 a"),
    (".lista-noticias a", ".lista-noticias h2"),
    ("main h2 a", "main h3 a"),
    ('[class*="noticia"] a', '[class*="news"] a'),
]


class ScraperCollector:
    """
    Coletor de sites via scraping. Duas estratégias:
    
    1. HTTPX (sites estáticos/SSR) — rápido, baixo recurso
    2. Playwright (sites JS-heavy/SPA) — renderiza JavaScript, mais lento
    
    Cada fonte tem config_scraper (JSONB) com:
    - needs_javascript: bool
    - seletor_lista: str (CSS selector para lista de artigos)
    - seletor_titulo: str (CSS selector para título)
    - seletor_link: str (CSS selector para link)
    - seletor_data: str (CSS selector para data)
    - seletor_imagem: str (CSS selector para imagem)
    - url_noticias: str (URL da página de notícias)
    - estrategia: str (html|nextjs|api_json|feed|sitemap)
    """

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context_semaphore = asyncio.Semaphore(PLAYWRIGHT_MAX_CONTEXTS)
        self.http_client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Inicializa Playwright browser (reutilizado por todos os workers)."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",  # Evita crash em containers com pouca shared memory
                "--disable-gpu",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                "--disable-translate",
                "--metrics-recording-only",
                "--mute-audio",
                "--no-first-run",
                "--safebrowsing-disable-auto-update",
            ],
        )
        
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(HTTP_TIMEOUT),
            limits=httpx.Limits(
                max_connections=HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=30,
            ),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            http2=True,
        )
        
        logger.info(
            "ScraperCollector iniciado: Playwright browser + HTTPX client"
        )

    async def stop(self):
        """Fecha browser e HTTP client."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()

    async def collect(self, source_config: dict) -> list[dict]:
        """
        Ponto de entrada principal. Determina estratégia e coleta artigos.
        
        Retorna lista de dicts com:
        { titulo, url, url_hash, data_publicacao, resumo, og_image,
          fonte_id, fonte_nome, grupo, tipo_coleta, coletado_em }
        """
        config = source_config.get("config_scraper") or {}
        needs_js = config.get("needs_javascript", False)
        url = config.get("url_noticias") or source_config.get("url", "")
        
        if not url:
            logger.warning("Fonte sem URL: %s", source_config.get("nome", "?"))
            return []
        
        estrategia = config.get("estrategia", "html")
        
        # Estratégias especiais que não dependem de JS
        if estrategia == "api_json":
            return await self._collect_api_json(source_config, config)
        elif estrategia == "feed":
            # Redireciona para RSSCollector (não deveria chegar aqui, mas safety net)
            logger.info("Fonte %s tem estrategia=feed, delegando", source_config.get("nome"))
            return []
        elif estrategia == "sitemap":
            return await self._collect_sitemap(source_config, config)
        
        # HTML/NextJS: decisão entre HTTPX e Playwright
        if needs_js:
            html = await self._fetch_with_playwright(url)
        else:
            html = await self._fetch_with_httpx(url)
        
        if not html:
            return []
        
        # Parse do HTML
        if estrategia == "nextjs":
            articles = self._extract_nextjs(source_config, config, html)
        else:
            articles = self._extract_html(source_config, config, html)
        
        return articles

    async def _fetch_with_httpx(self, url: str) -> Optional[str]:
        """Fetch HTTP simples para sites estáticos/SSR."""
        try:
            response = await self.http_client.get(url)
            if response.status_code >= 400:
                logger.warning("HTTP %d para %s", response.status_code, url[:80])
                return None
            return response.text
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as e:
            logger.warning("HTTPX erro para %s: %s", url[:80], e)
            return None

    async def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """
        Fetch com Playwright para sites JavaScript-heavy.
        
        Usa semáforo para limitar contextos simultâneos (RAM).
        Cada fetch cria um contexto ISOLADO (cookies, storage separados).
        """
        if not self._browser:
            logger.error("Playwright browser não inicializado")
            return None
        
        async with self._context_semaphore:
            context: Optional[BrowserContext] = None
            page: Optional[Page] = None
            try:
                context = await self._browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 720},
                    java_script_enabled=True,
                    # Bloqueia recursos pesados desnecessários
                    # (route interceptor abaixo)
                )
                page = await context.new_page()
                
                # Interceptar e bloquear recursos pesados
                await page.route(
                    "**/*",
                    lambda route: (
                        route.abort()
                        if route.request.resource_type in ("image", "font", "media", "stylesheet")
                        else route.continue_()
                    ),
                )
                
                await page.goto(
                    url,
                    timeout=PLAYWRIGHT_PAGE_TIMEOUT,
                    wait_until="domcontentloaded",
                )
                
                # Espera network idle (max 5s adicional)
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=PLAYWRIGHT_IDLE_TIMEOUT
                    )
                except Exception:
                    pass  # Timeout de idle é aceitável — content já carregou
                
                html = await page.content()
                return html
                
            except Exception as e:
                logger.warning("Playwright erro para %s: %s", url[:80], e)
                return None
            finally:
                if page:
                    await page.close()
                if context:
                    await context.close()

    def _extract_html(
        self, source_config: dict, config: dict, html: str
    ) -> list[dict]:
        """
        Extrai artigos de HTML usando seletores CSS da config_scraper.
        Fallback para seletores genéricos se não configurado.
        """
        soup = BeautifulSoup(html, "html.parser")
        url_base = config.get("url_noticias") or source_config.get("url", "")
        fonte_id = source_config.get("fonte_id", 0)
        fonte_nome = source_config.get("nome", "")
        grupo = config.get("grupo", "")
        
        # Seletores da config ou fallback
        seletor_lista = config.get("seletor_lista", "")
        seletor_titulo = config.get("seletor_titulo", "")
        seletor_link = config.get("seletor_link", "")
        seletor_data = config.get("seletor_data", "")
        seletor_imagem = config.get("seletor_imagem", "")
        
        # Busca items usando seletores configurados
        items = []
        if seletor_lista:
            for sel in seletor_lista.split(","):
                sel = sel.strip()
                if sel:
                    items = soup.select(sel)
                    if items:
                        break
        
        # Fallback para seletores genéricos
        if not items:
            for fallback_pair in FALLBACK_SELECTORS:
                for sel in fallback_pair:
                    items = soup.select(sel)
                    if items:
                        break
                if items:
                    break
        
        if not items:
            logger.warning("Nenhum item encontrado para %s", fonte_nome)
            return []
        
        articles = []
        for item in items:
            article = self._parse_html_item(
                item=item,
                url_base=url_base,
                fonte_id=fonte_id,
                fonte_nome=fonte_nome,
                grupo=grupo,
                seletor_titulo=seletor_titulo,
                seletor_link=seletor_link,
                seletor_data=seletor_data,
                seletor_imagem=seletor_imagem,
            )
            if article:
                articles.append(article)
        
        return articles

    def _parse_html_item(
        self,
        item,
        url_base: str,
        fonte_id: int,
        fonte_nome: str,
        grupo: str,
        seletor_titulo: str,
        seletor_link: str,
        seletor_data: str,
        seletor_imagem: str,
    ) -> Optional[dict]:
        """Parse de um item HTML individual."""
        # Link
        link_el = None
        if seletor_link:
            for sel in seletor_link.split(","):
                sel = sel.strip()
                if sel:
                    link_el = item.select_one(sel)
                    if link_el:
                        break
        if not link_el:
            link_el = item if item.name == "a" else item.find("a")
        if not link_el:
            return None
        
        url = link_el.get("href", "")
        if not url:
            return None
        url = urljoin(url_base, url)
        
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return None
        
        # Título
        titulo = ""
        if seletor_titulo:
            for sel in seletor_titulo.split(","):
                sel = sel.strip()
                if sel:
                    titulo_el = item.select_one(sel)
                    if titulo_el:
                        titulo = titulo_el.get_text(strip=True)
                        break
        if not titulo:
            titulo = link_el.get_text(strip=True)
        
        if not titulo or len(titulo) < 10:
            return None
        
        # Data
        data_str = ""
        if seletor_data:
            for sel in seletor_data.split(","):
                sel = sel.strip()
                if sel:
                    data_el = item.select_one(sel)
                    if data_el:
                        data_str = data_el.get("datetime", "") or data_el.get_text(strip=True)
                        break
        
        # Imagem
        og_image = ""
        if seletor_imagem:
            for sel in seletor_imagem.split(","):
                sel = sel.strip()
                if sel:
                    img_el = item.select_one(sel)
                    if img_el:
                        og_image = img_el.get("src", "") or img_el.get("data-src", "")
                        if og_image:
                            og_image = urljoin(url_base, og_image)
                        break
        
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        
        return {
            "titulo": titulo,
            "url": url,
            "url_hash": url_hash,
            "data_publicacao": data_str or None,
            "resumo": "",
            "og_image": og_image,
            "fonte_id": fonte_id,
            "fonte_nome": fonte_nome,
            "grupo": grupo,
            "tipo_coleta": "scraper_http" if not self._context_semaphore.locked() else "scraper_playwright",
            "coletado_em": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_nextjs(
        self, source_config: dict, config: dict, html: str
    ) -> list[dict]:
        """
        Extrai artigos de sites Next.js via __NEXT_DATA__ JSON blob.
        Fallback para HTML parsing se __NEXT_DATA__ não encontrado.
        """
        soup = BeautifulSoup(html, "html.parser")
        next_data_script = soup.find("script", id="__NEXT_DATA__")
        
        if not next_data_script:
            logger.info("__NEXT_DATA__ não encontrado para %s, fallback HTML", source_config.get("nome"))
            return self._extract_html(source_config, config, html)
        
        try:
            next_data = json.loads(next_data_script.string)
        except (json.JSONDecodeError, TypeError):
            return self._extract_html(source_config, config, html)
        
        url_base = config.get("url_noticias") or source_config.get("url", "")
        fonte_id = source_config.get("fonte_id", 0)
        fonte_nome = source_config.get("nome", "")
        grupo = config.get("grupo", "")
        
        articles = []
        
        def _buscar(obj, depth=0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                tem_titulo = any(k in obj for k in ("title", "titulo", "headline", "name"))
                tem_url = any(k in obj for k in ("url", "href", "link", "slug", "path"))
                
                if tem_titulo and tem_url:
                    titulo = obj.get("title") or obj.get("titulo") or obj.get("headline") or obj.get("name") or ""
                    url = obj.get("url") or obj.get("href") or obj.get("link") or ""
                    slug = obj.get("slug") or obj.get("path") or ""
                    
                    if not url and slug:
                        url = urljoin(url_base, slug)
                    elif url and not url.startswith("http"):
                        url = urljoin(url_base, url)
                    
                    if titulo and url and len(str(titulo)) >= 10:
                        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
                        articles.append({
                            "titulo": str(titulo),
                            "url": url,
                            "url_hash": url_hash,
                            "data_publicacao": str(obj.get("date", obj.get("publishedAt", ""))) or None,
                            "resumo": str(obj.get("excerpt", obj.get("summary", "")))[:500],
                            "og_image": str(obj.get("image", obj.get("thumbnail", ""))) or "",
                            "fonte_id": fonte_id,
                            "fonte_nome": fonte_nome,
                            "grupo": grupo,
                            "tipo_coleta": "scraper_nextjs",
                            "coletado_em": datetime.now(timezone.utc).isoformat(),
                        })
                
                for val in obj.values():
                    _buscar(val, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    _buscar(item, depth + 1)
        
        try:
            _buscar(next_data.get("props", {}))
        except Exception as e:
            logger.warning("Erro parsear __NEXT_DATA__ de %s: %s", fonte_nome, e)
        
        return articles or self._extract_html(source_config, config, html)

    async def _collect_api_json(
        self, source_config: dict, config: dict
    ) -> list[dict]:
        """Coleta via API JSON (WordPress REST API, APIs genéricas)."""
        api_url = config.get("url_api") or config.get("url_noticias") or source_config.get("url", "")
        fonte_id = source_config.get("fonte_id", 0)
        fonte_nome = source_config.get("nome", "")
        grupo = config.get("grupo", "")
        url_base = config.get("url_home", "")
        
        try:
            response = await self.http_client.get(api_url)
            if response.status_code >= 400:
                return []
            data = response.json()
        except Exception as e:
            logger.warning("API JSON erro para %s: %s", fonte_nome, e)
            return []
        
        items = data if isinstance(data, list) else data.get("items", data.get("results", data.get("posts", [])))
        if not isinstance(items, list):
            return []
        
        articles = []
        for item in items:
            if not isinstance(item, dict):
                continue
            
            titulo = item.get("title", {}).get("rendered", "") if isinstance(item.get("title"), dict) else str(item.get("title", item.get("titulo", item.get("headline", ""))))
            url = str(item.get("link", item.get("url", item.get("href", ""))))
            slug = str(item.get("slug", ""))
            
            if not url and slug:
                url = urljoin(url_base, slug)
            if not titulo or not url or len(titulo) < 10:
                continue
            
            # og:image via WP _embedded
            og_image = ""
            if isinstance(item.get("_embedded"), dict):
                media = item["_embedded"].get("wp:featuredmedia", [])
                if media and isinstance(media[0], dict):
                    og_image = media[0].get("source_url", "")
            
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            articles.append({
                "titulo": titulo,
                "url": url,
                "url_hash": url_hash,
                "data_publicacao": str(item.get("date", item.get("published", ""))) or None,
                "resumo": "",
                "og_image": og_image,
                "fonte_id": fonte_id,
                "fonte_nome": fonte_nome,
                "grupo": grupo,
                "tipo_coleta": "scraper_api",
                "coletado_em": datetime.now(timezone.utc).isoformat(),
            })
        
        return articles

    async def _collect_sitemap(
        self, source_config: dict, config: dict
    ) -> list[dict]:
        """Coleta via XML Sitemap."""
        sitemap_url = config.get("url_sitemap") or urljoin(
            config.get("url_home", source_config.get("url", "")), "/sitemap.xml"
        )
        fonte_id = source_config.get("fonte_id", 0)
        fonte_nome = source_config.get("nome", "")
        grupo = config.get("grupo", "")
        
        try:
            response = await self.http_client.get(sitemap_url)
            if response.status_code >= 400:
                return []
        except Exception as e:
            logger.warning("Sitemap erro para %s: %s", fonte_nome, e)
            return []
        
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        
        soup = BeautifulSoup(response.text, "xml")
        articles = []
        
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if not loc:
                continue
            url = loc.get_text(strip=True)
            
            lastmod = url_tag.find("lastmod")
            if lastmod:
                try:
                    lm = lastmod.get_text(strip=True)
                    dt = datetime.fromisoformat(lm.replace("Z", "+00:00")) if "T" in lm else datetime.strptime(lm, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                except ValueError:
                    pass
            
            # Filtra por paths de notícias
            path = urlparse(url).path.lower()
            if not any(p in path for p in ("/noticias/", "/noticia/", "/news/", "/comunicacao/", "/imprensa/", "/materia/", "/artigo/")):
                continue
            
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            articles.append({
                "titulo": "",  # Sitemap não tem título — será extraído downstream
                "url": url,
                "url_hash": url_hash,
                "data_publicacao": lastmod.get_text(strip=True) if lastmod else None,
                "resumo": "",
                "og_image": "",
                "fonte_id": fonte_id,
                "fonte_nome": fonte_nome,
                "grupo": grupo,
                "tipo_coleta": "scraper_sitemap",
                "coletado_em": datetime.now(timezone.utc).isoformat(),
            })
        
        return articles
```

### 6.4 Gerenciamento de Recursos Playwright

**OBRIGATÓRIO:** Playwright consome muita RAM (~1-2 GB por contexto Chromium). O sistema DEVE:

1. **Instância única de Browser** — `chromium.launch()` é chamado UMA vez no `start()`, compartilhado por todos os workers
2. **Semáforo de contextos** — `asyncio.Semaphore(PLAYWRIGHT_MAX_CONTEXTS=5)` limita contextos simultâneos
3. **Contextos isolados por fetch** — cada `_fetch_with_playwright` cria/destrói seu próprio contexto
4. **Bloqueio de recursos pesados** — imagens, fonts, media e CSS são interceptados e abortados via `page.route()`
5. **Timeout em dois estágios** — `domcontentloaded` (45s) + `networkidle` (5s adicional, não-fatal)
6. **Cleanup garantido** — `page.close()` e `context.close()` em `finally`, mesmo em exceção

### 6.5 Robots.txt e Politeness

```python
# brasileira/ingestion/collectors/robots_checker.py
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

class RobotsChecker:
    """
    Cache de robots.txt por domínio.
    Verifica se podemos acessar uma URL.
    
    OBRIGATÓRIO: Respeitar robots.txt é legal e ético.
    """
    def __init__(self):
        self._cache: dict[str, RobotFileParser] = {}

    async def can_fetch(self, url: str, user_agent: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        
        if base not in self._cache:
            rp = RobotFileParser()
            try:
                rp.set_url(f"{base}/robots.txt")
                rp.read()
                self._cache[base] = rp
            except Exception:
                # Se não consegue ler robots.txt, permite (fail-open)
                self._cache[base] = RobotFileParser()
        
        return self._cache[base].can_fetch(user_agent, url)

    def get_crawl_delay(self, url: str, user_agent: str) -> float:
        """Retorna crawl-delay em segundos, default 1.0."""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._cache.get(base)
        if rp:
            delay = rp.crawl_delay(user_agent)
            if delay:
                return float(delay)
        return 1.0  # Default 1s entre requests ao mesmo domínio
```

**Rate limiting por domínio:** O WorkerPool DEVE implementar rate limiting por domínio usando um `asyncio.Lock` + timestamp por `netloc`, respeitando o `Crawl-delay` do robots.txt. Isso é feito no nível do worker antes de chamar o coletor, não dentro do coletor.

---

## PARTE VII — ESPECIFICAÇÃO: DEDUPLICAÇÃO EM 4 CAMADAS

### 7.1 Visão Geral

```
Artigo coletado
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│ CAMADA 1: HTTP ETag / 304 Not Modified                  │
│ Onde: No RSSCollector, ANTES de baixar o feed           │
│ Custo: Zero (HTTP nativo)                               │
│ Escopo: Evita re-processar feeds que não mudaram         │
│ Se 304 → retorna [] (feed inteiro ignorado)             │
└───────────────────────────┬─────────────────────────────┘
                            │ feed mudou (200)
                            ▼
┌─────────────────────────────────────────────────────────┐
│ CAMADA 2: Redis SET de URLs normalizadas                │
│ Onde: No WorkerPool, após coletor retornar artigos      │
│ Custo: O(1) lookup em Redis                             │
│ Escopo: URL exata (normalizada) já vista nas últimas 72h│
│ Key: dedup:urls (SET com TTL 72h nos membros)           │
│ Se membro existe → artigo ignorado                      │
└───────────────────────────┬─────────────────────────────┘
                            │ URL nova
                            ▼
┌─────────────────────────────────────────────────────────┐
│ CAMADA 3: SHA-256 hash (título + domínio_fonte + data)  │
│ Onde: No WorkerPool, após Camada 2                      │
│ Custo: O(1) lookup em PostgreSQL (índice UNIQUE)        │
│ Escopo: Mesmo artigo com URL diferente (utm_params, etc)│
│ Hash: sha256(titulo_normalizado + domínio + data[:10])  │
│ Se hash existe → artigo ignorado                        │
└───────────────────────────┬─────────────────────────────┘
                            │ hash novo
                            ▼
┌─────────────────────────────────────────────────────────┐
│ CAMADA 4: SimHash LSH (near-duplicate)                  │
│ Onde: No WorkerPool, após Camada 3                      │
│ Custo: O(1) amortizado com LSH index                    │
│ Escopo: Artigos "quase iguais" (rewrite de agência)     │
│ Threshold: Hamming distance ≤ 3 bits (de 64)            │
│ Se match → artigo marcado como near-duplicate           │
│   (produz para Kafka com flag near_duplicate=true)      │
│   (downstream decide se consolida ou ignora)            │
└───────────────────────────┬─────────────────────────────┘
                            │ artigo genuinamente novo
                            ▼
                    Produce para Kafka: raw-articles
```

### 7.2 Implementação OBRIGATÓRIA

```python
# brasileira/ingestion/dedup.py
import hashlib
import logging
import re
import unicodedata
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class DeduplicationEngine:
    """
    Motor de deduplicação em 4 camadas.
    
    Camada 1 (ETag) é aplicada no coletor RSS, não aqui.
    Camadas 2-4 são aplicadas aqui, no WorkerPool.
    """

    def __init__(self, redis_client=None, db_pool=None):
        self.redis = redis_client
        self.db_pool = db_pool
        # SimHash index em memória (rebuild a cada restart)
        self._simhash_index: dict[int, str] = {}  # simhash_value -> url_hash

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normaliza URL para comparação:
        - Remove www.
        - Remove trailing slash
        - Remove query params de tracking (utm_*, fbclid, etc.)
        - Lowercase scheme e netloc
        """
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.rstrip("/")
        
        # Remove tracking params
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "fbclid", "gclid", "ref", "source", "amp",
        }
        if parsed.query:
            params = parse_qs(parsed.query)
            cleaned = {k: v for k, v in params.items() if k.lower() not in tracking_params}
            query = urlencode(cleaned, doseq=True) if cleaned else ""
        else:
            query = ""
        
        return urlunparse((
            parsed.scheme.lower(), netloc, path, "", query, ""
        ))

    @staticmethod
    def normalize_title(titulo: str) -> str:
        """
        Normaliza título para hashing:
        - Lowercase
        - Remove acentos
        - Remove caracteres especiais
        - Colapsa espaços
        """
        titulo = titulo.lower().strip()
        # Remove acentos
        titulo = unicodedata.normalize("NFKD", titulo)
        titulo = "".join(c for c in titulo if not unicodedata.combining(c))
        # Remove caracteres especiais
        titulo = re.sub(r"[^a-z0-9\s]", "", titulo)
        # Colapsa espaços
        titulo = re.sub(r"\s+", " ", titulo).strip()
        return titulo

    @staticmethod
    def compute_content_hash(titulo: str, dominio_fonte: str, data: Optional[str]) -> str:
        """
        SHA-256 de título normalizado + domínio + data.
        Detecta mesma matéria com URL diferente.
        """
        titulo_norm = DeduplicationEngine.normalize_title(titulo)
        data_prefix = (data or "")[:10]  # Só a data (YYYY-MM-DD)
        payload = f"{titulo_norm}|{dominio_fonte}|{data_prefix}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_simhash(text: str, hashbits: int = 64) -> int:
        """
        Calcula SimHash de um texto para near-duplicate detection.
        
        Usa shingles de 3 palavras para capturar frases, não apenas bag-of-words.
        """
        tokens = text.lower().split()
        if len(tokens) < 3:
            return 0
        
        # Shingles de 3 palavras
        shingles = [" ".join(tokens[i:i+3]) for i in range(len(tokens) - 2)]
        
        v = [0] * hashbits
        for shingle in shingles:
            h = int(hashlib.md5(shingle.encode("utf-8")).hexdigest(), 16)
            for i in range(hashbits):
                bitmask = 1 << i
                if h & bitmask:
                    v[i] += 1
                else:
                    v[i] -= 1
        
        fingerprint = 0
        for i in range(hashbits):
            if v[i] >= 0:
                fingerprint |= (1 << i)
        
        return fingerprint

    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        """Distância de Hamming entre dois SimHashes."""
        return bin(hash1 ^ hash2).count("1")

    async def check_and_register(self, article: dict) -> bool:
        """
        Verifica se artigo é novo em todas as camadas.
        Se novo, registra e retorna True.
        Se duplicado, retorna False.
        
        CAMADA 1 (ETag) já foi aplicada no coletor.
        """
        url = article.get("url", "")
        titulo = article.get("titulo", "")
        url_hash = article.get("url_hash", "")
        
        if not url or not url_hash:
            return False
        
        # CAMADA 2: Redis URL SET
        url_normalizada = self.normalize_url(url)
        if self.redis:
            is_new = await self.redis.sadd("dedup:urls", url_normalizada)
            if not is_new:
                logger.debug("Dedup Camada 2 (Redis URL): %s", url[:80])
                return False
            # TTL no SET inteiro: 72h (renovado a cada adição)
            await self.redis.expire("dedup:urls", 259200)
        
        # CAMADA 3: SHA-256 content hash em PostgreSQL
        if self.db_pool and titulo:
            from urllib.parse import urlparse
            dominio = urlparse(url).netloc
            content_hash = self.compute_content_hash(titulo, dominio, article.get("data_publicacao"))
            
            async with self.db_pool.acquire() as conn:
                # INSERT com ON CONFLICT — atômico, sem race condition
                result = await conn.execute("""
                    INSERT INTO artigos (url_hash, titulo, url_fonte, editoria)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (url_hash) DO NOTHING
                """, content_hash, titulo, url, article.get("grupo", "geral"))
                
                # Se 0 rows affected, já existia
                if result == "INSERT 0 0":
                    logger.debug("Dedup Camada 3 (SHA-256): %s", titulo[:60])
                    return False
        
        # CAMADA 4: SimHash near-duplicate
        if titulo:
            simhash = self.compute_simhash(titulo)
            if simhash:
                for existing_hash, existing_url_hash in self._simhash_index.items():
                    if self.hamming_distance(simhash, existing_hash) <= 3:
                        # Near-duplicate detectado — marca no artigo, mas NÃO bloqueia
                        article["near_duplicate"] = True
                        article["near_duplicate_of"] = existing_url_hash
                        logger.info(
                            "Dedup Camada 4 (SimHash): near-duplicate detectado | %s",
                            titulo[:60],
                        )
                        break
                
                # Registra no index
                self._simhash_index[simhash] = url_hash
        
        return True

    async def rebuild_simhash_index(self):
        """
        Reconstrói o índice SimHash a partir do PostgreSQL.
        Chamado no startup e periodicamente.
        """
        if not self.db_pool:
            return
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT titulo, url_hash FROM artigos
                WHERE publicado_em >= NOW() - INTERVAL '72 hours'
                ORDER BY publicado_em DESC
                LIMIT 10000
            """)
        
        self._simhash_index = {}
        for row in rows:
            titulo = row["titulo"]
            if titulo:
                simhash = self.compute_simhash(titulo)
                if simhash:
                    self._simhash_index[simhash] = row["url_hash"]
        
        logger.info("SimHash index reconstruído: %d entradas", len(self._simhash_index))
```

### 7.3 Diferenças Críticas vs V2

| Camada | V2 | V3 |
|--------|-----|-----|
| 1. ETag | Inexistente | Redis com TTL 24h, enviado em If-None-Match |
| 2. URL | SQL query por artigo (N+1) | Redis SET O(1), com normalização (www, trailing slash, utm) |
| 3. Content hash | Inexistente | SHA-256(título normalizado + domínio + data), INSERT ON CONFLICT (atômico) |
| 4. Near-duplicate | Inexistente | SimHash 64-bit com Hamming distance ≤ 3 |
| Race condition | Check-then-act não atômico | INSERT ON CONFLICT — operação atômica do PostgreSQL |
| Performance | `get_published_urls_last_24h` sem LIMIT (milhares de URLs em memória) | Redis SET (O(1)) + PostgreSQL index (O(1)) |

---

## PARTE VIII — ESPECIFICAÇÃO: SOURCE HEALTH TRACKER

### 8.1 Responsabilidade

Monitora saúde de cada fonte. Registra latência, sucesso/falha, taxa de artigos. Fornece dados para o adaptive polling do Scheduler e para o agente Focas (que gerencia fontes).

### 8.2 Implementação OBRIGATÓRIA

```python
# brasileira/ingestion/health.py
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

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
    """
    Rastreia saúde de cada fonte. Dados em Redis para acesso rápido,
    com persistência periódica em PostgreSQL.
    
    PRINCÍPIO: NUNCA desativa uma fonte. Apenas ajusta polling interval.
    """

    def __init__(self, redis_client=None, db_pool=None):
        self.redis = redis_client
        self.db_pool = db_pool
        self._local_cache: dict[int, SourceHealthRecord] = {}

    def get_source_health(self, fonte_id: int) -> Optional[SourceHealthRecord]:
        return self._local_cache.get(fonte_id)

    def record_success(self, fonte_id: int, latency_ms: float = 0.0, articles_count: int = 0):
        record = self._local_cache.setdefault(fonte_id, SourceHealthRecord(fonte_id=fonte_id))
        record.consecutive_successes += 1
        record.consecutive_failures = 0
        record.total_successes += 1
        record.last_success = datetime.now(timezone.utc)
        record.articles_last_cycle = articles_count
        
        # Moving average de latência
        if record.avg_latency_ms == 0:
            record.avg_latency_ms = latency_ms
        else:
            record.avg_latency_ms = record.avg_latency_ms * 0.8 + latency_ms * 0.2

    def record_failure(self, fonte_id: int, error_type: str = "unknown"):
        record = self._local_cache.setdefault(fonte_id, SourceHealthRecord(fonte_id=fonte_id))
        record.consecutive_failures += 1
        record.consecutive_successes = 0
        record.total_failures += 1
        record.last_failure = datetime.now(timezone.utc)
        record.last_error_type = error_type
        
        # Log alertas baseado em falhas consecutivas
        if record.consecutive_failures == 3:
            logger.warning(
                "ALERTA: fonte_id=%d com 3 falhas consecutivas (último erro: %s)",
                fonte_id, error_type,
            )
        elif record.consecutive_failures == 10:
            logger.error(
                "ALERTA CRÍTICO: fonte_id=%d com 10 falhas consecutivas — investigar",
                fonte_id,
            )

    async def persist_to_postgres(self):
        """
        Persiste métricas de saúde no PostgreSQL.
        Chamado periodicamente pelo scheduler ou monitor.
        """
        if not self.db_pool:
            return
        
        async with self.db_pool.acquire() as conn:
            for fonte_id, record in self._local_cache.items():
                await conn.execute("""
                    UPDATE fontes SET
                        ultimo_sucesso = COALESCE($2, ultimo_sucesso),
                        ultimo_erro = $3
                    WHERE id = $1
                """, fonte_id, record.last_success, record.last_error_type)

    async def persist_to_redis(self):
        """
        Publica métricas no Redis para acesso rápido por outros componentes.
        """
        if not self.redis:
            return
        
        for fonte_id, record in self._local_cache.items():
            await self.redis.hset(f"source:health:{fonte_id}", mapping={
                "consecutive_failures": record.consecutive_failures,
                "consecutive_successes": record.consecutive_successes,
                "last_success": record.last_success.isoformat() if record.last_success else "",
                "last_error_type": record.last_error_type or "",
                "avg_latency_ms": str(round(record.avg_latency_ms, 2)),
                "articles_last_cycle": record.articles_last_cycle,
            })
            await self.redis.expire(f"source:health:{fonte_id}", 7200)  # 2h TTL
```

---

## PARTE IX — TÓPICOS KAFKA E SCHEMAS DE MENSAGEM

### 9.1 Tópicos Usados por Este Componente

| Tópico | Papel neste componente | Partições | Retenção |
|--------|----------------------|-----------|----------|
| `fonte-assignments` | PRODUCE (Scheduler) + CONSUME (Workers) | 10 (por fonte_id % 10) | 1h |
| `raw-articles` | PRODUCE (Workers após dedup) | 20 (por publisher_id hash) | 24h |

### 9.2 Schema da Mensagem `fonte-assignments`

```json
{
    "fonte_id": 42,
    "nome": "Agência Brasil",
    "url": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml",
    "tipo": "rss",
    "tier": "vip",
    "config_scraper": null,
    "polling_interval_min": 15,
    "priority": "high",
    "scheduled_at": "2026-03-26T12:00:00-03:00",
    "retry": false
}
```

### 9.3 Schema da Mensagem `raw-articles`

```json
{
    "titulo": "Governo anuncia novo pacote de investimentos em infraestrutura",
    "url": "https://agenciabrasil.ebc.com.br/economia/noticia/2026-03/governo-anuncia-novo-pacote",
    "url_hash": "a1b2c3d4e5f6...",
    "data_publicacao": "2026-03-26T10:30:00-03:00",
    "resumo": "O governo federal anunciou nesta terça-feira um novo pacote...",
    "og_image": "https://agenciabrasil.ebc.com.br/sites/default/files/foto.jpg",
    "fonte_id": 42,
    "fonte_nome": "Agência Brasil",
    "grupo": "governo",
    "tipo_coleta": "rss",
    "coletado_em": "2026-03-26T12:01:15-03:00",
    "near_duplicate": false,
    "near_duplicate_of": null
}
```

---

## PARTE X — TABELAS POSTGRESQL

### 10.1 Tabelas Que Este Componente Usa

```sql
-- Tabela de fontes (já definida no master briefing, incluída aqui como referência)
CREATE TABLE IF NOT EXISTS fontes (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    url TEXT UNIQUE NOT NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'rss',  -- 'rss' | 'scraper'
    tier VARCHAR(20) NOT NULL DEFAULT 'padrao',  -- 'vip' | 'padrao' | 'secundario'
    config_scraper JSONB DEFAULT '{}',
    polling_interval_min INTEGER DEFAULT 30,
    ultimo_sucesso TIMESTAMPTZ,
    ultimo_erro TEXT,
    ativa BOOLEAN DEFAULT TRUE,  -- NUNCA muda para false automaticamente
    criado_em TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fontes_tier ON fontes(tier);
CREATE INDEX IF NOT EXISTS idx_fontes_tipo ON fontes(tipo);
CREATE INDEX IF NOT EXISTS idx_fontes_ativa ON fontes(ativa) WHERE ativa = TRUE;

-- Tabela de artigos (deduplicação + tracking)
CREATE TABLE IF NOT EXISTS artigos (
    id SERIAL PRIMARY KEY,
    url_hash CHAR(64) UNIQUE NOT NULL,  -- SHA-256, UNIQUE para dedup atômica
    wp_post_id INTEGER UNIQUE,
    url_fonte TEXT NOT NULL,
    titulo TEXT NOT NULL,
    editoria VARCHAR(50) DEFAULT 'geral',
    urgencia VARCHAR(20) DEFAULT 'normal',
    score_relevancia FLOAT,
    publicado_em TIMESTAMPTZ DEFAULT NOW(),
    revisado BOOLEAN DEFAULT FALSE,
    imagem_aplicada BOOLEAN DEFAULT FALSE,
    fonte_id INTEGER REFERENCES fontes(id),
    fonte_nome VARCHAR(200),
    tipo_coleta VARCHAR(30),
    near_duplicate BOOLEAN DEFAULT FALSE,
    near_duplicate_of CHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_artigos_url_hash ON artigos(url_hash);
CREATE INDEX IF NOT EXISTS idx_artigos_publicado ON artigos(publicado_em DESC);
CREATE INDEX IF NOT EXISTS idx_artigos_editoria ON artigos(editoria);
CREATE INDEX IF NOT EXISTS idx_artigos_fonte ON artigos(fonte_id);

-- Tabela de métricas de coleta (observabilidade)
CREATE TABLE IF NOT EXISTS coleta_metricas (
    id SERIAL PRIMARY KEY,
    fonte_id INTEGER REFERENCES fontes(id),
    ciclo_id VARCHAR(50),  -- UUID do ciclo
    artigos_coletados INTEGER DEFAULT 0,
    artigos_novos INTEGER DEFAULT 0,
    artigos_deduplicados INTEGER DEFAULT 0,
    latency_ms INTEGER,
    sucesso BOOLEAN DEFAULT TRUE,
    erro_tipo VARCHAR(100),
    worker_id VARCHAR(50),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_coleta_fonte_time ON coleta_metricas(fonte_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_coleta_ciclo ON coleta_metricas(ciclo_id);
```

### 10.2 Migração de MariaDB para PostgreSQL

A V2 usa MariaDB (`bitnami_wordpress` com prefixo `wp_7_`). A V3 usa PostgreSQL separado (NÃO o mesmo banco do WordPress).

**OBRIGATÓRIO:** As tabelas acima são criadas no PostgreSQL V3. O banco MariaDB do WordPress continua existindo para o CMS, mas os agentes V3 usam PostgreSQL para tudo exceto a publicação de posts (que usa a WordPress REST API).

---

## PARTE XI — CHAVES REDIS

### 11.1 Chaves Usadas por Este Componente

| Chave | Tipo | TTL | Uso |
|-------|------|-----|-----|
| `dedup:urls` | SET | 72h | URLs normalizadas de artigos já processados |
| `source:etag:{fonte_id}` | STRING | 24h | ETag HTTP do último fetch de cada fonte RSS |
| `source:last_modified:{fonte_id}` | STRING | 24h | Last-Modified HTTP do último fetch |
| `source:health:{fonte_id}` | HASH | 2h | Métricas de saúde por fonte |

---

## PARTE XII — ESTRUTURA DE DIRETÓRIOS E DEPENDÊNCIAS

### 12.1 Estrutura de Arquivos

```
brasileira/
├── ingestion/
│   ├── __init__.py
│   ├── scheduler.py           # FeedScheduler
│   ├── worker_pool.py         # WorkerPool
│   ├── dedup.py               # DeduplicationEngine
│   ├── health.py              # SourceHealthTracker
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── rss_collector.py   # RSSCollector
│   │   ├── scraper_collector.py  # ScraperCollector
│   │   └── robots_checker.py  # RobotsChecker
│   └── main.py                # Entrypoint: inicializa tudo, roda scheduler + workers
├── llm/
│   └── smart_router.py        # SmartLLMRouter (Componente #1 — já implementado)
├── db/
│   └── postgres.py            # Pool asyncpg
└── config/
    └── settings.py            # Variáveis de ambiente, configuração
```

### 12.2 Dependências Python (requirements.txt parcial)

```
# Async runtime
asyncio  # stdlib

# Kafka
aiokafka>=0.10.0

# HTTP
httpx[http2]>=0.27.0
feedparser>=6.0.11

# Scraping
playwright>=1.48.0
beautifulsoup4>=4.12.0
lxml>=5.0.0

# Database
asyncpg>=0.29.0  # PostgreSQL async

# Cache
redis[hiredis]>=5.0.0  # Redis async com hiredis para performance

# Hashing
simhash>=2.1.2  # Alternativa: implementação nativa conforme dedup.py

# Utils
python-dotenv>=1.0.0
```

### 12.3 Variáveis de Ambiente OBRIGATÓRIAS

```env
# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# PostgreSQL
POSTGRES_DSN=postgresql://brasileira:password@localhost:5432/brasileira_v3

# Redis
REDIS_URL=redis://localhost:6379/0

# Worker Pool
INGESTION_NUM_WORKERS=30
INGESTION_CYCLE_INTERVAL=1800  # 30 minutos

# Playwright
PLAYWRIGHT_MAX_CONTEXTS=5

# Timeouts
RSS_FETCH_TIMEOUT=12
HTTP_SCRAPER_TIMEOUT=20
PLAYWRIGHT_PAGE_TIMEOUT=45000
```

---

## PARTE XIII — ENTRYPOINT E INICIALIZAÇÃO

### 13.1 Main Module

```python
# brasileira/ingestion/main.py
import asyncio
import logging
import signal
import os
from brasileira.ingestion.scheduler import FeedScheduler
from brasileira.ingestion.worker_pool import WorkerPool
from brasileira.ingestion.health import SourceHealthTracker
from brasileira.ingestion.dedup import DeduplicationEngine

logger = logging.getLogger(__name__)

async def main():
    """
    Entrypoint do Worker Pool de Coletores.
    
    Inicializa:
    1. Conexões (PostgreSQL, Redis, Kafka)
    2. Health Tracker
    3. Worker Pool (30-50 workers)
    4. Feed Scheduler
    
    Executa scheduler e workers em paralelo.
    """
    # 1. Configuração
    kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    postgres_dsn = os.getenv("POSTGRES_DSN", "postgresql://localhost:5432/brasileira_v3")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    num_workers = int(os.getenv("INGESTION_NUM_WORKERS", "30"))
    cycle_interval = int(os.getenv("INGESTION_CYCLE_INTERVAL", "1800"))

    # 2. Conexões
    import asyncpg
    import redis.asyncio as aioredis
    
    db_pool = await asyncpg.create_pool(
        postgres_dsn,
        min_size=5,
        max_size=20,
    )
    redis_client = aioredis.from_url(redis_url, decode_responses=False)
    
    # 3. Componentes
    health_tracker = SourceHealthTracker(redis_client=redis_client, db_pool=db_pool)
    
    worker_pool = WorkerPool(
        kafka_bootstrap=kafka_bootstrap,
        num_workers=num_workers,
        db_pool=db_pool,
        redis_client=redis_client,
    )
    
    scheduler = FeedScheduler(
        kafka_bootstrap=kafka_bootstrap,
        db_pool=db_pool,
        health_tracker=health_tracker,
        cycle_interval=cycle_interval,
    )
    
    # 4. Reconstruir índice SimHash
    await worker_pool.dedup.rebuild_simhash_index()
    
    # 5. Graceful shutdown
    shutdown_event = asyncio.Event()
    
    def handle_shutdown(sig):
        logger.info("Sinal %s recebido. Iniciando shutdown graceful...", sig)
        shutdown_event.set()
    
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: handle_shutdown(s))
    
    # 6. Start
    await worker_pool.start()
    await scheduler.start()
    
    logger.info(
        "=== Worker Pool de Coletores V3 iniciado ===\n"
        "  Workers: %d\n"
        "  Ciclo: %ds\n"
        "  Kafka: %s\n"
        "  PostgreSQL: %s\n"
        "  Redis: %s",
        num_workers, cycle_interval, kafka_bootstrap, postgres_dsn, redis_url,
    )
    
    # 7. Run
    try:
        await asyncio.gather(
            scheduler.run_forever(),
            shutdown_event.wait(),
        )
    except asyncio.CancelledError:
        pass
    finally:
        # 8. Shutdown
        logger.info("Encerrando Worker Pool...")
        await scheduler.stop()
        await worker_pool.stop()
        await health_tracker.persist_to_postgres()
        await db_pool.close()
        await redis_client.aclose()
        logger.info("=== Worker Pool de Coletores V3 encerrado ===")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(main())
```

---

## PARTE XIV — TESTES E VALIDAÇÃO

### 14.1 Critérios de Aceitação

| Critério | Métrica | Threshold |
|----------|---------|-----------|
| **Throughput** | Fontes processadas por ciclo | ≥ 648 (100% cobertura) |
| **Latência** | Tempo médio de coleta RSS | < 5s por feed |
| **Latência** | Tempo médio de coleta scraper HTTP | < 15s por fonte |
| **Latência** | Tempo médio de coleta scraper Playwright | < 45s por fonte |
| **Deduplicação** | Taxa de falsos negativos (artigos duplicados não detectados) | < 1% |
| **Deduplicação** | Taxa de falsos positivos (artigos únicos marcados como dup) | < 0,5% |
| **Isolamento** | Worker crash não afeta outros workers | 100% isolamento |
| **Resiliência** | Kafka indisponível por 5 min → recuperação automática | Sim, com retry |
| **Resiliência** | Redis indisponível → funciona com dedup degradada (sem Camadas 1-2) | Sim |
| **Resiliência** | PostgreSQL indisponível → funciona sem Camadas 3-4 | Sim |
| **Memória** | RSS do processo principal | < 2GB sem Playwright, < 4GB com Playwright |
| **ETag** | % de feeds que retornam 304 | > 50% (economia de banda) |

### 14.2 Testes Unitários OBRIGATÓRIOS

```python
# tests/ingestion/test_dedup.py

def test_normalize_url():
    dedup = DeduplicationEngine()
    assert dedup.normalize_url("https://www.example.com/news/?utm_source=twitter") == "https://example.com/news"
    assert dedup.normalize_url("https://example.com/news/") == "https://example.com/news"
    assert dedup.normalize_url("http://WWW.Example.COM/Path") == "http://example.com/Path"

def test_normalize_title():
    dedup = DeduplicationEngine()
    assert dedup.normalize_title("Governo Anuncia Pacote de Investimentos") == "governo anuncia pacote de investimentos"
    assert dedup.normalize_title("Inflação cai para 3,5% em março") == "inflacao cai para 35 em marco"

def test_simhash_similar_texts():
    dedup = DeduplicationEngine()
    h1 = dedup.compute_simhash("governo anuncia novo pacote de investimentos em infraestrutura")
    h2 = dedup.compute_simhash("governo anuncia novo pacote de investimentos em infra-estrutura federal")
    assert dedup.hamming_distance(h1, h2) <= 5  # Textos similares = distância baixa

def test_simhash_different_texts():
    dedup = DeduplicationEngine()
    h1 = dedup.compute_simhash("governo anuncia novo pacote de investimentos")
    h2 = dedup.compute_simhash("time de futebol vence campeonato estadual")
    assert dedup.hamming_distance(h1, h2) > 10  # Textos diferentes = distância alta

def test_content_hash_ignores_utm():
    dedup = DeduplicationEngine()
    h1 = dedup.compute_content_hash("Governo anuncia pacote", "agenciabrasil.ebc.com.br", "2026-03-26")
    h2 = dedup.compute_content_hash("governo anuncia pacote", "agenciabrasil.ebc.com.br", "2026-03-26T10:30:00")
    assert h1 == h2  # Mesmo título normalizado + mesmo domínio + mesma data
```

### 14.3 Testes de Integração OBRIGATÓRIOS

1. **Teste RSS com ETag:** Fetch um feed → verifica ETag no Redis → segundo fetch retorna 304
2. **Teste Playwright:** Fetch site JS-heavy → verifica que HTML contém conteúdo renderizado por JavaScript
3. **Teste Kafka end-to-end:** Scheduler → fonte-assignments → Worker → raw-articles → consumer verifica mensagem
4. **Teste deduplicação atômica:** 2 workers processam mesmo artigo simultaneamente → apenas 1 é inserido (INSERT ON CONFLICT)
5. **Teste isolamento de falhas:** Worker #1 recebe fonte que dá timeout → Workers #2-#30 continuam normalmente
6. **Teste graceful shutdown:** SIGTERM → workers terminam artigo atual → stats finais logadas

---

## PARTE XV — OBSERVABILIDADE E MÉTRICAS

### 15.1 Logs Estruturados

Todos os logs DEVEM seguir formato estruturado para facilitar queries no observability stack:

```python
# Formato: [COMPONENTE] [WORKER] [AÇÃO] campos=valores
logger.info(
    "[INGESTION] [worker-003] [COLETA_OK] fonte=%s tipo=%s artigos=%d novos=%d latency_ms=%d",
    fonte_nome, tipo_coleta, total, novos, latency_ms,
)

logger.warning(
    "[INGESTION] [worker-003] [TIMEOUT] fonte=%s url=%s timeout_s=%d",
    fonte_nome, url, timeout,
)

logger.error(
    "[INGESTION] [worker-003] [ERRO] fonte=%s error_type=%s msg=%s",
    fonte_nome, type(e).__name__, str(e),
)
```

### 15.2 Métricas para Dashboard

| Métrica | Descrição | Alerta se |
|---------|-----------|-----------|
| `ingestion.sources.processed` | Fontes processadas por ciclo | < 600 (de 648+) |
| `ingestion.articles.collected` | Artigos coletados por ciclo | < 100 |
| `ingestion.articles.new` | Artigos novos (pós-dedup) por ciclo | < 30 |
| `ingestion.articles.deduped` | Artigos deduplicados por ciclo | > 95% (algo errado) |
| `ingestion.etag.hit_rate` | % de feeds que retornaram 304 | < 30% (ETags não funcionando) |
| `ingestion.playwright.active_contexts` | Contextos Playwright ativos | > PLAYWRIGHT_MAX_CONTEXTS |
| `ingestion.worker.active` | Workers ativos | < num_workers * 0.5 |
| `ingestion.errors.rate` | Taxa de erros por ciclo | > 10% |
| `ingestion.latency.p95` | Latência P95 de coleta | > 30s (RSS), > 60s (scraper) |

---

## PARTE XVI — PLANO DE IMPLEMENTAÇÃO

### 16.1 Ordem de Implementação (OBRIGATÓRIA)

```
Fase 1 (Fundação):
├── 1.1 Estrutura de diretórios + config/settings.py
├── 1.2 PostgreSQL: criar tabelas fontes, artigos, coleta_metricas
├── 1.3 Redis: verificar conexão, testar SET/GET
└── 1.4 Kafka: criar tópicos fonte-assignments e raw-articles

Fase 2 (Coletores):
├── 2.1 rss_collector.py — com ETag, feedparser, HTTPX async
├── 2.2 scraper_collector.py — HTTPX para estáticos
├── 2.3 scraper_collector.py — Playwright para JS-heavy
├── 2.4 robots_checker.py
└── 2.5 Testes unitários dos coletores

Fase 3 (Deduplicação):
├── 3.1 dedup.py — Camadas 2 e 3 (Redis URL + SHA-256 PostgreSQL)
├── 3.2 dedup.py — Camada 4 (SimHash)
└── 3.3 Testes unitários de dedup

Fase 4 (Orquestração):
├── 4.1 health.py — SourceHealthTracker
├── 4.2 worker_pool.py — Worker loop com consumer Kafka
├── 4.3 scheduler.py — FeedScheduler com producer Kafka
└── 4.4 main.py — Entrypoint

Fase 5 (Integração):
├── 5.1 Testes de integração end-to-end
├── 5.2 Load test: 648 fontes simuladas, 30 workers
├── 5.3 Teste de falhas: kill workers, desligar Redis, desligar Kafka
└── 5.4 Migração de dados: importar fontes V2 para PostgreSQL V3
```

### 16.2 Migração de Dados V2 → V3

As 648+ fontes atualmente configuradas em arquivos JSON (`scrapers.json`) e hardcoded no `motor_rss_v2.py` DEVEM ser migradas para a tabela `fontes` no PostgreSQL V3.

```python
# scripts/migrar_fontes_v2.py
# 1. Ler feeds RSS do motor_rss_v2 (lista hardcoded)
# 2. Ler scrapers.json do motor_scrapers_v2
# 3. Para cada fonte:
#    - Determinar tipo (rss/scraper)
#    - Determinar tier (vip/padrao/secundario) baseado no grupo
#    - Construir config_scraper JSONB (seletores, needs_javascript, etc.)
#    - INSERT na tabela fontes
```

---

## PARTE XVII — CHECKLIST DE VALIDAÇÃO FINAL

Antes de considerar o Worker Pool de Coletores implementado, verificar TODOS os itens:

- [ ] **648+ fontes processadas por ciclo** — sem blocos rotativos, sem caps
- [ ] **ETag/If-Modified-Since funcional** — verificar com `curl -I` que feeds retornam 304
- [ ] **Playwright renderiza sites JS** — testar com um site Next.js real
- [ ] **Deduplicação 4 camadas funcional** — artigo duplicado por URL, hash e SimHash
- [ ] **INSERT ON CONFLICT** — 2 workers processando mesmo artigo = 1 inserção
- [ ] **Kafka produce/consume funcional** — mensagens em `raw-articles` acessíveis por consumer downstream
- [ ] **Isolamento de workers** — kill -9 de um worker não afeta outros
- [ ] **Graceful shutdown** — SIGTERM encerra limpo em < 30s
- [ ] **Sem hard caps** — buscar por `MAX_ARTICLES`, `[:20]`, `[:10]` no código — NÃO devem existir
- [ ] **Sem `requests.get`** — buscar por `import requests` — NÃO deve existir neste componente
- [ ] **Sem `time.sleep`** — buscar por `time.sleep` — usar `asyncio.sleep` quando necessário
- [ ] **Sem `ThreadPoolExecutor`** — buscar por `ThreadPoolExecutor` — usar `asyncio.create_task`
- [ ] **Sem `nest_asyncio`** — buscar por `nest_asyncio` — NÃO deve existir
- [ ] **Sem `cloudscraper`** — buscar por `cloudscraper` — usar Playwright ou HTTPX
- [ ] **Sem `sys.path.insert`** — buscar por `sys.path` — NÃO deve existir
- [ ] **Logs estruturados** — todos os logs seguem formato `[INGESTION] [worker-id] [AÇÃO]`
- [ ] **Métricas no PostgreSQL** — tabela `coleta_metricas` populada a cada ciclo
- [ ] **Health no Redis** — chaves `source:health:*` atualizadas após cada coleta

---

*Fim do Briefing — Worker Pool de Coletores V3*
*Componente #2 do pipeline brasileira.news V3*
*Data: 26 de março de 2026*
