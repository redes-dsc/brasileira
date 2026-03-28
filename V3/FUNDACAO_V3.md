# brasileira.news V3.0 — Documento de Fundação Técnica

**Data:** 26 de março de 2026  
**Autor:** Head de TI / Desenvolvimento  
**Classificação:** Documento Estratégico-Técnico  
**Escopo:** Transição V2 → V3.0 — Reconstrução completa para padrão TIER-1

---

## 1. SUMÁRIO EXECUTIVO

A versão 2 do brasileira.news apresenta falhas estruturais que impedem produção estável: fluxo editorial invertido com 18 agentes-gate que bloqueiam publicação (resultado: 0 artigos publicados quando ativados), tiers LLM invertidos (ECONÔMICO para redação, PREMIUM para monitoring), ingestão sequencial de 648+ fontes onde 1 erro trava tudo, e duplicidade arquitetural (3 motores independentes + 20 agentes LangGraph nunca integrados).

A V3.0 é uma reconstrução do zero baseada em:
- **Auditoria de 329 bugs** catalogados em 20 arquivos de código-fonte
- **Benchmarking de 6 sistemas** em produção (AP, Bloomberg, Reuters, Washington Post, Forbes, BBC)
- **13 briefings técnicos** detalhando cada subsistema
- **Diretrizes de Context Engineering** baseadas em estado da arte (Anthropic, LangChain, Weaviate)

**Resultado esperado:** Portal TIER-1 publicando ≥40 artigos/hora, 16 categorias, 0% sem imagem, custo <$0.02/artigo.

---

## 2. DIAGNÓSTICO TÉCNICO COMPLETO DA V2

### 2.1 Inventário do Codebase Atual

```
PRODUÇÃO ATIVA (3 motores + curator):
├── motor_rss/           → Raia 1: RSS feeds (feedparser → LLM rewrite → WP)
│   ├── motor_rss_v2.py  → Motor principal
│   ├── llm_router.py    → Roteador LLM (41 modelos, 7 provedores, 4 tiers)
│   ├── image_handler.py → Cascade 5-tier de imagens
│   └── wp_publisher.py  → Publicador WordPress
├── motor_scrapers/      → Raia 2: Web scraping direto
│   ├── motor_scrapers_v2.py → Motor principal
│   └── detector_estrategia.py → Selenium vs BS4 vs Playwright
├── motor_consolidado/   → Raia 3: Monitoramento portais tier-1
│   ├── motor_consolidado.py → Motor principal (ciclo 2h)
│   ├── scraper_homes.py → Scraper de homepages
│   └── sintetizador.py  → Síntese multi-fonte
└── curator/             → Curadoria de homepage
    ├── curator_agent.py → Agente principal (score + tags)
    └── curator_scorer.py → Cálculo de relevância

NUNCA EM PRODUÇÃO ESTÁVEL (versao2/):
└── versao2/src/newsroom/  → 64 arquivos Python, 41.145 linhas
    ├── agents/            → 20 agentes LangGraph
    ├── llm/gateway.py     → 2.588 linhas, 101KB
    ├── memory/            → Redis + PG + pgvector
    └── pipeline/          → Editorial pipeline

CONFIGURAÇÃO:
├── config_geral.py        → WP_URL, AUTH_HEADERS (credenciais hardcoded)
├── config_categorias.py   → 13 macros + 28 subcategorias (precisa 16+)
├── catalogo_fontes.py     → 630+ fontes (sem YAML/JSON estruturado)
└── .env                   → Variáveis de ambiente (parcialmente usado)
```

### 2.2 Os 7 Problemas Fatais

