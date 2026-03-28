# COMPREHENSIVE V2 MASTER PLAN SUMMARY
## brasileira.news Multi-Agent System Transformation

**Compiled:** March 23, 2026  
**Status:** Complete strategic plan ready for Phase 0 implementation  
**Total Development Scope:** 24 weeks, 500-700 hours, $210-400/month operational cost

---

## EXECUTIVE SUMMARY

The V2 transformation aims to convert brasileira.news from a monolithic, single-instanced system into a **distributed, hierarchical multi-agent editorial system** with:
- **10+ specialized agents** (Director, 4 Editors, Reporters, Revisor, Photographer, Homepage Curator, Competence Monitor, Source Manager, Metrics Analyst)
- **3-layer memory system** (Redis for hot state, PostgreSQL for medium-term, pgvector for long-term knowledge base)
- **Complete editorial hierarchy** mirroring a professional newsroom
- **LiteLLM unified proxy** replacing custom routing with 20+ API keys across 7 LLM providers
- **100%+ capacity increase** (60-80 articles/day → 200+ articles/day)
- **Cost-neutral or cheaper** ($195-369/month vs $200-510/month current) with massively improved reliability and observability

---

## I. CURRENT SYSTEM DIAGNOSIS

### A. Strengths (Assets to Preserve)
| Component | Value | Status |
|-----------|-------|--------|
| 630+ catalogued news sources | Months of curation | Migrating to dynamic Focas agent |
| 16 macro + 73 subcategories | Proven taxonomy | Preserving in WordPress |
| 6-tier LLM routing with 7 providers | $2-3k dev effort | Migrating to LiteLLM proxy |
| 5-tier image pipeline | Tested hierarchy | Enhancing with LLM-powered selection |
| ~9,180 published articles | 1+ years of backfill data | Converting to knowledge base |
| Bitnami WordPress stack | Proven hosting | Keeping, reducing Python load |

### B. Critical Limitations (11 Major Issues)

1. **Exposed credentials** (hardcoded in 3 files)
2. **No centralized monitoring** (health checks bury alerts in logs)
3. **Disabled image generation** (roteador_ia_imagem() returns None)
4. **Duplicate RSS ingest systems** (Motor Mestre + Motor RSS v2 = dedup risk)
5. **Unbounded cache** (historico_links.txt grows indefinitely)
6. **Editorial tension** (cannot synthesize entertainment sources)
7. **No API budget control** (agents can burn $300+/day)
8. **Fragile scraper dependencies** (breaks on portal redesign)
9. **Zero test coverage** (9,180+ articles published without tests)
10. **No editorial memory** (each cycle isolated, no context, no continuity)
11. **External dependency risk** (Jina Reader fallback with no SLA)

### C. Current Architecture
```
Single AWS LightSail Instance (overcrowded):
├── WordPress + Bitnami (web serving)
├── Motor RSS v2 (398 sources)
├── Motor Scrapers v2 (5 strategies)
├── Motor Consolidado (trending + synthesis)
├── Curator (homepage selection)
├── 6 health check + maintenance scripts
├── MariaDB (state)
└── SQLite (knowledge_db - 9,180 articles, no indexing)
```

---

## II. BENCHMARKING & MARKET VALIDATION

### Reference Systems (2024-2026)

**Hallucination Herald**
- 20 autonomous agents
- $2/day cost (~$60/month)
- Next.js + Supabase + Claude
- Self-reflection + MCP public interface
- 1.7B workflows executed

**Al Jazeera "The Core"**
- Google Cloud + Gemini Enterprise
- Fine-tuned on 50+ years of archives
- 6 pillars: AJ Now, AJ-LLM, AJ Vision, Data Lake, Ops Engine, Academic Arm
- Enterprise-scale reimagining of editorial workflow

**Reuters Lynx Insight**
- Detects financial data patterns
- Writes 2/3 of complex financial stories
- 8-60 min advantage on breaking news

**AP Wordsmith**
- Automated Insights partnership
- 1000s of reports automated
- Deployed since 2014

### Market Validation Findings

- **Hierarchical multi-agent systems outperform flat systems by 11-36%** (Emergent Mind research)
- **93% of Brazilian news sites have no robot.txt blocking AI collection** (LatAm Journalism Review)
- **LangGraph state management + checkpointing** is production-standard for multi-agent workflows
- **Semantic caching reduces LLM costs 30-50%** (Redis + LiteLLM)
- **Prompt caching can reduce input token costs 80-90%** (Anthropic Claude)

---

## III. PROPOSED ARCHITECTURE

