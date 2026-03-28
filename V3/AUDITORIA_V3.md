# AUDITORIA COMPLETA V3 — brasileira.news

**Data:** 2026-03-26
**Escopo:** Todos os 12 componentes + shared + infraestrutura
**Objetivo:** Avaliar implementação vs. spec para funcionamento TIER 1

---

## RESUMO EXECUTIVO

| Métrica | Valor |
|---------|-------|
| Componentes planejados | 13 (shared + 12 agentes) |
| Componentes com código | 13/13 (100%) |
| Componentes funcionais em produção | **0/12** (0%) |
| Bugs críticos encontrados | **38** |
| Bugs de alta severidade | **29** |
| Bugs de média severidade | **42** |
| Total de issues | **120+** |

### Veredito: A V3 é um **esqueleto estrutural** — toda a arquitetura de diretórios e scaffolding existe, mas nenhum componente está pronto para produção. Os componentes P1-P2 (pipeline mínimo) requerem trabalho significativo antes do primeiro artigo ser publicado end-to-end.

---

## 1. MAPA DE IMPLEMENTAÇÃO — O QUE FOI vs. O QUE NÃO FOI

### Legenda: ✅ Implementado | ⚠️ Parcial/Stub | ❌ Ausente

### 1.1 Shared Library (P1)

| Feature | Status | Detalhe |
|---------|--------|---------|
| config.py (AppConfig) | ⚠️ | Funciona mas falta ProviderConfig, WP DB fields, per-provider api_base |
| kafka_client.py | ⚠️ | Funciona mas **sem lz4**, acks=1 (risco perda), sem retry, send() não aguarda confirmação |
| redis_client.py | ⚠️ | 4 linhas — sem pool config, sem health check, sem retry |
| db.py | ⚠️ | Cria pool mas sem retry na conexão, sem migration runner |
| wp_client.py | ⚠️ | Tem backoff mas GET não suporta query params, retorna `dict` quando WP retorna `list` |
| memory.py | ❌ | **Crítico: write-only** — tem add_semantic/add_episodic mas ZERO métodos de query/busca |
| schemas.py | ⚠️ | Só cobre router + worker_pool. Faltam schemas para 7 dos 9 Kafka topics |

### 1.2 Smart Router (P1)

| Feature | Status | Detalhe |
|---------|--------|---------|
| 3 tiers (PREMIUM/PADRAO/ECONOMICO) | ✅ | Correto |
| Health scoring (50/30/20) | ✅ | Fórmula correta |
| Cascading fallback tier→tier | ✅ | PREMIUM→PADRAO→ECONOMICO funciona |
| last_resort (any alive model) | ❌ | **Ausente — AllProvidersFailedError é imediato** |
| 7 providers | ⚠️ | Declarados mas **4/7 falham** (xAI, Perplexity, DeepSeek, Alibaba) — sem api_base |
| KeyManager com rate-limit awareness | ❌ | Round-robin primitivo, sem cooldown por key |
| Error classification (rate_limit/billing/auth) | ❌ | Só captura nome da exceção |
| _log_health fire-and-forget | ❌ | await direto — falha PG mata request em andamento |
| Cost tracker completo | ⚠️ | Só 10/22 modelos têm pricing |

### 1.3 Worker Pool (P2)

| Feature | Status | Detalhe |
|---------|--------|---------|
| 30 async workers | ✅ | Configurável |
| FeedScheduler | ⚠️ | Funciona mas `mark_processed()` nunca é chamado → **fontes processadas 2x por ciclo** |
| RSS Fetcher com ETag/304 | ⚠️ | ETag salvo mas `redis.get()` retorna bytes, não str → headers corrompidos |
| Scraper Engine (Playwright) | ⚠️ | Race condition no `_ensure_browser`, sem rate-limiting por domínio |
| Dedup Layer 1: ETag | ⚠️ | No RSSFetcher mas não integrado no DeduplicationEngine |
| Dedup Layer 2: Redis URL set | ✅ | Funciona (mas TTL é resetado a cada artigo → nunca expira) |
| Dedup Layer 3: SHA-256 hash | ✅ | Funciona |
| Dedup Layer 4: SimHash LSH | ❌ | **O(N) brute-force** em vez de LSH. Index nunca rebuilt, cresce sem limite |
| Kafka lz4 compression | ❌ | Ausente |