| # | Problema | Impacto | Evidência |
|---|----------|---------|-----------|
| 1 | **Fluxo Invertido** | 0 artigos publicados com agentes ativos | Pauteiro filtra 99%, Editor-Chefe gate, Revisor rejeita |
| 2 | **Tiers LLM Invertidos** | Artigos de baixa qualidade, custos altos em monitoring | ECONÔMICO para redação/imagens, PREMIUM para health check |
| 3 | **Ingestão Sequencial** | 1 fonte com erro trava 648+ fontes | motor_rss processa sequencialmente sem isolamento |
| 4 | **Duplicidade Arquitetural** | Comportamento inconsistente, bugs de configuração | 2 curadores, 2 roteadores LLM, 2 configs incompatíveis |
| 5 | **Memória Fake** | Agentes não aprendem, repetem erros | BaseAgent V2 tem hooks mas nunca persiste/consulta |
| 6 | **Cobertura Limitada** | Portal "meia-boca" vs competidores | 4 editorias (precisa 16+), sem regionais |
| 7 | **Homepage Frágil** | 30-90s vazia durante atualização | clear→apply sequencial sem atomicidade |

### 2.3 Mapeamento V2 → V3 (18 → 9 Agentes)

| Agente V2 | Problema Fatal | V3 |
|-----------|---------------|-----|
| pauteiro-15.py | Filtra 99% das fontes | Agente paralelo de inteligência, NÃO entry point |
| editor_chefe-10.py | Gatekeeper que bloqueia | Observador estratégico no FIM |
| editor_editoria-9.py | Mais um gate (4 editorias) | **ELIMINADO** — ML automático |
| reporter-19.py | Espera pautas, faz draft | Escreve E publica 100% direto |
| revisor-20.py | Gate PRÉ-publicação, rejeita | PÓS-publicação, corrige in-place |
| publisher-7.py | Espera aprovação | **ELIMINADO** — integrado ao Reporter |
| fotografo-17.py | ECONÔMICO, sem og:image | PREMIUM queries, 4 tiers |
| curador_homepage-12.py | Score ECONÔMICO, só tags | PREMIUM, 6 zonas + layouts |
| curador_home-13.py | DUPLICIDADE | **ELIMINADO** |
| analista-2.py | Insights não consumidos | **ELIMINADO** |
| diretor-6.py | Foco em cortar custos | **ELIMINADO** |
| focas-8.py | Desativa fontes | Mantido, NUNCA desativa |
| consolidador-14.py | MIN_SOURCES=3 | Lógica 0/1/2+ por capas |
| monitor-16.py | Foco em custos | Foco em throughput |
| monitor_concorrencia-18.py | Alertas → Pauteiro | Alertas → Reporters direto |
| qa_layout-3.py | EventBus bug | **ELIMINADO** |
| qa_imagem-4.py | EventBus bug | **ELIMINADO** |
| base-5.py | Budgets BLOQUEIAM | Budgets como alertas |

---

## 3. ARQUITETURA V3 — VISÃO GERAL

### 3.1 Diagrama de 5 Camadas

```
┌─────────────────────────────────────────────────────────────────┐
│ CAMADA 1: INGESTÃO PARALELA                                      │
│   Feed Scheduler → Kafka:fonte-assignments → Worker Pool 30-50   │
│   RSS Collectors + Scraper Collectors (Playwright/HTTPX)          │
│   Dedup 4 camadas → Kafka:raw-articles                           │
├─────────────────────────────────────────────────────────────────┤
│ CAMADA 2: CLASSIFICAÇÃO E ROTEAMENTO                              │
│   Classificador ML local (NÃO LLM) → 16 categorias              │
│   Urgência + Tipo → Kafka:classified-articles                     │
├─────────────────────────────────────────────────────────────────┤
│ CAMADA 3: PRODUÇÃO EDITORIAL                                      │
│   Reporter Pool: contextualizar → redigir → SEO → publicar → WP │
│   Fan-out pós-publicação: Fotógrafo ║ Revisor ║ Consolidador     │
├─────────────────────────────────────────────────────────────────┤
│ CAMADA 4: CURADORIA E INTELIGÊNCIA                                │
│   Curador Homepage (6 zonas, ACF, layouts dinâmicos)             │
│   Pauteiro (trending, pautas especiais via Kafka)                 │
├─────────────────────────────────────────────────────────────────┤
│ CAMADA 5: OBSERVAÇÃO E ESTRATÉGIA                                 │
│   Editor-Chefe (analytics, 1h) ║ Monitor Concorrência (30min)   │
│   Monitor Sistema (health) ║ Focas (fontes, discovery)            │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Fluxo de Dados Principal

```
FONTES (648+) ──→ Kafka:fonte-assignments ──→ WORKERS (30-50)
                                                    │
                                              Kafka:raw-articles
                                                    │
                                              CLASSIFICADOR ML
                                                    │
                                           Kafka:classified-articles
                                                    │
                                              REPORTER POOL
                                              (escreve+publica)
                                                    │
                                           Kafka:article-published
                                                    │
                              ┌──────────────────┬──┴──────────────┐
                         FOTÓGRAFO          REVISOR          CONSOLIDADOR
                         (imagem)           (QA)             (análise)
                              │                │                  │
                         UPDATE WP         PATCH WP          PUBLISH WP