### A. 6-Layer Stack

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: ORCHESTRATION (LangGraph + Python 3.11)            │
│  Diretor → Editores → Repórteres → Revisor → Publicador    │
├─────────────────────────────────────────────────────────────┤
│ LAYER 2: LLM SERVICES (LiteLLM Proxy)                        │
│  20+ keys, 7 providers, semantic cache, circuit breaker      │
├─────────────────────────────────────────────────────────────┤
│ LAYER 3: MEMORY & KNOWLEDGE                                  │
│  Redis (curto) ← PostgreSQL (médio) ← pgvector (longo)      │
├─────────────────────────────────────────────────────────────┤
│ LAYER 4: PUBLISHING (WordPress REST API)                    │
│  Authenticated via Application Passwords (no plugins)       │
├─────────────────────────────────────────────────────────────┤
│ LAYER 5: OBSERVABILITY (LangSmith + Prometheus)             │
│  Cost/article, latency/agent, error tracking, dashboards    │
├─────────────────────────────────────────────────────────────┤
│ LAYER 6: INFRASTRUCTURE                                      │
│  Railway (Python backend) + LightSail (WordPress only)      │
└─────────────────────────────────────────────────────────────┘
```

### B. Infrastructure Separation

**Before (monolithic):**
```
LightSail instance:
├── WordPress web server
├── Python scraping/processing processes (competing for CPU/RAM)
├── Health check scripts
├── MariaDB
└── Single point of failure
```

**After (distributed):**
```
Railway (backend Python agents):
├── LangGraph orchestration
├── LiteLLM proxy ($4-20/month)
├── PostgreSQL + pgvector ($25/month via Supabase Pro)
├── Redis cache/state ($10-30/month)
└── Scalable independently