### 1.4 Classificador (P2)

| Feature | Status | Detalhe |
|---------|--------|---------|
| ML classifier (sentence-transformers) | ❌ | **CRÍTICO: usa keyword matching** — a exata abordagem que a V3 deveria substituir |
| NER (spaCy pt_core_news_lg) | ❌ | **CRÍTICO: usa 3 regex hardcoded** com ~9 orgs e ~6 locais |
| Relevance scoring | ⚠️ | Funciona mas `fonte_tier` recebe tipo_coleta ("rss") em vez de tier ("vip") |
| Batch processing (50 msgs) | ❌ | Processa 1 mensagem por vez, sequencialmente |
| Manual Kafka commit | ❌ | Auto-commit (risco de perda de mensagens) |
| Dead Letter Queue | ❌ | Ausente — 1 mensagem malformada mata o consumer |
| LLM fallback (confidence < 0.6) | ❌ | Dead code — llm_fallback é sempre None |
| 16 macrocategorias → WP IDs | ⚠️ | `ultimas_noticias` mapeia WP ID 17 (spec diz 1) |

### 1.5 Reporter (P2)

| Feature | Status | Detalhe |
|---------|--------|---------|
| LangGraph StateGraph | ❌ | Plain async methods |
| Content extraction (trafilatura→newspaper4k→HTML→resumo) | ❌ | Só `BeautifulSoup.stripped_strings` (captura nav, footer, ads) |
| RAG contextualização (pgvector top-3) | ❌ | Totalmente ausente |
| LLM rewriting (PREMIUM) | ⚠️ | Funciona mas sem fonte attribution, max_tokens=1200 (baixo), sem retry |
| SEO optimization | ⚠️ | Funciona básico |
| Publish status="publish" | ✅ | **Correto — única regra #1 cumprida** |
| Consume 3 topics (classified + pautas-especiais + pautas-gap) | ❌ | Só consome classified-articles |
| Worker pool de N LangGraph runners | ❌ | Single-threaded sequencial |
| Memory 3-layer | ❌ | Zero memória |

### 1.6 Fotógrafo (P3)

| Feature | Status | Detalhe |
|---------|--------|---------|
| Tier 1: Extração original (5-level hierarchy) | ❌ | Só regex og:image, e **html_fonte nunca é passado** → sempre falha |
| Tier 2: Stock APIs (Pexels/Unsplash/etc) | ❌ | **STUB — retorna URL fake** `images.example.com` |
| Tier 3: AI generativa (gpt-image-1/Flux.2) | ❌ | **STUB — retorna URL fake** `ai-images.example.com` |
| Tier 4: Placeholder temático | ⚠️ | Só 3/16 editorias, WP media IDs hardcoded |
| CLIP validation | ❌ | **Fake — compara tokens do texto com tokens da URL** (não carrega modelo) |
| Query reformulation (broaden→pivot) | ❌ | Ausente |
| Ad CDN filtering | ❌ | Ausente |
| Rejection cache (Redis) | ❌ | Ausente |
| LangGraph StateGraph | ❌ | Ausente |

### 1.7 Revisor (P3)

| Feature | Status | Detalhe |
|---------|--------|---------|
| PATCH in-place (nunca rejeita) | ⚠️ | Faz PATCH mas **raises RuntimeError no lock** — é um bloqueio |
| Grammar check (LLM PADRAO) | ❌ | **2 regras regex** — zero uso de LLM |
| Style check (LLM PADRAO) | ❌ | Só remove `!!` e capitaliza primeira letra |
| Fact check | ❌ | Totalmente ausente |
| SEO review | ❌ | Só truncamento de length |
| LangGraph StateGraph | ❌ | Ausente |
| Idempotência | ❌ | Pode aplicar double-corrections |

### 1.8 Consolidador (P4)

| Feature | Status | Detalhe |
|---------|--------|---------|
| 0 sources → pautas-gap | ❌ | **Producer Kafka nunca iniciado** → crash na primeira mensagem |
| 1 source → REWRITE (LLM PREMIUM) | ⚠️ | Funciona se producer estivesse ok |
| 2+ sources → CONSOLIDATE | ⚠️ | Funciona se producer estivesse ok |
| json.loads sem error handling | ❌ | LLM response malformada mata o serviço |
| LangGraph StateGraph | ❌ | Ausente |