```

### 3.3 Stack Tecnológico

| Componente | Tecnologia | Justificativa |
|-----------|------------|---------------|
| Runtime agentes | LangGraph 1.0 | StateGraph + checkpointing. Produção: Uber, JP Morgan |
| Checkpointing | PostgresSaver | Pausa/retomada, sobrevive restarts |
| Message broker | Apache Kafka | Durabilidade, replay, consumer groups, particionamento |
| Cache | Redis Cluster | Working memory, dedup rápida, health scores |
| DB relacional | PostgreSQL 16 | Fonte de verdade: artigos, fontes, métricas |
| Vector DB | pgvector (HNSW) | Memória semântica/episódica, busca similaridade |
| CMS | WordPress REST API + ACF PRO | Publicação, homepage dinâmica |
| LLM Gateway | LiteLLM + SmartRouter | 7 provedores, health scoring, fallback cascata |
| Scraping | Playwright headless + HTTPX | SPAs/JS + sites estáticos |
| RSS | feedparser + HTTPX | ETag/If-Modified-Since |
| Observabilidade | LangSmith + OpenTelemetry | Tracing agentes, latência, custo/artigo |
| Imagens | Pexels, Unsplash, Wikimedia, Flickr CC, Agência Brasil | Gratuitas |
| Geração imagem | DALL-E 3 / Flux | Fallback quando foto real não existe |

---

## 4. SMART LLM ROUTER V3

### 4.1 Arquitetura

```python
class SmartLLMRouter:
    """
    1. NUNCA hardcoda modelos — escolhe MELHOR DISPONÍVEL do tier
    2. Se provedor falha → tenta TODOS antes de desistir
    3. Se tier inteiro falha → downgrade automático
    4. NUNCA retorna erro sem tentar todos os 7 provedores
    5. Pools dinâmicos — carregáveis de Redis, sem deploy
    """
    
    TIER_POOLS = {
        "premium": [  # Claude Sonnet 4.6, GPT-5.4, Gemini 3.1 Pro, Grok 4, Sonar Pro, ... ],
        "padrao":  [  # GPT-4.1 Mini, Gemini 2.5 Flash, Grok 4.1 Fast, DeepSeek, Qwen3.5+, ... ],
        "economico": [ # Qwen3.5 Flash, DeepSeek, Gemini Flash-Lite, GPT-4.1 Nano, ... ],
    }
    
    async def route_request(self, task_type, content):
        tier = self.get_tier_for_task(task_type)
        pool = await self.load_pool_from_redis(tier) or self.TIER_POOLS[tier]
        ranked = self.rank_by_health_and_cost(pool)
        
        for model in ranked:
            try: return await self.call_provider(model, content, timeout=30)
            except: continue  # PRÓXIMO modelo, NUNCA para
        
        # Tier falhou → downgrade
        if tier == "premium": return await self.route_with_tier("padrao", content)
        elif tier == "padrao": return await self.route_with_tier("economico", content)
        return await self.last_resort_any_model(content)
```

### 4.2 Health Scoring Dinâmico

Score 0-100 por modelo: 50% taxa de sucesso + 30% velocidade + 20% tempo desde último erro.
- Score < 30 → deprioritizado (mas NÃO excluído)
- Score = 0 → skip por 5 minutos

### 4.3 Mapeamento Tarefa → Tier

| Tarefa | Tier | Justificativa |
|--------|------|---------------|
| redacao_artigo | PREMIUM | Qualidade editorial TIER-1 |
| imagem_query | PREMIUM | Relevância depende da query |
| homepage_scoring | PREMIUM | Decisão de altíssimo impacto |
| consolidacao_sintese | PREMIUM | Análise precisa raciocínio |
| seo_otimizacao | PADRÃO | Otimização mecânica |
| revisao_texto | PADRÃO | Correção gramatical |
| trending_detection | PADRÃO | Raciocínio mas não máximo |
| classificacao_categoria | ECONÔMICO | Repetitivo e simples |
| extracao_entidades | ECONÔMICO | NER básico |
| deduplicacao_texto | ECONÔMICO | Comparação mecânica |

---

## 5. ESPECIFICAÇÃO DOS 9 AGENTES V3

### 5.1 Reporter (Agente Principal)

**Papel:** Coração do sistema. Consome classificados do Kafka, escreve e publica 100%.

**Pipeline LangGraph:** contextualizar (RAG) → redigir (PREMIUM) → SEO (PADRÃO) → publicar (WP REST) → eventos (Kafka)

**Regras:** Sem draft. Sem aprovação. 100% processado. Min 300 palavras.

### 5.2 Fotógrafo (Pós-Publicação)

**Pipeline 4 Tiers:**
1. og:image da fonte original (gratuito)
2. Busca com queries PREMIUM (Pexels → Unsplash → Wikimedia → Flickr → Agência Brasil)
3. Geração IA (DALL-E 3 / Flux) com label "Imagem gerada por IA"
4. Placeholder temático por editoria (garantia)

**Reformulação automática:** broadening → pivoting (máx 2 rodadas)

### 5.3 Revisor (QA Pós-Publicação)

**Regra:** NUNCA rejeita. Corrige in-place via PATCH WordPress.
Revisa: gramática, estilo, dados, SEO básico.
NÃO: rejeitar, despublicar, bloquear, solicitar aprovação.

### 5.4 Consolidador

**Lógica por capas de concorrentes:**
- 0 fontes nossas → acionar Reporter
- 1 fonte → REESCREVER com ângulo editorial
- 2+ fontes → CONSOLIDAR em análise

### 5.5 Curador Homepage

**6 Zonas:** Manchete (layout variável), Destaques (grid adaptativo), Por Editoria (carrosséis), Mais Lidas (analytics), Opinião/Análise, Regional.

**Layouts:** Normal (2/3 + sidebar), Destaque Amplo (full sem sidebar), Breaking (full-width banner vermelho).

**ACF Options + REST API** para controle dinâmico.

### 5.6 Pauteiro (Inteligência Paralela)

NÃO é entry point. NÃO filtra conteúdo. Detecta trending, gera briefings de pauta via Kafka.

### 5.7 Editor-Chefe (Observador)

Ciclo 1h. Analisa métricas, compara cobertura, identifica gaps. NÃO aprova, NÃO bloqueia.

### 5.8 Monitor Concorrência

Scan capas (G1, UOL, Folha, Estadão, CNN) a cada 30min. TF-IDF gap analysis.
Gaps → Kafka → Reporters/Consolidador diretamente.

### 5.9 Focas + Monitor Sistema

Focas: health checks 648+ fontes, adaptive polling, discovery. NUNCA desativa.
Monitor: throughput + health. Custo como informação, nunca bloqueio.

---

## 6. CAMADA DE INGESTÃO PARALELA

### 6.1 Dois Tipos de Coletores

**RSS:** feedparser + HTTPX com ETag/If-Modified-Since. Timeout 15s.
**Scraper:** Config de seletores CSS por fonte. HTTPX simples ou Playwright headless. Timeout 30s/60s.

### 6.2 Worker Loop com Isolamento Total

```python
async def worker_loop(worker_id):
    while True:
        try:
            source = await kafka_consumer.next()
            articles = await collect(source)
            for article in articles:
                await kafka_producer.send("raw-articles", article)
        except Exception as e:
            logger.error(f"Worker {worker_id}: {e}")
            mark_for_retry(source, delay=30)
            continue  # NÃO levanta exceção
```

### 6.3 Deduplicação 4 Camadas

| Camada | Técnica | Custo |
|--------|---------|-------|
| 1 | HTTP ETag / 304 | Zero |
| 2 | Redis SET URLs (TTL 72h) | O(1) |
| 3 | SHA-256 hash (título+data+url) | O(1) PG |
| 4 | SimHash LSH (near-duplicate) | Clustering |

---

## 7. CONTEXT ENGINEERING

### 7.1 Framework Write/Select/Compress/Isolate

| Estratégia | Aplicação V3 |
|-----------|-------------|
| **WRITE** | Scratchpads Redis por agente, memória episódica pgvector, checkpointing LangGraph |
| **SELECT** | Just-in-time retrieval (não carregar catálogo inteiro), progressive disclosure, RAG ferramentas |
| **COMPRESS** | Compactação 85%, tool result clearing, sumarização handoffs (max 1.500 tokens) |
| **ISOLATE** | Janelas de contexto independentes por agente, sandbox imagens, estado modular |

### 7.2 Memória em 3 Camadas

| Camada | Storage | TTL | Conteúdo |
|--------|---------|-----|----------|
| Curto Prazo | Context window | Duração do ciclo | System prompt + mensagens + tool results |
| Trabalho | Redis | 1-24h | Scratchpads, quotas, circuit breaker |
| Longo Prazo | PostgreSQL + pgvector | 7-365 dias | Knowledge base, episódica, perfis fonte |

### 7.3 Modos de Falha Mitigados

- **Context Poisoning:** Validação + quarentena, checksums semânticos, thread limpo
- **Context Distraction:** Compactação agressiva, regra dos 3 ciclos, métricas novidade
- **Context Confusion:** Single source of truth, RAG ferramentas, max 15-20 tools/fase
- **Context Clash:** Poda, versionamento prompts, prioridade explícita

---

## 8. SCHEMA PostgreSQL

```sql
CREATE TABLE artigos (
    id SERIAL PRIMARY KEY,
    wp_post_id INTEGER UNIQUE,
    url_fonte TEXT NOT NULL,
    url_hash CHAR(64) UNIQUE,
    titulo TEXT NOT NULL,
    editoria VARCHAR(50),
    urgencia VARCHAR(20),
    score_relevancia FLOAT,
    publicado_em TIMESTAMPTZ DEFAULT NOW(),
    revisado BOOLEAN DEFAULT FALSE,
    imagem_aplicada BOOLEAN DEFAULT FALSE,
    fonte_nome VARCHAR(200)
);

CREATE TABLE fontes (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200),
    url TEXT UNIQUE,
    tipo VARCHAR(20),  -- 'rss' | 'scraper'
    tier VARCHAR(20),  -- 'vip' | 'padrao' | 'secundario'
    config_scraper JSONB,
    polling_interval_min INTEGER DEFAULT 30,
    ultimo_sucesso TIMESTAMPTZ,
    ultimo_erro TEXT,
    ativa BOOLEAN DEFAULT TRUE  -- NUNCA false automaticamente
);

CREATE TABLE memoria_agentes (
    id SERIAL PRIMARY KEY,
    agente VARCHAR(50),
    tipo VARCHAR(20),  -- 'semantica' | 'episodica'
    conteudo JSONB,
    embedding vector(1536),
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    relevancia_score FLOAT DEFAULT 0.5,
    ttl_dias INTEGER DEFAULT 90
);

CREATE TABLE llm_health_log (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(30),
    model VARCHAR(100),
    success BOOLEAN,
    latency_ms INTEGER,
    error_type VARCHAR(50),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 9. TÓPICOS KAFKA

| Tópico | Particionamento | Producers | Consumers |
|--------|----------------|-----------|-----------|
| fonte-assignments | fonte_id | Feed Scheduler | Workers |
| raw-articles | publisher_id | Workers | Classificador |
| classified-articles | categoria | Classificador | Reporter Pool |
| article-published | post_id | Reporter | Fotógrafo, Revisor, Curador, Monitor |
| pautas-especiais | editoria | Pauteiro | Reporter Pool |
| pautas-gap | urgencia | Consolidador, Monitor | Reporter Pool |
| consolidacao | tema_id | Monitor Concorrência | Consolidador |
| homepage-updates | — | Curador | Monitor Sistema |
| breaking-candidate | — | Monitor Concorrência | Curador Homepage |

---

## 10. ESTRUTURA DE DIRETÓRIOS V3

```
brasileira/
├── agents/
│   ├── base.py                    # BaseAgent V3 com memória real
│   ├── reporter.py                # Reporter (escreve + publica)
│   ├── fotografo.py               # Pipeline imagem 4 tiers
│   ├── revisor.py                 # QA pós-publicação
│   ├── consolidador.py            # Reescrever/consolidar
│   ├── curador_homepage.py        # Homepage + layouts dinâmicos
│   ├── pauteiro.py                # Inteligência de pautas
│   ├── editor_chefe.py            # Observador estratégico
│   ├── monitor_concorrencia.py    # Gap analysis
│   ├── monitor_sistema.py         # Health + throughput
│   └── focas.py                   # Gerenciamento de fontes
├── ingestion/
│   ├── feed_scheduler.py
│   ├── rss_collector.py
│   ├── scraper_collector.py
│   ├── deduplicator.py
│   └── worker_pool.py
├── classification/
│   ├── classifier.py
│   └── models/
├── llm/
│   ├── smart_router.py
│   ├── health_tracker.py
│   ├── circuit_breaker.py
│   └── tier_config.py
├── integrations/
│   ├── wordpress_client.py
│   ├── kafka_client.py
│   ├── redis_client.py
│   ├── postgres_client.py
│   └── image_apis/
│       ├── pexels.py
│       ├── unsplash.py
│       ├── wikimedia.py
│       ├── flickr.py
│       └── agencia_brasil.py
├── memory/
│   ├── semantic.py
│   ├── episodic.py
│   ├── working.py
│   └── scratchpad.py
├── observability/
│   ├── tracing.py
│   ├── metrics.py
│   └── alerts.py
├── config/
│   ├── sources.yaml               # 648+ fontes estruturadas
│   ├── categories.yaml            # 16 macrocategorias
│   ├── prompts/                   # System prompts por agente
│   └── homepage_zones.yaml
├── wordpress/
│   ├── template-homepage.php
│   ├── zones/
│   └── acf-setup.php
├── migrations/
│   ├── 001_initial_schema.sql
│   └── 002_indexes_views.sql
├── tests/
│   ├── test_router.py
│   ├── test_reporter.py
│   ├── test_ingestion.py
│   └── test_dedup.py
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 11. PADRÕES DE RESILIÊNCIA

### Circuit Breaker
- 10% falha em janela 30s → abre circuito
- Cooldown 5min → half-open (1 tentativa)
- Skip modelo, NÃO retorna erro

### Retry com Backoff
- Exponential backoff + jitter (max 3 retries)
- Após 3: Dead Letter Queue, NÃO trava pipeline

### Backpressure
- Kafka consumer groups com max.poll.records
- Token bucket para custo (sem bloqueio, apenas alert)
- Agente lento → Kafka acumula, outros continuam

---

## 12. MÉTRICAS-ALVO

| Métrica | Alvo | Alerta |
|---------|------|--------|
| Artigos publicados/hora | ≥ 40 | < 20 |
| Tempo médio publicação | < 60s | > 120s |
| Fontes processadas/ciclo | 648+ | < 600 |
| Taxa sucesso LLM | > 95% | < 90% |
| Artigos sem imagem | 0% | > 5% |
| Cobertura 16 categorias | 100% | Alguma com 0 em 2h |
| Latência homepage update | < 2 min | > 5 min |
| Custo por artigo | < $0.02 | > $0.05 |

---

## 13. CHECKLIST DE IMPLEMENTAÇÃO (Prioridade)

### P1 — Core Pipeline (PRIMEIRO)
- [ ] Docker Compose: Kafka + Redis + PostgreSQL + pgvector
- [ ] SmartLLMRouter: 7 provedores, health scoring, fallback cascata
- [ ] Worker pool: RSS + Scrapers com isolamento total
- [ ] Deduplicação 4 camadas
- [ ] Reporter: contextualizar → redigir → SEO → publicar direto WP
- [ ] Kafka topics configurados
- [ ] PostgreSQL schema completo
- [ ] Classificador ML local

### P2 — Agentes Pós-Publicação
- [ ] Fotógrafo: 4 tiers + queries PREMIUM + reformulação
- [ ] Revisor: correção in-place, NUNCA rejeita
- [ ] Consolidador: lógica 0/1/2+ por capas

### P3 — Curadoria e Inteligência
- [ ] Curador Homepage: 6 zonas + ACF + layouts dinâmicos
- [ ] Templates PHP adaptativos
- [ ] Pauteiro: trending + pautas especiais

### P4 — Observação e Estratégia
- [ ] Editor-Chefe: analytics + gaps
- [ ] Monitor Concorrência: scan capas
- [ ] Monitor Sistema: health + throughput
- [ ] Focas: fontes + discovery

### P5 — Observabilidade e Context Engineering
- [ ] OpenTelemetry tracing por artigo
- [ ] Dashboard métricas
- [ ] Alertas automáticos
- [ ] Sistema memória 3 camadas
- [ ] Compressão de contexto

---

## 14. REGRAS ABSOLUTAS (NUNCA VIOLAR)

1. **Publicar primeiro, revisar depois**
2. **Sem aprovação antes de publicação**
3. **100% das fontes processadas — NUNCA desativar**
4. **Nenhuma notícia sem imagem**
5. **Homepage com inteligência PREMIUM**
6. **Roteador inteligente, não engessado**
7. **Sem modelos locais — apenas APIs**
8. **Budgets informam, NUNCA bloqueiam**

---

## 15. REFERÊNCIA: BRIEFINGS INDIVIDUAIS DISPONÍVEIS

| Briefing | Escopo |
|----------|--------|
| briefing-implementacao-brasileira-news-v3.md | Implementação completa V3 |
| context-engineering-brasileira-news.md | Diretrizes context engineering |
| briefing-reporter-v3.md | Reporter agent |
| briefing-fotografo-v3.md | Fotógrafo/pipeline imagens |
| briefing-revisor-v3.md | Revisor QA |
| briefing-consolidador-v3.md | Consolidador multi-fonte |
| briefing-curador-homepage-v3.md | Curador homepage |
| briefing-pauteiro-v3.md | Pauteiro inteligência |
| briefing-editor-chefe-v3.md | Editor-Chefe observador |
| briefing-monitor-concorrencia-v3.md | Monitor concorrência |
| briefing-monitor-focas-v3.md | Focas + fontes |
| briefing-classificador-kafka-v3.md | Classificador Kafka |
| briefing-smart-llm-router-v3.md | SmartLLMRouter |

---

*Documento compilado a partir da auditoria de 329 bugs, análise de 20 arquivos V2, benchmarking de 6 sistemas editoriais em produção, e 13 briefings técnicos V3.*