LightSail (WordPress only):
├── WordPress serving web only (reduced load)
├── MariaDB
├── Nginx with rate limiting
└── Reduced resource contention
```

### C. Recommended Technology Stack

| Layer | Technology | Justification |
|-------|-----------|---------------|
| **Orchestration** | LangGraph (Python 3.11+) | Native checkpointing, state management, LangSmith integration |
| **LLM Proxy** | LiteLLM (self-hosted) | 100+ providers, overhead ~3ms, native fallback/circuit-breaker |
| **Short-term memory** | Redis Cloud/Railway | Sub-ms for session state, semantic cache (30-50% LLM reduction) |
| **Medium-term KB** | PostgreSQL + pgvector (Supabase) | ACID, native SQL, p50=31ms on vector search, JOINs with metadata |
| **Event bus** | Redis Pub/Sub (production) → Redis Streams (scale) | Pub/sub for real-time events, streams for persistence |
| **Publishing** | WordPress REST API (keep current) | Preserves all integrations (Yoast, AIOSEO, Newspaper theme) |
| **Backend hosting** | Railway ($5-20/month) | Docker-based, GitHub deploy, PostgreSQL/Redis included |
| **Observability** | LangSmith + Prometheus | Native LangGraph tracing, cost/tokens/latency per agent |
| **Web search** | Tavily API ($30-50/month) | JSON structured, LLM-agnostic, built-in LangGraph integration |
| **Embeddings** | OpenAI text-embedding-3-large | 1536 dims, best Portuguese performance among commercial models |

---

## IV. AGENT SYSTEM DESIGN (10+ Agents)

### A. Hierarchy

```
DIRETOR DE REDAÇÃO (Director)
├─ EDITOR-CHEFE (Editor-in-Chief)
│   ├─ EDITOR POLÍTICA (Political Editor)
│   ├─ EDITOR ECONOMIA (Economics Editor)
│   ├─ EDITOR ESPORTES (Sports Editor)
│   ├─ EDITOR TECNOLOGIA (Tech Editor)
│   └─ [Can dynamically create: EDITOR COPA, EDITOR ELEIÇÕES, etc]
│       ├─ REPÓRTER A (Reporter - beat A)
│       ├─ REPÓRTER B (Reporter - beat B)
│       └─ [Multiple concurrent reporters per editor]
│
├─ REDATOR/REVISOR (Quality Gate)
├─ EDITOR FOTOGRAFIA (Photo Editor)
├─ ASSISTENTE FOTOGRAFIA (Photo Assistant)
├─ PAUTEIRO (Assignment Editor)
│   ├─ Pauteiro Diário (reactive coverage)
│   └─ Pauteiro Estratégico (proactive/calendar)
├─ FOCAS (Source Manager)
├─ CURADOR HOMEPAGE (Homepage Curator)
├─ MONITOR CONCORRÊNCIA (Competence Monitor)
└─ ANALISTA MÉTRICAS (Metrics Analyst)
```

### B. Agent Specifications (Detailed)

#### DIRETOR DE REDAÇÃO (Director)
| Attribute | Value |
|-----------|-------|
| **Frequency** | Every 2-4 hours |
| **LLM Tier** | Premium (Claude Sonnet 4 → GPT-4.1 → Gemini 2.5 Pro) |
| **Responsibilities** | Editorial strategy, resource allocation, agent creation/destruction, line validation |
| **Memory** | Long-term: editorial decisions, coverage patterns, performance by editoria |
| **Tools** | Analytics API, competitor data, cost dashboards, can spawn/kill agents |
| **Outputs** | Editorial directives (JSON), resource reallocation, agent lifecycle commands |

#### EDITOR-CHEFE (Editor-in-Chief)
| Attribute | Value |
|-----------|-------|
| **Frequency** | Every 15-30 minutes (continuous) |
| **LLM Tier** | Intermediate-Premium (Claude Sonnet 4 → GPT-4.1 → Gemini Flash) |
| **Responsibilities** | Real-time production monitoring, quality gate, breaking news coordination |
| **Memory** | Medium-term: last 24h published articles, editorial tone, approval patterns |
| **Tools** | Publishing queue (Redis), quality checklist, recent articles (pgvector), WP REST API (read) |
| **Key difference from current** | Pre-publication gate (current: post-publication curator). Has memory of what was published. |

#### 4 EDITORES DE EDITORIA (Section Editors - Política, Economia, Esportes, Tecnologia)
| Attribute | Value |
|-----------|-------|
| **Frequency** | Every 30-60 minutes |
| **LLM Tier** | Intermediate (Claude Sonnet 4 → Gemini Flash → GPT-4.1) |
| **Responsibilities** | Monitor section sources, detect coverage gaps vs competitors, assign beats to reporters, review articles |
| **Memory** | Medium-term: last 7 days coverage, angles explored, most productive sources |
| **Tools** | Specialized KB for editoria, source monitor, deduplication, WordPress category mapping |
| **Dynamic instantiation** | Director can create EDITOR COPA during World Cup, EDITOR ELEIÇÕES during elections |

#### REPÓRTERES (Reporters - Multiple concurrent)
| Attribute | Value |
|-----------|-------|
| **Trigger** | On-demand (triggered by assignment) |
| **LLM Tier** | Writing: Sonnet 4 / Gemini Flash / GPT-4.1. SEO: Gemini Flash-Lite / Haiku |
| **Responsibilities** | Research, write with context from RAG, generate SEO metadata |
| **Memory** | Short-term: current assignment. Access: KB for previous coverage of topic |
| **Key difference from current** | **Receives RAG context** of previous articles on same topic with instruction "don't repeat angles, maintain consistency" |
| **Tools** | Tavily search API, RSS parser, content extractor, knowledge base RAG |
| **Output** | Complete article (H1, body HTML with H2 FAQ, excerpt, tags, meta description, slug) |

#### REDATOR/REVISOR (Quality Gate - Pre-publication)
| Attribute | Value |
|-----------|-------|
| **Trigger** | Every article before publishing |
| **LLM Tier** | Premium (Claude Sonnet 4) |
| **Responsibilities** | Check editorial rules, plagiarism <40%, consistency with prior coverage, SEO validation |
| **Tools** | Editorial rules prompt, difflib for plagiarism, KB for consistency |
| **Key difference from current** | **Pre-publication** (current: post-publication). Max 2 loops: reject → reporter rewrites. After 2 rejections → "needs human review" |

#### EDITOR FOTOGRAFIA (Photo Editor)
| Attribute | Value |
|-----------|-------|
| **Trigger** | Every article |
| **LLM Tier** | Multimodal (GPT-4.1 → Claude Sonnet 4 → Gemini 2.5 Pro) |
| **Responsibilities** | Context-aware image sourcing, copyright validation |
| **Image source hierarchy** | (1) Original source og:image → (2) Gov sources (Agência Brasil, Senado) → (3) Flickr CC → (4) Wikimedia → (5) Stock (Pexels/Unsplash) → (6) Placeholder |
| **Output** | Image URL + caption + alt text + credit + license |

#### ASSISTENTE FOTOGRAFIA (Photo Assistant)
| Attribute | Value |
|-----------|-------|
| **Trigger** | Every image from Photo Editor |
| **LLM Tier** | Economic (Haiku 3.5) |
| **Responsibilities** | Smart crop (OpenCV face detection), resize to 1200×628 OG, generate caption/alt text |
| **Tools** | OpenCV, PIL/Pillow, BunnyCDN, WordPress media upload |
| **Output** | Processed image (crop+resize), WordPress media ID |

#### PAUTEIRO (Assignment Editor)
**Diário (Reactive - every 1-2 hours):** Google Trends BR RSS, breaking news detection  
**Estratégico (Proactive - daily morning):** Diário Oficial, Chamber/Senate agendas, calendar events

#### FOCAS (Source Manager)
| Attribute | Value |
|-----------|-------|
| **Frequency** | Always-on (not daily like current) |
| **LLM Tier** | Economic (Haiku 3.5 for classification; no LLM for health checks) |
| **Responsibilities** | Monitor source health, adaptive polling frequency, auto-discovery of new sources |
| **Key difference from current** | Continuous monitoring (current: 1x/day at 3-4am). Migrates sources between strategies (RSS ↔ scraping) automatically |
| **Output** | Updated catalog, health reports, new source discovery |

#### CURADOR HOMEPAGE (Homepage Curator)
| Attribute | Value |
|-----------|-------|
| **Frequency** | Every 30-60 minutes |
| **LLM Tier** | Curation: Gemini 2.5 Flash. Headline: Claude Sonnet 4 (premium decision) |
| **Responsibilities** | Select & position 14 homepage slots, maintain thematic diversity, avoid repetition, apply home-* tags |
| **Key difference from current** | **Editorial memory** to maintain narrative coherence (current: pure scoring) |

#### MONITOR CONCORRÊNCIA (Competence Monitor)
| Attribute | Value |
|-----------|-------|
| **Frequency** | Every 1-2 hours |
| **LLM Tier** | Economic: Haiku 3.5 (classification). Intermediate: Sonnet 4 (gap analysis) |
| **Monitors** | 12 portals (G1, UOL, Folha, Estadão, R7, CNN Brasil, Terra, Metrópoles, AgBr, Poder360, etc) |
| **Detects** | Trending topics (3+ portals), coverage gaps, competitive angles |
| **Output** | Hot themes not covered, unexplored angles, volume by editoria, trending list |

#### ANALISTA MÉTRICAS (Metrics Analyst)
| Attribute | Value |
|-----------|-------|
| **Frequency** | Every 4-6 hours |
| **LLM Tier** | Intermediate (Gemini 2.5 Flash) |
| **Responsibilities** | Connect GA Data API v2 + Search Console to editorial decisions |
| **Output** | Performance reports, high-performing article patterns, traffic alerts |

---

## V. MEMORY SYSTEM (3 LAYERS)

### A. Layer 1: Short-Term (Redis - <24h TTL)
```
editorial:sessao:{cycle_id}           → Current cycle state
editorial:fila_publicacao             → Posts awaiting publish (List)
editorial:trending                    → Active trending topics (TTL: 2h)
editorial:artigos_em_progresso        → In-progress assignments
llm:cache:semantic:{hash}             → Semantic cache (85% similarity)
agente:estado:{agent_id}              → Agent state (idle/processing/error)
pubsub:editorial:*                    → Event channels
  :novas_noticias
  :concorrentes
  :trending
  :aprovacoes
  :publicados