### 1.9 Curador Homepage (P4)

| Feature | Status | Detalhe |
|---------|--------|---------|
| 6 zonas editoriais | ⚠️ | Parcial — manchete/destaques/mais_lidas/editorias, falta Opinião e Regional |
| 3 layouts (NORMAL/AMPLO/BREAKING) | ⚠️ | Declarados mas breaking nunca ativa (breaking-candidate sem post_id) |
| LLM PREMIUM scoring | ✅ | Correto — task_type="homepage_score" |
| Atomic diff (ACF) | ⚠️ | Implementado mas type mismatch causa writes desnecessários |
| Redis distributed lock | ⚠️ | TTL 600s (spec diz 120s) |
| Adaptive frequency (5/15/30 min) | ❌ | Hardcoded 300s fixo |
| `article-published` consumer | ❌ | Só cycle periódico |
| Dedup posts entre zonas | ❌ | mais_lidas pode duplicar manchete/destaques |

### 1.10 Pauteiro (P4)

| Feature | Status | Detalhe |
|---------|--------|---------|
| 5 monitoring loops independentes | ❌ | **ZERO loops implementados** |
| Google Trends API | ❌ | Ausente |
| X/Twitter API | ❌ | Ausente |
| Reddit API | ❌ | Ausente |
| News agencies (AP/AFP/Reuters) | ❌ | Ausente |
| Circuit breaker | ❌ | Ausente |
| Signal aggregation | ⚠️ | Scaffolding existe mas recebe `[]` — produz zero output |

### 1.11 Editor-Chefe (P5)

| Feature | Status | Detalhe |
|---------|--------|---------|
| Coverage analysis | ⚠️ | Existe mas recebe `[]` → **publica 16 gaps falsos por ciclo** (384/dia) |
| GA4 API integration | ❌ | Totalmente ausente |
| LLM analysis (PADRAO) | ❌ | Sem router, sem LLM |
| Observer only (nunca bloqueia) | ⚠️ | Nunca bloqueia mas **inunda pautas-gap com falsos positivos** |
| Editorial report generation | ❌ | Ausente |

### 1.12 Monitor Concorrência (P5)

| Feature | Status | Detalhe |
|---------|--------|---------|
| Playwright scanning 8 portais | ⚠️ | Código existe mas **roda uma vez e termina** (sem loop) |
| Portal-specific CSS selectors | ✅ | 8 portais com seletores customizados |
| TF-IDF gap analysis | ⚠️ | Existe mas `nossos_titulos=[]` → **retorna zero gaps** (logic inversion) |
| 3 routing decisions (GAP/PARTIAL/BREAKING) | ⚠️ | Código existe mas schema incompatível com Consolidador |
| Parallel scanning (asyncio.gather) | ❌ | Sequencial |

### 1.13 Monitor Sistema + Focas (P5)

| Feature | Status | Detalhe |
|---------|--------|---------|
| Health monitoring (60s) | ❌ | Ciclo de 300s, não 60s |
| Throughput SLO (≥40/hr) | ⚠️ | Lógica existe mas recebe `artigos_ultima_hora=0` → sempre "critico" |
| Focas adaptive polling | ⚠️ | Lógica correta mas `fontes=[]` → nunca executa |
| Source discovery | ❌ | Ausente |
| Prometheus metrics | ❌ | Ausente |

---

## 2. BUGS CRÍTICOS — BLOQUEIAM PRODUÇÃO

### 2.1 Infraestrutura (6 críticos)

| # | Bug | Impacto | Arquivo |
|---|-----|---------|---------|
| I1 | **Networks isoladas**: docker-compose.infra.yml usa `v3-infra`, agents usam `v3-net` | Agentes não conseguem conectar a Kafka/Redis/PG | docker-compose*.yml |
| I2 | **langgraph não está no requirements** | Nenhum agente pode usar StateGraph | requirements-base.txt |
| I3 | **pgvector (Python) não está no requirements** | asyncpg não serializa VECTOR columns | requirements-base.txt |
| I4 | **Tabela `artigos` sem coluna `embedding`** e sem 10+ colunas esperadas | Semantic search impossível | 001_schema_base.sql |
| I5 | **PostgreSQL trust auth + porta exposta 0.0.0.0** | BD acessível sem senha da internet | docker-compose.infra.yml |
| I6 | **deploy.sh continua após criar .env template** com CHANGE_ME | Tenta conectar a hosts inexistentes | deploy.sh |