```

### B. Layer 2: Medium-Term (PostgreSQL - 30-90 days)
```sql
decisoes_editoriais         → Editorial decisions + outcomes (for Diretor/Editor-Chefe memory)
cobertura_topicos           → Topic coverage tracking (avoid saturation)
sessoes_agentes             → Agent session logs with performance metrics
calendario_editorial        → Proactive calendar (gov agendas, events, holidays)
analise_concorrencia        → Competitor headline tracking (last 7 days)
```

### C. Layer 3: Long-Term (PostgreSQL + pgvector - Permanent)
```sql
artigos                     → All published articles with embeddings
  └─ embedding (vector 1536) for semantic search
  └─ data_publicacao (temporal weighting: 7-day half-life)
  └─ entidades (people, orgs, locations via LLM extraction)
  └─ topicos, angulo_editorial, tipo (breaking vs evergreen)
  └─ metricas (pageviews, time_on_page, bounce_rate)

topico_tracking             → Topic saturation/gaps
catalogo_fontes             → Dynamic source catalog with adaptive polling
```

### D. Key Innovation: Temporal Weighting in RAG

Current system: No temporal weighting (old articles = recent articles)  
Proposed system: **Recency half-life (7 days for news)**

```python
def score_temporal_combinado(similarity: float, doc_date: datetime, alpha: float = 0.5, half_life_dias: int = 7):
    dias = (datetime.now() - doc_date).days
    score_recencia = exp(-0.693 * dias / half_life_dias)
    return (1 - alpha) * similarity + alpha * score_recencia
```

Research shows this achieves **perfect accuracy (1.00)** on freshness tests vs 0-quality without temporal component.

---

## VI. LLM ROUTING (LITELLM PROXY)

### A. Architecture

```
┌───────────────────────────┐
│  LiteLLM Proxy (nginx)     │
│  :4000                     │
├───────────────────────────┤
│ • Circuit breaker         │
│ • Key rotation            │
│ • Fallback chain          │
│ • Semantic cache (Redis)  │
│ • Cost tracking           │
└───────────────────────────┘
        ↓
    20+ Keys
    7 Providers
    ↓
┌──────────────────────────────────────┐
│  Tier 1: PREMIUM (strategic)          │
│  Claude Sonnet 4 (weight 8)           │
│  GPT-4.1 (weight 5)                   │
│  Gemini 2.5 Pro (weight 3)            │
│  Use: Diretor, Editor-Chefe, Revisor  │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  Tier 2: REDAÇÃO (article writing)    │
│  Claude Sonnet 4 (weight 10)          │
│  Gemini 2.5 Flash (weight 8)          │
│  GPT-4.1 (weight 5)                   │
│  Use: Repórteres, Editor Fotografia   │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  Tier 3: ECONÔMICO (high volume)      │
│  Haiku 3.5 (weight 10)                │
│  GPT-4.1 nano (weight 10)             │
│  Gemini Flash-Lite (weight 8)         │
│  DeepSeek Chat (weight 5)             │
│  Use: SEO, triaging, captions         │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  Tier 4: MULTIMODAL (image analysis)  │
│  GPT-4.1 (weight 8)                   │
│  Claude Sonnet 4 (weight 5)           │
│  Gemini 2.5 Pro (weight 3)            │
│  Use: Photo Editor image selection    │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  EMBEDDINGS (semantic search)         │
│  text-embedding-3-large (OpenAI)      │
│  Use: RAG indexing, similarity search │
└──────────────────────────────────────┘
```

### B. Cost Breakdown (100 articles/day baseline)

| Agent/Function | Calls/month | Cost/month USD | Notes |
|---|---|---|---|
| Repórteres (writing) | 3,000 | $75-100 | Sonnet 4 + Flash mix |
| Revisor (quality gate) | 3,000 | $10-15 | Sonnet 4 only |
| Triaging/classification | 10,000 | $5-8 | Haiku/nano (economic tier) |
| SEO/metadata | 3,000 | $5-8 | Flash-Lite/Haiku |
| Homepage curation | 1,500 | $3-5 | Gemini Flash |
| Headline selection | 60 | $2-3 | Sonnet 4 (premium) |
| Photo Editor | 3,000 | $8-12 | Multimodal (GPT-4.1) |
| Captions/credits | 3,000 | $2-3 | Haiku |
| Monitor Concorrência | 1,000 | $5-8 | Mixed |
| Diretor | 180 | $3-5 | Sonnet 4 |
| Editor-Chefe | 1,500 | $5-8 | Sonnet 4 |
| Editores de Editoria | 2,000 | $5-8 | Sonnet 4 |
| Pauteiro | 500 | $2-3 | Haiku + Sonnet |
| Embeddings | 10,000 | $1-2 | text-embedding-3-large |
| Analista Métricas | 200 | $1 | Gemini Flash |
| **TOTAL LLMs** | | **$132-208/month** | |

### C. Cost Optimizations

**Current system:** $150-400/month in unmeasured LLM costs (no tracking)  
**Proposed system:** $90-150/month (post-optimization)

**Optimizations:**
- **Prompt caching (Claude):** Reduces input tokens 80-90% for shared system prompts → 15-25% savings
- **Semantic caching (Redis):** Similar queries return cached responses → 20-30% reduction
- **Batch API (OpenAI):** 50% discount for non-urgent SEO/fact-checking → 5-10% savings
- **Dynamic tier switching:** Haiku for triaging, Sonnet 4 only when needed

---

## VII. 5-PHASE IMPLEMENTATION PLAN (24 Weeks)

### PHASE 0: PREPARATION (Weeks 1-2)

**Objective:** Infrastructure, CI/CD, credential security  
**Deliverables:**
1. GitHub repo with structure + branch protection
2. Railway account with PostgreSQL + Redis provisioned
3. LiteLLM config YAML with all 20+ keys validated
4. PostgreSQL schema (8 tables + pgvector extension)
5. Docker Compose for local dev (postgres + redis + litellm + agents)
6. GitHub Actions CI/CD pipeline (lint → test → deploy)
7. All credentials migrated from code to .env
8. Pytest framework + first smoke tests

**Success Criteria:**
- LiteLLM proxy responds on all tiers without error
- pgvector extension active + indexes created
- GitHub Actions completes full pipeline
- Zero credentials in git history

**Estimated Cost:** $15-30/month

---

### PHASE 1: MVP EDITORIAL (Weeks 3-6)

**Objective:** End-to-end pipeline: Pauta → Redação → Revisão → Publicação

**Deliverables:**
1. **LangGraph pipeline** (5 nodes):
   - Extrair: newspaper3k → BeautifulSoup → Jina cascade
   - Buscar Contexto RAG: vector search with temporal weighting
   - Redigir: LLM redaction with editorial rules
   - Revisar: Quality gate + plagiarism check <40%
   - Publicar: WordPress REST API publish

2. **Knowledge base backfill:** Index all 9,180 existing articles
3. **Deduplication:** Cross-check against legacy system
4. **Draft publishing:** Articles publish as "draft" for 2-week validation
5. **Comparison metrics:** Manual review of 50 articles (quality vs legacy)

**LangGraph StateGraph:**
```python
ArticleState = TypedDict(
    pauta_url, pauta_editoria, pauta_fonte_nome,
    conteudo_fonte, titulo_original, data_publicacao_fonte,
    artigos_relacionados, contexto_editorial,
    artigo_titulo, artigo_corpo_html, artigo_excerpt, artigo_meta_description,
    artigo_slug, artigo_tags, artigo_categoria_id, artigo_autor_id,
    revisao_aprovado, revisao_score, revisao_feedback, revisao_iteracao,
    imagem_url, imagem_credito, imagem_legenda, imagem_wp_id,
    wp_post_id, wp_url, publicado_em,
    custo_total_usd, tokens_total, erros, status
)