### 2.2 Smart Router (4 críticos)

| # | Bug | Impacto | Arquivo |
|---|-----|---------|---------|
| R1 | **4/7 providers falham** — sem api_base para xAI, Perplexity, DeepSeek, Alibaba | 57% dos providers não funcionam | router.py |
| R2 | **Sem last_resort fallback** | AllProvidersFailedError sem tentar qualquer modelo vivo | router.py |
| R3 | **Sem error classification** | Keys rate-limited são re-tentadas infinitamente | router.py |
| R4 | **Sem KeyManager** | Round-robin sem cooldown por key | router.py |

### 2.3 Pipeline Core (10 críticos)

| # | Bug | Impacto | Arquivo |
|---|-----|---------|---------|
| P1 | **Classifier usa keyword matching**, não sentence-transformers | Classificação ~V2 quality, mata o propósito da V3 | classifier.py |
| P2 | **NER usa 3 regex**, não spaCy | False positives massivos, cobertura mínima | ner_extractor.py |
| P3 | **Content extractor captura página inteira** (nav, footer, ads) | LLM recebe lixo, artigos de baixa qualidade | content_extractor.py |
| P4 | **Reporter sem LangGraph, sem RAG, sem extraction cascade** | Pipeline editorial é sequência de chamadas simples | reporter.py |
| P5 | **Fotografo Tier 2 e 3 são stubs** (URLs fake) | Imagens serão broken links | tier2_stocks.py, tier3_generative.py |
| P6 | **CLIP validator é fake** (compara tokens de URL) | Zero validação real de relevância | clip_validator.py |
| P7 | **Revisor não usa LLM** | Só 2 regex — detecta ~0% de erros reais | grammar/style/seo_checker.py |
| P8 | **Memory write-only** — sem query_semantic/query_episodic | Agentes não podem consultar memória passada | memory.py |
| P9 | **Kafka auto-commit + auto_offset_reset=latest** | Mensagens perdidas durante downtime + crash | kafka_client.py |
| P10 | **1 mensagem por vez no classificador** (spec: batch 50) | Throughput ~10x abaixo do target | classificador/__main__.py |

### 2.4 Componentes Não-Funcionais (8 críticos)

| # | Bug | Impacto | Arquivo |
|---|-----|---------|---------|
| N1 | **Consolidador: producer Kafka nunca iniciado** | Crash na 1ª mensagem | consolidador/__main__.py |
| N2 | **Pauteiro: ZERO monitoring loops** (Google, X, Reddit, agencies) | Produz zero pautas especiais | pauteiro/ |
| N3 | **Editor-Chefe: recebe [] → publica 16 gaps falsos/ciclo** | 384 falsas pautas-gap/dia inundam o Reporter | editor_chefe/__main__.py |
| N4 | **Monitor Conc.: roda uma vez e termina** | Sem monitoramento contínuo | monitor_conc/__main__.py |
| N5 | **Monitor Conc.: gap_analysis retorna [] quando nossos_titulos=[]** | Lógica invertida — deveria ser "tudo é gap" | gap_analysis.py |
| N6 | **Schema mismatch Monitor Conc. ↔ Consolidador** | {portal,titulo,url} vs {tema_id,tema_descricao,...} — KeyError | monitor.py ↔ consolidador.py |
| N7 | **breaking-candidate sem post_id** | Curador Homepage nunca ativa layout BREAKING | monitor.py ↔ curador.py |
| N8 | **Monitor Sistema: dados dummy (0,[], [])** → sempre "critico" | Zero monitoramento real | monitor_sistema/__main__.py |

---

## 3. GAPS SISTÊMICOS — AFETAM TODOS OS COMPONENTES