Workflow:
  extrair_conteudo → buscar_contexto_rag → redigir_artigo 
  → revisar_qualidade [loop max 2x] → publicar_wordpress
```

**Success Criteria:**
- Quality ≥ current system (manual audit of 50 articles)
- <5 min end-to-end per article
- <$0.05 cost per article
- Zero duplicate publications
- LangSmith traces complete with costs

**Estimated Cost:** $40-80/month

---

### PHASE 2: HIERARCHY & MEMORY (Weeks 7-10)

**Objective:** Add editorial management layer with memory

**Deliverables:**
1. **Editor-Chefe:** Continuous monitoring, pre-publication approval, breaking news coordination
2. **4 Editores de Editoria:** Política, Economia, Esportes, Tecnologia
3. **Memory system operational:** Editorial decisions tracked, topic coverage monitored
4. **RAG enhancement:** Repórteres receive prior coverage context with "don't repeat angles" instruction
5. **Pauteiro:** Trending detection + governmental agenda monitoring
6. **System migration:**
   - Motor Scrapers → Focas + Repórteres
   - Motor Consolidado → Monitor Concorrência + Repórteres with synthesis instruction

**Success Criteria:**
- Editor-Chefe rejects duplicate-angle articles (test with 20 cases)
- RAG returns relevant articles <500ms
- Volume ≥ legacy system (baseline: ~20 RSS + 20 scraper + consolidado per cycle)
- Continuity verification: articles reference prior developments

**Estimated Cost:** $80-150/month

---

### PHASE 3: IMAGES & HOMEPAGE (Weeks 11-14)

**Objective:** Image sourcing + homepage curation with memory

**Deliverables:**
1. **Photo Editor:** Context-aware selection from 6 sources (Agência Brasil, Senado, Flickr CC, Wikimedia, Pexels, Unsplash)
2. **Photo Assistant:** Smart crop + captions + credits + WordPress upload
3. **Homepage Curator:** Migrate existing system, add editorial memory for diversity
4. **Competence Monitor:** 12-portal tracking, trending detection, gap analysis

**Success Criteria:**
- ≥80% articles with real images (not placeholder)
- Zero copyright-restricted images
- Homepage updated every 30-60 min with diversity verification
- Trending detection <30min lag from emergence

**Estimated Cost:** $120-200/month

---

### PHASE 4: DIRECTION & AUTONOMY (Weeks 15-18)

**Objective:** Strategic layer + metrics-driven decisions

**Deliverables:**
1. **Diretor:** Every 2-4 hours, analyzes coverage, defines priorities, can create/destroy editors
2. **Dynamic agent instantiation:** EDITOR_COPA, EDITOR_ELEIÇÕES, etc
3. **Analista Métricas:** Google Analytics Data API v2 + Search Console integration
4. **Focas enhancement:** Adaptive polling + auto-discovery of new sources
5. **LGPD compliance:** Automated detection of sensitive personal data

**Success Criteria:**
- Diretor directives measurably alter coverage composition
- Metrics analyst identifies high-performer patterns
- Focas discovers ≥5 new sources/month
- All editorias maintain minimum coverage (gap <6h without article)

**Estimated Cost:** $180-300/month

---

### PHASE 5: OPTIMIZATION & SCALE (Weeks 19-24)

**Objective:** Cost reduction, performance tuning, full decommission of legacy

**Deliverables:**
1. **Cost optimization:** Batch API, prompt caching, semantic cache tuning
2. **Legacy system decommission:** Motor RSS v2, Motor Mestre, Motor Scrapers, Motor Consolidado all offline
3. **Dashboard:** Full operational visibility (costs, quality, latency, coverage)
4. **Documentation:** Architecture, runbooks, incident playbooks
5. **Load testing:** Validate 200+ articles/day without degradation

**Success Criteria:**
- Cost per article ≤$0.04 (Hallucination Herald benchmark)
- Mean latency <3 min end-to-end
- Uptime ≥99.5% (30 consecutive days)
- System fully autonomous with observable metrics

**Estimated Cost:** $200-350/month

---

## VIII. COST PROJECTIONS & ROI

### A. Current System Costs (Estimated)

| Component | Monthly USD |
|-----------|-------------|
| AWS LightSail | $20-40 |
| LLM APIs (unmeasured, inferred) | $150-400 |
| Image APIs | $20-50 |
| Domain + CDN | $10-20 |
| **TOTAL** | **$200-510** |

### B. Proposed System Costs

| Component | Monthly USD | Notes |
|-----------|-------------|-------|
| Railway (agents + compute) | $15-25 | Always-on workers + add-ons |
| Supabase Pro (PostgreSQL + pgvector) | $25 | Includes compute + storage |
| Redis | $10-30 | Cache + semantic cache + pub/sub |
| LLMs (optimized) | $90-150 | Prompt caching + semantic cache |
| Image APIs | $10-20 | Reduced: Gov sources are free |
| Tavily search | $30-50 | With Redis caching: reduce 40-60% |
| LangSmith | $0-39 | Free tier: 5K traces/month; Dev: $39 |
| LightSail (WP only) | $10-20 | Reduced load (no Python) |
| Domain + CDN | $5-10 | |
| **TOTAL** | **$195-369** | -2% to -28% vs current |

### C. Comparative Analysis

| Dimension | Current | Proposed | Delta |
|-----------|---------|----------|-------|
| **Total cost/month** | $200-510 | $195-369 | **-2% to -28%** |
| **Articles/day (capacity)** | 60-80 | 200+ | **+150-233%** |
| **Editorial memory** | Zero | Complete (3-layer) | **New capability** |
| **Continuity tracking** | None | RAG + topic tracking | **New capability** |
| **Monitoring** | Logs → lost | LangSmith + dashboards | **New capability** |
| **Test coverage** | 0% | 80%+ | **New capability** |
| **Cost tracking** | None | Per-agent, per-task, per-article | **New capability** |
| **Resilience** | Monolithic | Distributed | **Significant improvement** |
| **Breaking news speed** | Cycle-dependent (30m-2h) | Event-driven (minutes) | **5-10x faster** |
| **Quality gate** | Post-pub (reactive) | Pre-pub (proactive) | **Significant improvement** |

**ROI Principal:** Not cost reduction (marginal) but **capacity +150-233%, quality improvement, operational visibility, elimination of architectural fragility**.

---

## IX. RISK MITIGATION

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|-----------|
| 1 | **LLM costs uncontrolled** (agent loops/redundancy) | High | High | Circuit breaker (LiteLLM), cost ceiling/agent, semantic cache (30-50% reduction), daily anomaly alerts |
| 2 | **Agent retry storms** | Medium | High | Max 2 revisor loops; after 2 rejects → "needs human review". Counter per task in state. |
| 3 | **WordPress rate limiting (429)** | Medium | Medium | 10-concurrent max semaphore, exponential backoff (1s→2s→4s→8s), Nginx config `rate=30r/s` |
| 4 | **Scrapers break** (portal redesign) | High | Medium | Continuous health check in Focas (not daily). Auto-migrate A-E strategies. Slack alert if 0 articles >24h. |
| 5 | **Quality regression during migration** | Medium | High | Run in parallel 2-4 weeks, manual comparison of 50 articles, preserve `regras_editoriais.py` completely. |
| 6 | **pgvector scales poorly** (>10M vectors) | Low | Medium | Monitor latency. Archive embeddings >365d. Scale to Qdrant self-hosted if needed. |
| 7 | **Tone inconsistency between models** | Medium | Medium | Standardized system prompt with tone examples in `regras_editoriais.py`. Revisor checks tone. Prioritize one model per editoria. |
| 8 | **LGPD (personal data exposure)** | Low | High | Compliance agent (Revisor sub-function) checks sensitive mentions. ID judicial process articles for name omission. Mark AI-generated articles. |
| 9 | **Single LLM provider outage** | Low | High | Fallback chain via LiteLLM (7 providers, 20+ keys). No single point of failure. Semantic cache serves during partial outages. |
| 10 | **Data loss during migration** | Low | Medium | Complete backfill of 9,180 articles before decommissioning. Verify all WP posts in KB before killing legacy. |
| 11 | **Railway instability** | Low | High | Portable Dockerfile → Render, Fly.io, VPS in <1h. Docker Compose for local fallback. No Railway-specific features. |
| 12 | **LLM model discontinued** | Medium | Medium | LiteLLM abstracts models → change YAML config without code change. Keep 2+ validated models per tier. Monitor provider changelogs. |

---

## X. CURRENT PROGRESS STATUS

### Based on Codebase Analysis

**What's Already Implemented (Assets in Place):**
- [x] 630+ source catalog (categorized + mapped to WordPress authors)
- [x] 16 macro + 73 subcategories (WordPress taxonomy)
- [x] 6-tier LLM routing with 7 providers (custom code)
- [x] 5-tier image pipeline (tested hierarchy)
- [x] ~9,180 published articles (backfill data)
- [x] Health check scripts (can be adapted)
- [x] RSS + Scraper infrastructure (can be migrated)
- [x] WordPress integration (REST API ready)

**What Was Last Being Worked On (Inferred from Docs):**
- System analysis docs suggest recent audit of current architecture limitations
- Planning docs are comprehensive → indicates strategic preparation phase
- No code changes in v2 directory yet (skeleton only)
- Focus appears to be on design validation before implementation starts

**What Needs Building (24-Week Development):**
- [ ] LangGraph orchestration framework
- [ ] LiteLLM integration + configuration
- [ ] PostgreSQL + pgvector schema + migrations
- [ ] Memory system (editorial_memory.py, topic_tracker.py, etc)
- [ ] 10+ agent implementations
- [ ] RAG pipeline (chunking, embedding, indexing)
- [ ] Event bus (Redis Pub/Sub)
- [ ] WordPress async client
- [ ] Observability layer (LangSmith integration)
- [ ] Complete test suite
- [ ] Documentation + runbooks

---

## XI. NEXT IMMEDIATE STEPS (START TOMORROW)

### Week 1: Foundation
```
Day 1-2: Infrastructure Setup
  - [ ] Create GitHub repo: brasileira-news-agents
  - [ ] Railway account + PostgreSQL + Redis provisioned
  - [ ] Docker Compose local env running
  