| # | Gap | Componentes Afetados |
|---|-----|---------------------|
| S1 | **Zero LangGraph StateGraph** em qualquer componente | Todos os 12 agentes |
| S2 | **Zero semantic memory (pgvector queries)** | Todos os 12 agentes |
| S3 | **Zero DLQ (Dead Letter Queue)** | Todos os consumers Kafka |
| S4 | **Zero graceful shutdown (SIGTERM/SIGINT handlers)** | Todos os 12 agentes |
| S5 | **Zero Prometheus/OpenTelemetry metrics** | Todos os 12 agentes |
| S6 | **Zero Pydantic validation em mensagens Kafka inbound** | Todos os consumers |
| S7 | **1 mensagem malformada mata qualquer consumer** (sem try/except per-msg) | Todos os consumers |
| S8 | **json.loads sem error handling em respostas LLM** | Reporter, Fotografo, Consolidador, Curador, Pauteiro |

---

## 4. ISSUES DE SEGURANÇA

| Severidade | Issue | Arquivo |
|------------|-------|---------|
| CRÍTICO | PostgreSQL trust auth + porta 0.0.0.0:5432 | docker-compose.infra.yml |
| ALTO | Redis sem senha + porta exposta | docker-compose.infra.yml |
| ALTO | Kafka/Zookeeper sem auth + portas expostas | docker-compose.infra.yml |
| ALTO | `COPY . /app` em 7 Dockerfiles pode leak .env | */Dockerfile |
| MÉDIO | Containers rodam como root | Todos os Dockerfiles |
| MÉDIO | Zero TLS entre serviços | Todos |
| BAIXO | Senha default hardcoded no config.py | shared/config.py |

---

## 5. PLANO DE AÇÃO PARA TIER 1

Para o pipeline mínimo funcionar (fonte → classificação → redação → publicação no WordPress), estes são os fixes necessários em ordem de prioridade:

### FASE 0: Infraestrutura (1-2 dias)

1. **Unificar Docker networks** — todos na `v3-net`
2. **Corrigir .env defaults** para hostnames Docker (kafka:29092, postgres:5432, redis:6379)
3. **Adicionar ao requirements-base.txt**: `langgraph`, `pgvector`, `trafilatura`, `newspaper4k`, `numpy`
4. **Corrigir migrations** — adicionar colunas faltantes em `artigos` e `fontes`, vector index
5. **Corrigir deploy.sh** — exit após criar .env template
6. **Segurança mínima** — senha no PG, requirepass no Redis, bind só localhost
7. **Criar .dockerignore** excluindo .env, docs/, tests/, __pycache__/

### FASE 1: Smart Router funcional (1-2 dias)

8. **Adicionar api_base** para xAI, Perplexity, DeepSeek, Alibaba
9. **Implementar last_resort** — tentar qualquer modelo com health > 0
10. **Error classification** — rate_limit, billing, auth, timeout, server_error
11. **KeyManager** com cooldown por key e rate-limit awareness
12. **_log_health fire-and-forget** via asyncio.create_task()

### FASE 2: Kafka Client robusto (1 dia)

13. **lz4 compression** no producer
14. **auto_offset_reset="earliest"**
15. **enable_auto_commit=False** + manual commit
16. **send_and_wait()** em vez de send()
17. **Per-message try/except** em TODOS os consumers

### FASE 3: Worker Pool confiável (2-3 dias)

18. **Corrigir mark_processed** — scheduler não re-envia fontes
19. **Corrigir Redis ETag** — decode bytes para str
20. **SimHash: implementar LSH real** ou pelo menos cap + rebuild periódico
21. **Incluir fonte tier** no payload raw-articles
22. **Signal handlers** para graceful shutdown

### FASE 4: Classificador real (3-5 dias)

23. **Implementar ML classifier** com sentence-transformers + centroid prototypes
24. **Implementar NER** com spaCy pt_core_news_lg
25. **Batch processing** — getmany(max_records=50) + asyncio.gather
26. **DLQ** para falhas
27. **Corrigir WP category IDs** (ultimas_noticias → 1)
28. **LLM fallback real** quando confidence < 0.6

### FASE 5: Reporter funcional (3-5 dias)

29. **Content extraction cascade** — trafilatura → newspaper4k → BS4 → resumo
30. **LangGraph StateGraph** com checkpointing
31. **RAG contextualização** via pgvector
32. **Source attribution** obrigatória (link HTML no 1º/2º parágrafo)
33. **Consumir 3 topics** (classified + pautas-especiais + pautas-gap)
34. **max_tokens adequado** (2000+) + retry com JSON parse