Day 3-4: Security & Configuration
  - [ ] All credentials migrated to .env
  - [ ] LiteLLM config YAML validated with all 20+ keys
  - [ ] GitHub secrets configured
  
Day 5: CI/CD Pipeline
  - [ ] GitHub Actions lint + test workflow
  - [ ] GitHub Actions deploy to Railway
  - [ ] Dockerfile builds successfully
```

### Week 2: Database & Initial Tests
```
Day 1-2: PostgreSQL Setup
  - [ ] Schema deployed (8 tables + pgvector)
  - [ ] Indexes created
  - [ ] Local pytest framework configured
  
Day 3-4: First Agent
  - [ ] Minimal LangGraph graph
  - [ ] LiteLLM proxy call test
  - [ ] LangSmith trace test
  
Day 5: Deploy & Validate
  - [ ] Smoke tests pass on Railway
  - [ ] LangSmith receiving traces
```

---

## CONCLUSION

The V2 transformation is a **comprehensive reimagining** of brasileira.news from a brittle, memory-less monolith into a **distributed, autonomous editorial system** that matches the maturity and sophistication of enterprise newsrooms. The plan is:

- **Architecturally sound** (aligned with published research on hierarchical multi-agent systems)
- **Cost-neutral to cheaper** (~$195-369/month vs $200-510)
- **Massively more capable** (60-80 → 200+ articles/day, editorial memory, continuity, observability)
- **Risk-mitigated** (12 major risks identified with specific mitigations)
- **Pragmatically phased** (24 weeks, separable into 5 incremental phases)
- **Production-validated** (technologies chosen based on benchmarking of Hallucination Herald, Al Jazeera, Reuters, AP)

**The development should begin immediately with Phase 0 infrastructure setup.** All planning is complete; only execution remains.