### FASE 6: Memory funcional (1-2 dias)

35. **Implementar query_semantic()** — pgvector cosine similarity search
36. **Implementar query_episodic()** — filter by agent/time
37. **Adicionar delete_working()** e garbage collection
38. **Integrar memory** em Reporter, Classificador

### FASE 7: Fotografo + Revisor (P3) (5-7 dias)

39. **Tier 1: 5-level extraction hierarchy** + ad CDN filtering
40. **Tier 2: APIs reais** (Pexels, Unsplash, Wikimedia)
41. **Tier 3: gpt-image-1 ou Flux.2** + label "AI gerada"
42. **CLIP real** com modelo carregado
43. **Revisor: grammar/style/SEO com LLM PADRAO**
44. **Revisor: remover RuntimeError no lock** → skip gracefully

---

## 6. ESTIMATIVA DE COMPLETUDE POR COMPONENTE

| Componente | Infra OK | Lógica OK | Integração OK | Produção-ready | Completude |
|------------|----------|-----------|---------------|---------------|------------|
| shared/ | ⚠️ | ⚠️ | ⚠️ | ❌ | **35%** |
| smart_router/ | ⚠️ | ⚠️ | ❌ | ❌ | **40%** |
| worker_pool/ | ⚠️ | ⚠️ | ⚠️ | ❌ | **45%** |
| classificador/ | ⚠️ | ❌ | ❌ | ❌ | **15%** |
| reporter/ | ⚠️ | ❌ | ❌ | ❌ | **20%** |
| fotografo/ | ⚠️ | ❌ | ❌ | ❌ | **10%** |
| revisor/ | ⚠️ | ❌ | ❌ | ❌ | **15%** |
| consolidador/ | ⚠️ | ⚠️ | ❌ | ❌ | **25%** |
| curador_homepage/ | ⚠️ | ⚠️ | ❌ | ❌ | **30%** |
| pauteiro/ | ❌ | ❌ | ❌ | ❌ | **5%** |
| editor_chefe/ | ❌ | ❌ | ❌ | ❌ | **10%** |
| monitor_conc/ | ⚠️ | ⚠️ | ❌ | ❌ | **25%** |
| monitor_sistema/ | ⚠️ | ⚠️ | ❌ | ❌ | **20%** |
| **Infraestrutura** | ⚠️ | — | ❌ | ❌ | **30%** |
| **MÉDIA GERAL** | | | | | **~23%** |

---

## 7. O QUE ESTÁ BOM

Nem tudo é negativo. Estes elementos estão corretos e podem ser preservados:

1. **Arquitetura de diretórios** — cada agente é um módulo isolado com `__main__.py`, pronto para Docker
2. **Tier system do SmartRouter** — 3 tiers com cascading fallback (falta só api_base e last_resort)
3. **Health scoring formula** — 50/30/20 implementada corretamente
4. **Pydantic V2 strict mode** nos schemas existentes
5. **Publisher com status="publish"** — regra #1 da V3 cumprida
6. **Focas "never disable" logic** — corretamente nunca desativa fontes
7. **Portal CSS selectors** no Monitor Concorrência — 8 portais com seletores específicos
8. **deploy.sh modo HYBRID** — lógica para Aiven remoto + Kafka local é sofisticada
9. **4-layer dedup architecture** no worker_pool — design correto, implementação precisa de ajuste
10. **Kafka topic topology** — 9 topics com partições adequadas

---

## 8. CONCLUSÃO

A V3 está a **~23% de completude geral**. A estrutura arquitetural é sólida e segue o spec, mas a implementação é predominantemente scaffolding com stubs. Os problemas mais críticos para TIER 1:

1. **Infraestrutura**: Networks isoladas, credentials, requirements faltantes
2. **Smart Router**: 4/7 providers não funcionam
3. **Classificador**: Keyword matching em vez de ML (derrota o propósito da V3)
4. **Reporter**: Sem extraction cascade, sem RAG, sem LangGraph
5. **Fotografo**: Tiers 2+3 são URLs fake
6. **Todos os componentes**: Zero LangGraph, zero DLQ, zero graceful shutdown

O pipeline mínimo (FASE 0-5 do plano de ação) requer implementação substancial antes de produzir o primeiro artigo end-to-end com qualidade aceitável.
