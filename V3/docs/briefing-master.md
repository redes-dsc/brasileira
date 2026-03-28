# Briefing Completo para IA — Readequação do Sistema brasileira.news V3

**Data:** 26 de março de 2026
**Classificação:** Documento de Implementação — Referência Completa
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / LangGraph / Kafka / Redis / PostgreSQL + pgvector / WordPress REST API / LiteLLM

---

## LEIA ISTO PRIMEIRO — Contexto e Mandato

Este documento é o briefing completo para a reconstrução do sistema multi-agente da **brasileira.news**, um portal jornalístico brasileiro automatizado por IA. O sistema atual (V2) está **fundamentalmente quebrado**: 0 artigos publicados em mais de 24 horas, fluxo editorial invertido, 18 agentes com gates que bloqueiam a produção, modelos LLM engessados sem fallback, e ingestão sequencial que trava ao primeiro erro.

**Seu mandato:** Reconstruir a V3 do zero, seguindo rigorosamente este briefing. Cada decisão aqui documentada foi resultado de auditoria de 20 arquivos de código, análise de 329 bugs, benchmarking de sistemas em produção (AP, Bloomberg, Washington Post, Reuters, BBC), e pesquisa extensiva sobre cada subsistema. Não há espaço para interpretação criativa nos pontos marcados como OBRIGATÓRIO.

**Volume de produção:** O sistema já produz mais de 100 matérias/dia na V2 quando funciona. A V3 deve suportar **pelo menos 1.000 artigos/dia** com folga — 10x o volume atual.

---

## PARTE I — DIAGNÓSTICO: POR QUE A V2 FALHOU

### 1.1 O Fluxo Invertido (Problema Central)

```
V2 (QUEBRADO):
Fontes → Pauteiro (FILTRA 99%) → Editor-Chefe (GATE) → Editor Editoria (GATE)
→ Reporter (FAZ DRAFT) → Revisor (REJEITA) → Publisher (ESPERA APROVAÇÃO)
= 0 artigos publicados

V3 (CORRETO):
Fontes → Ingestão Paralela (100%) → Classificação → Reporter (ESCREVE E PUBLICA)
→ [paralelo pós-publicação]:
    ├── Revisor (CORRIGE in-place)
    ├── Fotógrafo (BUSCA/GERA imagem)
    └── Curador (POSICIONA na homepage)
```

### 1.2 Mapeamento dos 18 Agentes V2 → V3

| Agente V2 | Problema Fatal | Destino V3 |
|-----------|----------------|------------|
| `pauteiro-15.py` | Filtra 99% das fontes, gera no máximo ~20 pautas/ciclo | Agente paralelo de inteligência, NÃO entry point |
| `editor_chefe-10.py` | Gatekeeper no INÍCIO, bloqueia publicação | Observador estratégico no FIM do pipeline |
| `editor_editoria-9.py` | Mais um gate, só 4 editorias | **ELIMINADO** — categorização é automática por ML |
| `reporter-19.py` | Espera pautas, faz draft em vez de publicar | Escreve E publica 100% direto no WordPress |
| `revisor-20.py` | Gate PRÉ-publicação, pode REJEITAR | PÓS-publicação, corrige in-place, NUNCA rejeita |
| `publisher-7.py` | Espera aprovação que nunca chega | **ELIMINADO** — publicação integrada ao Reporter |
| `fotografo-17.py` | Query gen com ECONÔMICO, sem og:image, sem fallback final | PREMIUM para queries, 4 tiers com persistência |
| `curador_homepage-12.py` | Score com ECONÔMICO, só aplica tags | PREMIUM, controla zonas editoriais + layouts dinâmicos |
| `curador_home-13.py` | DUPLICIDADE | **ELIMINADO** — um único Curador |
| `analista-2.py` | Insights não consumidos por ninguém | **ELIMINADO** — métricas integradas ao Editor-Chefe |
| `diretor-6.py` | Foco em cortar custos e restringir produção | **ELIMINADO** — responsabilidade absorvida pelo Editor-Chefe |
| `focas-8.py` | Desativa fontes "mortas" (PRODUCTIVITY_DEAD_DAYS=7) | Mantido, mas NUNCA desativa fontes |
| `consolidador-14.py` | Isolado, MIN_SOURCES=3 | Integrado ao pipeline, lógica corrigida (1 fonte=reescrever, 2+=consolidar) |
| `monitor-16.py` | Foco em custos, não produção | Reescrito: foco em throughput e cobertura |
| `monitor_concorrencia-18.py` | Alertas vão para Pauteiro (gargalo) | Alimenta Reporters/Consolidador diretamente |
| `qa_layout-3.py` | EventBus bug, overhead sem impacto | **ELIMINADO** |
| `qa_imagem-4.py` | EventBus bug, overhead sem impacto | **ELIMINADO** |
| `base-5.py` | Token budgets BLOQUEIAM agentes | Reescrito: budgets como alertas informativos, NUNCA bloqueiam |

**Resultado:** 18 agentes → 9 agentes na V3.

### 1.3 Tiers LLM Invertidos na V2

| Função | Tier V2 (ERRADO) | Tier V3 (CORRETO) |
|--------|-------------------|---------------------|
| Escrita de artigo | PADRÃO | **PREMIUM** |
| Query de imagem | ECONÔMICO | **PREMIUM** |
| Homepage curation/scoring | ECONÔMICO | **PREMIUM** |
| Consolidação/síntese | PADRÃO | **PREMIUM** |
| Pauta especial | PADRÃO | **PREMIUM** |
| SEO otimização | PADRÃO | **PADRÃO** |
| Revisão de texto | PREMIUM | **PADRÃO** |
| Trending detection | ECONÔMICO | **PADRÃO** |
| Análise de métricas | PREMIUM | **PADRÃO** |
| Classificação de categoria | — | **ECONÔMICO** |
| Extração de entidades | — | **ECONÔMICO** |
| Deduplicação | — | **ECONÔMICO** |
| Health monitoring | PREMIUM | **ECONÔMICO** |

### 1.4 Outros Problemas Críticos da V2

1. **Ingestão sequencial:** Um erro em qualquer fonte trava TUDO. Hoje roda sequencialmente por 648+ fontes.
2. **Sem scraping:** Sistema trata apenas RSS. Boa parte das fontes mais importantes são por scrapers.
3. **Modelos hardcoded:** Roteador LLM com modelos específicos de provedores específicos. Quando falha, tudo para.
4. **Sem fallback:** Nenhum circuit breaker real. Se LLM falha, agente entra em loop de retry infinito.
5. **Memória fake:** BaseAgent tem hooks para memória (working + episodic + semantic) mas nunca usa efetivamente.
6. **Cobertura insuficiente:** Só 4 editorias vs 16+ macrocategorias necessárias.
7. **Duplicidade:** Dois curadores da homepage com implementações diferentes e inconsistentes.

---

## PARTE II — ARQUITETURA V3

### 2.1 Visão Geral — 5 Camadas

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CAMADA 1: INGESTÃO PARALELA                                              │
│                                                                          │
│   [Feed Scheduler] distribui fontes para worker pool                     │
│        │                                                                 │
│   [Kafka: fonte-assignments]                                             │
│        │                                                                 │
│   [Worker Pool: 30-50 Coletores Independentes]                           │
│     ├── Coletor RSS #1..#N  (feeds RSS/Atom)                             │
│     └── Scraper #1..#N      (Playwright headless / HTTP)                 │
│     Regra: Cada worker é INDEPENDENTE. Se #3 trava, #1,#2,#4 continuam. │
│        │                                                                 │
│   [Deduplicação 4 Camadas]                                               │
│     1. HTTP ETag/304                                                     │
│     2. Redis SET de URLs (TTL 72h)                                       │
│     3. SHA-256 hash (título|data|url)                                    │
│     4. SimHash LSH (near-duplicate)                                      │
│        │                                                                 │
│   [Kafka: raw-articles] (particionado por publisher_id)                  │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CAMADA 2: CLASSIFICAÇÃO E ROTEAMENTO                                     │
│                                                                          │
│   [Classificador ML] — modelo leve (NÃO LLM), executado localmente       │
│     ├── 16 macrocategorias + regionais + internacional                   │
│     ├── Urgência: FLASH / NORMAL / ANÁLISE                               │
│     ├── Tipo: notícia_simples / consolidação / pauta_especial            │
│     └── Idioma e região de origem                                        │
│        │                                                                 │
│   [Kafka: classified-articles]                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CAMADA 3: PRODUÇÃO EDITORIAL (Fan-out)                                   │
│                                                                          │
│   [Worker Pool de Reporters] (N instâncias concorrentes LangGraph)       │
│     Pipeline por artigo:                                                 │
│       1. contextualizar  — RAG: busca matérias anteriores (pgvector)     │
│       2. redigir         — LLM PREMIUM: escreve artigo                   │
│       3. seo             — LLM PADRÃO: otimiza título/meta/slug          │
│       4. publicar        — WordPress REST API (PUBLICA DIRETO)           │
│       5. disparar_eventos — Kafka: article_published                     │
│                                                                          │
│   Fan-out paralelo PÓS-PUBLICAÇÃO (consumer groups Kafka):              │
│     ├── [Fotógrafo] busca/gera imagem → atualiza post WP                │
│     ├── [Revisor] revisa e corrige in-place no WP                        │
│     └── [Consolidador] detecta cluster → gera matéria de análise         │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CAMADA 4: CURADORIA E INTELIGÊNCIA                                       │
│                                                                          │
│   [Curador Homepage] — ciclo a cada 15-30 min                            │
│     ├── Coleta artigos recentes                                          │
│     ├── Score editorial com LLM PREMIUM                                  │
│     ├── Decide LAYOUT (normal / amplo / breaking) via ACF                │
│     ├── Posiciona artigos em zonas editoriais (6 zonas)                  │
│     └── Atualiza WordPress REST API + ACF Options                        │
│                                                                          │
│   [Pauteiro] — agente de INTELIGÊNCIA paralelo, NÃO entry point         │
│     ├── Monitora trending topics, redes sociais                          │
│     ├── Detecta pautas especiais e exclusivas                            │
│     └── Envia pautas para Reporters via Kafka                            │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CAMADA 5: OBSERVAÇÃO E ESTRATÉGIA                                        │
│                                                                          │
│   [Editor-Chefe] — observador (ciclo 1h), NÃO gatekeeper                │
│     ├── Monitora analytics (pageviews, CTR, engajamento)                 │
│     ├── Analisa cobertura vs concorrência (input do Monitor)             │
│     ├── Identifica gaps e ajusta prioridades                             │
│     └── Gera relatórios editoriais, NÃO bloqueia nada                   │
│                                                                          │
│   [Monitor Concorrência] — scan a cada 30min                             │
│     ├── Scanneia capas de G1, UOL, Folha, Estadão, CNN Brasil           │
│     ├── Gap analysis com TF-IDF + urgency scoring                        │
│     └── Gaps → Kafka → aciona Consolidador ou Reporters diretamente      │
│                                                                          │
│   [Monitor Sistema] — health + throughput                                │
│     ├── "Está publicando?" e "Cobertura completa?"                       │
│     ├── Alertas: < X artigos/hora = anomalia                             │
│     └── Custo como INFORMAÇÃO, nunca como bloqueio                       │
│                                                                          │
│   [Focas] — gerenciamento de fontes                                      │
│     ├── Health checks, adaptive polling                                  │
│     ├── Discovery de novas fontes (via citações)                         │
│     └── NUNCA desativa fontes — só ajusta frequência                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Stack Tecnológico V3

| Componente | Tecnologia | Justificativa |
|-----------|------------|---------------|
| **Runtime de agentes** | LangGraph 1.0 | StateGraph + checkpointing, usado em produção por Uber, JP Morgan, BlackRock. 90M+ downloads/mês |
| **Checkpointing** | PostgresSaver | Pausa/retomada em qualquer máquina, sobrevive a restarts, scaling O(1) |
| **Message broker** | Apache Kafka | Durabilidade, replay, múltiplos consumer groups, particionamento por publisher_id |
| **Cache / Working memory** | Redis Cluster | Cache de estados, deduplicação rápida (SET de URLs), health scores de provedores |
| **Banco relacional** | PostgreSQL 16 | Artigos processados, métricas, configurações, fonte de verdade |
| **Vector DB** | pgvector (HNSW) | Memória semântica/episódica dos agentes, busca de similaridade |
| **CMS** | WordPress REST API + ACF PRO | Publicação, gestão de homepage, zonas editoriais, layouts dinâmicos |
| **LLM Gateway** | LiteLLM + SmartRouter customizado | 7 provedores, health scoring, fallback em cascata |
| **Scraping** | Playwright (headless) + HTTPX | Playwright para SPAs/JS, HTTPX para sites estáticos |
| **RSS** | feedparser + HTTPX | ETag/If-Modified-Since para economia de banda |
| **Observabilidade** | LangSmith + OpenTelemetry | Tracing de agentes, latência por step, custo por artigo |
| **Image APIs** | Pexels, Unsplash, Wikimedia, Flickr CC, Agência Brasil | Gratuitas, sem custo de licença |
| **Geração de imagem** | DALL-E 3 / Flux | Fallback quando nenhuma foto real é encontrada |

---

## PARTE III — ROTEADOR LLM INTELIGENTE

### 3.1 Princípios OBRIGATÓRIOS

1. **NUNCA determina modelo específico** — escolhe o MELHOR DISPONÍVEL do tier
2. **Se um provedor falha, tenta TODOS os outros** antes de desistir
3. **Se o tier inteiro falha**, faz downgrade automático para o tier abaixo
4. **NUNCA retorna erro** sem ter tentado todos os 7 provedores
5. **Pools de modelos são dinâmicos** — carregáveis de Redis em runtime, sem deploy

### 3.2 Provedores Disponíveis (Março 2026)

**IMPORTANTE:** NÃO temos modelos open-source locais (sem Llama, sem Mixtral). Apenas APIs dos 7 provedores abaixo.

| Provedor | API Base | Flagship | Custo-Benefício | Ultra-Econômico |
|----------|----------|----------|-----------------|-----------------|
| **Anthropic** | `api.anthropic.com/v1` | Claude Opus 4.6 ($5/$25) | Claude Sonnet 4.6 ($3/$15) | Claude Haiku 3 ($0,25/$1,25) |
| **OpenAI** | `api.openai.com/v1` | GPT-5.4 ($2,50/$15) | GPT-4.1 Mini ($0,20/$0,80) | GPT-5.4 Nano ($0,20/$1,25) |
| **Perplexity** | `api.perplexity.ai` | Sonar Pro ($3/$15) | Sonar ($1/$1) | — |
| **xAI** | `api.x.ai/v1` | Grok 4 ($3/$15) | Grok 4.1 Fast ($0,20/$0,50) | Grok 3 Mini ($0,30/$0,50) |
| **Google** | `generativelanguage.googleapis.com` | Gemini 3.1 Pro ($2/$12) | Gemini 2.5 Flash ($0,30/$2,50) | Gemini 2.5 Flash-Lite ($0,10/$0,40) |
| **DeepSeek** | `api.deepseek.com/v1` | DeepSeek V3.2 ($0,28/$0,42) | — | — |
| **Alibaba** | Alibaba Cloud Model Studio | Qwen3.5-Plus ($0,26/$1,56) | Qwen3.5-Flash ($0,07/$0,26) | Qwen-Turbo ($0,03/$0,13) |

*Preços em USD por 1M tokens (input/output)*

### 3.3 Arquitetura do Roteador

```python
class SmartLLMRouter:
    """
    Roteador LLM inteligente com 3 princípios:
    1. NUNCA hardcoda modelos — escolhe MELHOR DISPONÍVEL do tier
    2. Se provedor falha → tenta TODOS antes de desistir
    3. Se tier inteiro falha → downgrade automático
    """

    # Pools dinâmicos — carregados de Redis, atualizáveis em runtime
    TIER_POOLS = {
        "premium": [
            {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            {"provider": "openai", "model": "gpt-5.4"},
            {"provider": "google", "model": "gemini-3.1-pro-preview"},
            {"provider": "xai", "model": "grok-4"},
            {"provider": "perplexity", "model": "sonar-pro"},
            {"provider": "anthropic", "model": "claude-opus-4.6"},
            {"provider": "openai", "model": "gpt-5.2"},
            {"provider": "google", "model": "gemini-2.5-pro"},
        ],
        "padrao": [
            {"provider": "openai", "model": "gpt-4.1-mini"},
            {"provider": "google", "model": "gemini-2.5-flash"},
            {"provider": "xai", "model": "grok-4-1-fast-reasoning"},
            {"provider": "deepseek", "model": "deepseek-chat"},
            {"provider": "alibaba", "model": "qwen3.5-plus"},
            {"provider": "anthropic", "model": "claude-haiku-4-5"},
            {"provider": "openai", "model": "gpt-5.4-mini"},
        ],
        "economico": [
            {"provider": "alibaba", "model": "qwen3.5-flash"},
            {"provider": "deepseek", "model": "deepseek-chat"},
            {"provider": "google", "model": "gemini-2.5-flash-lite"},
            {"provider": "openai", "model": "gpt-4.1-nano"},
            {"provider": "xai", "model": "grok-4-1-fast-non-reasoning"},
            {"provider": "alibaba", "model": "qwen-turbo"},
            {"provider": "openai", "model": "gpt-5.4-nano"},
        ],
    }

    async def route_request(self, task_type: str, content: str) -> LLMResponse:
        tier = self.get_tier_for_task(task_type)
        pool = await self.load_pool_from_redis(tier) or self.TIER_POOLS[tier]

        # Ordena por: health score (desc), latência recente (asc), custo (asc)
        ranked_pool = self.rank_by_health_and_cost(pool)

        for model_config in ranked_pool:
            try:
                response = await self.call_provider(
                    provider=model_config["provider"],
                    model=model_config["model"],
                    content=content,
                    timeout=30,  # timeout agressivo
                )
                self.record_success(model_config)
                return response
            except (ProviderError, TimeoutError, RateLimitError) as e:
                self.record_failure(model_config, e)
                continue  # PRÓXIMO modelo, NUNCA para

        # Tier inteiro falhou → downgrade automático
        if tier == "premium":
            return await self.route_with_tier("padrao", content)
        elif tier == "padrao":
            return await self.route_with_tier("economico", content)

        # TODOS falharam → última tentativa com qualquer modelo
        return await self.last_resort_any_model(content)
```

### 3.4 Health Scoring Dinâmico

```python
class ProviderHealthTracker:
    """
    Score 0-100 para cada modelo, atualizado em tempo real.
    Score < 30 → modelo deprioritizado (mas NÃO excluído)
    Score = 0  → skip automático por 5 minutos
    """

    def calculate_health(self, model_id: str) -> float:
        recent = self.get_last_n_calls(model_id, n=20)

        success_rate = recent.successes / recent.total
        avg_latency_factor = 1.0 - min(recent.avg_latency / 30.0, 1.0)
        error_recency = self.time_since_last_error(model_id)

        score = (
            success_rate * 50 +                     # 50% = taxa de sucesso
            avg_latency_factor * 30 +               # 30% = velocidade
            min(error_recency / 300, 1) * 20        # 20% = tempo desde último erro
        )
        return score
```

### 3.5 Mapeamento Tarefa → Tier

| Tipo de Tarefa | Tier | Justificativa |
|---------------|------|---------------|
| `redacao_artigo` | PREMIUM | Qualidade editorial TIER-1 |
| `imagem_query` | PREMIUM | Relevância da imagem depende da query |
| `homepage_scoring` | PREMIUM | Decisão editorial de altíssimo impacto |
| `consolidacao_sintese` | PREMIUM | Matéria de análise precisa de raciocínio |
| `pauta_especial` | PREMIUM | Ângulo editorial criativo |
| `seo_otimizacao` | PADRÃO | Otimização mecânica |
| `revisao_texto` | PADRÃO | Correção gramatical/estilo |
| `trending_detection` | PADRÃO | Precisa de raciocínio mas não máximo |
| `analise_metricas` | PADRÃO | Interpretação de dados |
| `classificacao_categoria` | ECONÔMICO | Tarefa simples e repetitiva |
| `extracao_entidades` | ECONÔMICO | NER básico |
| `deduplicacao_texto` | ECONÔMICO | Comparação mecânica |
| `monitoring_health` | ECONÔMICO | Verificação de status |

### 3.6 Configuração Dinâmica via Redis

Os pools são atualizáveis em runtime sem deploy:

```python
# Atualizar pool via API admin ou dashboard
await redis.set("llm:tier_pools:premium", json.dumps([
    {"provider": "anthropic", "model": "claude-sonnet-4-6", "weight": 1.0},
    {"provider": "openai", "model": "gpt-5.4", "weight": 1.0},
    # Adicionar/remover modelos em runtime
]))

# Router carrega na próxima request
pool = json.loads(await redis.get("llm:tier_pools:premium")) or TIER_POOLS["premium"]
```

---

## PARTE IV — ESPECIFICAÇÃO DOS 9 AGENTES V3

### 4.1 Reporter (Agente Principal — Produção)

**Papel:** Coração do sistema. Consome artigos classificados do Kafka, escreve e publica 100% do conteúdo diretamente no WordPress.

**REGRAS OBRIGATÓRIAS:**
- Sem draft. Publica direto.
- Sem aprovação. Sem gates.
- 100% das notícias de TODAS as fontes são processadas.
- Também executa pautas recebidas do Pauteiro.

**Pipeline LangGraph:**

```python
class ReporterState(TypedDict):
    raw_article: RawArticle            # Input do Kafka
    context: Optional[str]              # Matérias anteriores (RAG)
    written_article: Optional[str]      # Artigo redigido
    seo_data: Optional[SEOData]         # Título/meta/slug otimizados
    wp_post_id: Optional[int]           # ID do post publicado no WordPress
    published: bool

# Nós do grafo
nodes = {
    "contextualizar": contextualizar_node,   # RAG em pgvector
    "redigir": redigir_node,                 # LLM PREMIUM
    "seo": seo_node,                         # LLM PADRÃO
    "publicar": publicar_node,               # WordPress REST API
    "disparar_eventos": eventos_node,        # Kafka: article_published
}

# Fluxo: LINEAR sem branches
edges = [
    ("contextualizar", "redigir"),
    ("redigir", "seo"),
    ("seo", "publicar"),
    ("publicar", "disparar_eventos"),
]
```

**Contextualização (RAG):**
- Busca em pgvector matérias anteriores sobre o mesmo tema/entidades
- Evita repetição e fornece contexto para enriquecimento
- Limite: top 3 matérias mais similares, apenas resumos (não conteúdo completo)

**Redação (LLM PREMIUM):**
- System prompt define tom jornalístico TIER-1 brasileiro
- Mínimo 300 palavras para notícia simples, 500+ para análise
- Formato: título, subtítulo, lide (2 parágrafos), corpo, conclusão
- Crédito à fonte original obrigatório

**Publicação (WordPress REST API):**
```python
async def publicar_no_wordpress(artigo: ArticleData) -> int:
    response = await wp_client.post("/wp-json/wp/v2/posts", json={
        "title": artigo.titulo,
        "content": artigo.conteudo_html,
        "excerpt": artigo.resumo,
        "status": "publish",  # PUBLICA DIRETO — sem draft
        "categories": [artigo.categoria_wp_id],
        "tags": artigo.tag_ids,
        "meta": {
            "fonte_original": artigo.url_fonte,
            "editoria": artigo.editoria,
            "urgencia": artigo.urgencia,
        }
    })
    return response["id"]
```

**Após publicação, dispara evento Kafka:**
```json
{
    "event": "article_published",
    "post_id": 12345,
    "titulo": "...",
    "editoria": "politica",
    "urgencia": "normal",
    "url": "https://brasileira.news/...",
    "fonte_original": "https://...",
    "timestamp": "2026-03-26T12:00:00-03:00"
}
```

### 4.2 Fotógrafo (Pipeline de Imagem — Pós-Publicação)

**Papel:** Recebe evento `article_published` via Kafka. Busca/gera imagem relevante. Atualiza o post no WordPress. **Nenhuma notícia fica sem imagem.**

**REGRAS OBRIGATÓRIAS:**
- A IMAGEM TEM IMPORTÂNCIA jornalística. Não é um mero item decorativo.
- Query generation usa LLM PREMIUM (NÃO econômico).
- Pipeline de 4 tiers com persistência e reformulação automática.
- Se TUDO falha → placeholder temático por editoria. Notícia NUNCA fica sem imagem.

**Pipeline de 4 Tiers:**

```
TIER 1 — Extração da fonte original (Gratuito, rápido)
  ├── og:image do artigo fonte
  ├── schema.org ImageObject
  ├── twitter:image
  └── Primeiro <img> dentro de <article>
  → Se encontrou e resolução ≥ 800px e não é logo → USAR

TIER 2 — Busca com persistência (APIs gratuitas)
  ├── LLM PREMIUM gera 3 queries progressivas (específica → geral)
  │     Prompt: editor de fotografia de portal TIER-1
  │     Regras: inglês, 3-5 palavras, PESSOA + AÇÃO + CONTEXTO
  │     Evitar: nomes próprios, termos abstratos
  │     Output: query_especifica, query_media, query_generica
  │
  ├── Para CADA query, tenta CADA API:
  │     Pexels (200 req/h) → Unsplash (5k req/h) → Wikimedia → Flickr CC → Agência Brasil
  │
  ├── Validação: CLIP score > 0.3 + resolução ≥ 800px + não é ícone
  │
  └── Se TUDO falhou → REFORMULAÇÃO AUTOMÁTICA:
        Rodada 1: broadening ("senate vote reform" → "government legislation")
        Rodada 2: pivoting ("central bank interest rate" → "bank building exterior")
        Máximo 2 rodadas de reformulação

TIER 3 — Geração por IA (Pago)
  ├── DALL-E 3 ou Flux
  ├── Estilo: ilustração editorial (NÃO fotorrealista)
  └── Label obrigatório: "Imagem gerada por IA"

TIER 4 — Placeholder (Garantia)
  └── Imagem temática pré-definida por editoria
      (política, economia, esportes, etc.)
```

**System Prompt do Fotógrafo para geração de queries:**

```
Você é um editor de fotografia de um portal TIER-1 brasileiro.
Gere queries de busca de imagem que retornem FOTOS EDITORIAIS relevantes.

REGRAS:
- Queries em INGLÊS (cobertura 10x maior em bancos de imagem)
- 3-5 palavras por query (concisas mas precisas)
- Priorize: PESSOA + AÇÃO + CONTEXTO (não conceitos abstratos)
- EVITE nomes próprios (não funcionam em stock photos)
- EVITE termos abstratos: "economia", "crise", "futuro"
- USE termos visuais concretos: "trading floor", "parliament", "protest march"
- Gere 3 queries: específica → média → genérica

QUALIFICADORES por editoria:
- Política: "government", "parliament", "press conference"
- Economia: "trading floor", "business meeting", "financial data"
- Esportes: "stadium", "athlete", "competition"
- Saúde: "hospital", "medical", "healthcare worker"
- Tecnologia: "data center", "tech office", "server room"

Output JSON:
{
  "query_especifica": "...",
  "query_media": "...",
  "query_generica": "...",
  "editoria": "..."
}
```

**Atualização do post WordPress com imagem:**
```python
# 1. Upload da imagem como media
media_response = await wp_client.post("/wp-json/wp/v2/media", files={
    "file": (filename, image_bytes, content_type)
}, data={
    "alt_text": alt_text,
    "caption": credito,
})
media_id = media_response["id"]

# 2. Associar como featured image do post
await wp_client.post(f"/wp-json/wp/v2/posts/{post_id}", json={
    "featured_media": media_id,
})
```

### 4.3 Revisor (QA Pós-Publicação)

**Papel:** Recebe evento `article_published`. Revisa o artigo JÁ PUBLICADO. Corrige in-place no WordPress. **NUNCA rejeita.**

**REGRAS OBRIGATÓRIAS:**
- Trabalha em paralelo com Fotógrafo (ambos consomem article_published)
- Não rejeita. Faz a revisão, executa os ajustes no post já publicado.
- LLM PADRÃO (não precisa de PREMIUM para correção gramatical)

**Pipeline LangGraph:**

```python
nodes = {
    "carregar_post": carregar_post_wp,        # GET /wp-json/wp/v2/posts/{id}
    "revisar_gramatica": revisar_gramatica,    # LLM PADRÃO
    "revisar_estilo": revisar_estilo,          # LLM PADRÃO
    "revisar_fatos": revisar_fatos_basicos,    # Verificações básicas
    "aplicar_correcoes": aplicar_correcoes_wp, # PATCH no WordPress
}
```

**O que revisa:**
- Erros gramaticais e ortográficos
- Aderência ao manual de estilo do portal
- Consistência de dados (números, datas, nomes)
- SEO básico (título, meta description)

**O que NÃO faz:**
- Rejeitar artigo
- Despublicar artigo
- Bloquear pipeline
- Solicitar aprovação humana

### 4.4 Consolidador

**Papel:** Acionado pelo Monitor Concorrência quando detecta tema em capas de concorrentes. Gera matérias de análise ou reescrita editorial.

**REGRAS OBRIGATÓRIAS:**
- 0 fontes nossas sobre o tema → acionar Reporter para cobertura imediata
- 1 fonte → REESCREVER com ângulo editorial próprio
- 2+ fontes → CONSOLIDAR em matéria de análise aprofundada
- Tudo baseado em monitoramento das CAPAS DOS CONCORRENTES, não por número arbitrário

```python
class ConsolidadorV3:
    async def processar(self, tema: TemaDetectado):
        nossas_materias = await self.buscar_materias_sobre(tema)

        if len(nossas_materias) == 0:
            # Não temos NADA → acionar Reporter para cobertura
            await self.kafka.send("pautas_gap", {
                "tema": tema,
                "urgencia": "alta",
                "capas_concorrentes": tema.num_capas,
                "tipo": "cobertura_nova"
            })

        elif len(nossas_materias) == 1:
            # 1 fonte → REESCREVER com ângulo editorial próprio
            artigo = await self.reescrever(
                materia_existente=nossas_materias[0],
                contexto_concorrencia=tema.artigos_concorrentes,
                tier_llm="premium"
            )
            await self.publicar_wordpress(artigo)

        else:
            # 2+ fontes → CONSOLIDAR em análise aprofundada
            artigo = await self.consolidar(
                materias=nossas_materias,
                contexto_concorrencia=tema.artigos_concorrentes,
                tier_llm="premium"
            )
            await self.publicar_wordpress(artigo)
```

**Relevância por número de capas:**
- 1 capa de concorrente → relevância média
- 2-3 capas → relevância alta
- 4+ capas → relevância máxima (candidata a manchete)

### 4.5 Curador de Homepage

**Papel:** Gerencia a homepage com inteligência editorial PREMIUM. Controla zonas editoriais com layouts dinâmicos — não apenas tags.

**REGRAS OBRIGATÓRIAS:**
- LLM PREMIUM para scoring e decisões de layout
- Controla 6 zonas editoriais via ACF Options Page + WordPress REST API
- Muda o LAYOUT da homepage conforme importância (normal → amplo → breaking)
- Consulta métricas em tempo real para decidir o que manter e o que trocar
- Ciclo a cada 15-30 minutos

**6 Zonas Editoriais:**

```
┌────────────────────────────────────────────────────────────┐
│ ZONA 1: MANCHETE (layout variável)                          │
│                                                              │
│ MODO NORMAL:                    MODO BREAKING NEWS:          │
│ ┌──────────┐ ┌──────┐         ┌────────────────────────────┐│
│ │ Manchete  │ │Side  │         │     BREAKING NEWS          ││
│ │ com foto  │ │bar   │         │  Full-width com banner     ││
│ │ 2/3       │ │1/3   │         │  vermelho                  ││
│ └──────────┘ └──────┘         └────────────────────────────┘│
├────────────────────────────────────────────────────────────┤
│ ZONA 2: DESTAQUES (2-4 artigos, grid adaptativo)            │
├────────────────────────────────────────────────────────────┤
│ ZONA 3: POR EDITORIA (carrosséis por categoria)             │
├────────────────────────────────────────────────────────────┤
│ ZONA 4: MAIS LIDAS (auto-curada por analytics)              │
├────────────────────────────────────────────────────────────┤
│ ZONA 5: OPINIÃO / ANÁLISE                                   │
├────────────────────────────────────────────────────────────┤
│ ZONA 6: REGIONAL                                            │
└────────────────────────────────────────────────────────────┘
```

**Controle via ACF Options Page + REST API:**

```python
class CuradorHomepageV3:
    async def atualizar_homepage(self, composicao: HomepageComposicao):
        # MANCHETE: define artigo + modo
        await self.wp_api.update_option("manchete_principal", composicao.manchete.post_id)
        await self.wp_api.update_option("manchete_modo", composicao.manchete.modo)
        # modo = "normal" | "breaking" | "destaque_amplo"

        # DESTAQUES: até 4 artigos com tamanho de slot
        for i, destaque in enumerate(composicao.destaques):
            await self.wp_api.update_option(f"destaque_{i}_post", destaque.post_id)
            await self.wp_api.update_option(f"destaque_{i}_tamanho", destaque.tamanho)
            # tamanho: "pequeno" (1col) | "medio" (2col) | "grande" (3col)
            await self.wp_api.update_option(f"destaque_{i}_label", destaque.label)
            # label: "" | "EXCLUSIVO" | "AO VIVO" | "URGENTE"

        # EDITORIAS: artigos por categoria
        for editoria, artigos in composicao.por_editoria.items():
            await self.wp_api.update_option(
                f"editoria_{editoria}_posts",
                [a.post_id for a in artigos]
            )

        # BREAKING NEWS
        if composicao.breaking_news:
            await self.wp_api.update_option("breaking_news_ativo", True)
            await self.wp_api.update_option("breaking_news_post", composicao.breaking_news.post_id)
```

**Decisões de layout automáticas:**

| Condição | Layout |
|----------|--------|
| Score > 95, 4+ capas concorrentes, < 1h de publicação | BREAKING (full-width) |
| Score > 85, 2+ capas concorrentes | DESTAQUE AMPLO (manchete sem sidebar) |
| Demais | NORMAL (manchete 2/3 + sidebar 1/3) |

**Métricas para decisão de troca:**

| Sinal | Ação |
|-------|------|
| CTR > 5% | Manter ou promover |
| Bounce > 70% | Rebaixar |
| Tempo médio > 5min | Manter, considerar para "Mais Lidas" |
| 0 clicks em 30min | Substituir |
| Pico de tráfego externo em tema | Promover matéria sobre o tema |

### 4.6 Pauteiro (Agente de Inteligência)

**Papel:** Agente PARALELO que detecta pautas especiais, trending topics e oportunidades editoriais. NÃO é entry point. NÃO filtra conteúdo. Conteúdo flui independentemente de todas as fontes.

**O que faz:**
- Monitora Google Trends, redes sociais, trending topics
- Detecta pautas especiais que as fontes RSS/scrapers não cobrem
- Gera briefings de pauta para Reporters (via Kafka: `pautas_especiais`)
- Sugere ângulos editoriais diferenciados

**O que NÃO faz:**
- Filtrar conteúdo das fontes
- Ser entry point do pipeline
- Bloquear publicação
- Decidir o que é ou não coberto (TUDO é coberto)

### 4.7 Editor-Chefe (Observador Estratégico)

**Papel:** Observador no FIM do pipeline. Monitora analytics, analisa cobertura, identifica gaps. NÃO é gatekeeper.

**Ciclo:** A cada 1 hora

**O que faz:**
- Analisa métricas de engajamento (pageviews, CTR, tempo de leitura)
- Compara cobertura com concorrentes (input do Monitor Concorrência)
- Identifica editorias sub-representadas
- Ajusta pesos de categorias e prioridades
- Gera relatórios editoriais

**O que NÃO faz:**
- Aprovar publicação
- Bloquear qualquer artigo
- Ser gatekeeper no início do pipeline
- Rejeitar conteúdo

### 4.8 Monitor Concorrência

**Papel:** Scanneia capas de portais concorrentes a cada 30 minutos. Detecta gaps de cobertura. Alimenta Consolidador e Reporters diretamente.

**Concorrentes monitorados:** G1, UOL, Folha, Estadão, CNN Brasil, R7, Terra, Metrópoles

**Fluxo:**
```
Scanner de Capas → TF-IDF Gap Analysis → Urgency Scoring
    │
    ├── Gap com 0 matérias nossas → Kafka: pautas_gap → Reporter
    ├── Gap com 1+ matérias → Kafka: consolidacao → Consolidador
    └── Tema em 4+ capas → Kafka: breaking_candidate → Curador Homepage
```

### 4.9 Focas + Monitor Sistema

**Focas:** Gerencia health das 648+ fontes. Adaptive polling. Discovery de novas fontes via citações. **NUNCA desativa fontes** — apenas ajusta frequência de polling.

**Monitor Sistema:** Foco em produção, não custos.
- "Está publicando?" — se < X artigos/hora, alerta
- "Cobertura completa?" — quais editorias estão sem conteúdo?
- Custo como INFORMAÇÃO para relatório, NUNCA como bloqueio

---

## PARTE V — CAMADA DE INGESTÃO PARALELA

### 5.1 Princípios

- **Não é só RSS.** Boa parte das fontes mais importantes são por scrapers.
- **Paralelismo total.** Cada worker é independente. Se #3 trava, #1,#2,#4 continuam.
- **Isolamento de falhas.** Um erro NUNCA trava o pipeline inteiro.
- **Cobertura de 100%.** Todas as 648+ fontes são processadas em cada ciclo.

### 5.2 Dois Tipos de Coletores

**Coletor RSS:**
```python
class RSSCollector:
    """Processa feeds RSS/Atom. Stateless."""
    async def collect(self, feed_url: str) -> List[RawArticle]:
        # 1. Fetch com If-Modified-Since / ETag
        # 2. Parse XML (feedparser)
        # 3. Extrai artigos novos
        # 4. Para cada: título, link, resumo, data, og:image
        # Timeout: 15s. Se falha, log + next.
```

**Coletor Scraper:**
```python
class ScraperCollector:
    """Processa sites via scraping. Cada fonte tem config de seletores CSS."""
    async def collect(self, source_config: SourceConfig) -> List[RawArticle]:
        # 1. Determina método: HTTPX simples ou Playwright headless
        # 2. Acessa URL da fonte
        # 3. Aplica seletores CSS para extrair artigos
        # 4. Para cada: título, link, conteúdo, data, imagem
        # Timeout: 30s HTTP, 60s Playwright.
```

### 5.3 Worker Loop com Isolamento Total

```python
async def worker_loop(self, worker_id: str):
    """
    Loop infinito. NUNCA para. NUNCA bloqueia outros workers.
    """
    while True:
        try:
            source = await self.kafka_consumer.next()
            articles = await self.collect(source)
            for article in articles:
                await self.kafka_producer.send("raw-articles", article)
            self.mark_success(source)
        except Exception as e:
            self.logger.error(f"Worker {worker_id} falhou em {source.url}: {e}")
            self.mark_for_retry(source, delay=30)
            continue  # NÃO levanta exceção — continua
```

### 5.4 Feed Scheduler

```python
class FeedScheduler:
    """Distribui TODAS as fontes. Monitora quais foram processadas."""
    async def schedule_cycle(self):
        all_sources = await self.load_all_sources()  # 648+
        prioritized = self.sort_by_tier(all_sources)  # VIP primeiro

        for source in prioritized:
            await self.kafka_producer.send("fonte-assignments", source)

        # Após timeout do ciclo, verifica não-processadas
        await asyncio.sleep(self.cycle_timeout)
        missed = self.get_unprocessed_sources()
        for source in missed:
            await self.kafka_producer.send("fonte-assignments", source, priority=HIGH)
```

### 5.5 Deduplicação em 4 Camadas

| Camada | Técnica | Onde | Custo |
|--------|---------|------|-------|
| 1 | HTTP ETag / 304 Not Modified | No coletor, antes de baixar | Zero (HTTP nativo) |
| 2 | Redis SET de URLs normalizadas | Após coleta, antes de publicar no Kafka | O(1) lookup |
| 3 | SHA-256 hash (título + data + url) | Consumer do raw-articles | O(1) lookup em PostgreSQL |
| 4 | SimHash LSH (near-duplicate) | Consumer do raw-articles | Clustering |

---

## PARTE VI — FLUXOS DE DADOS E INTEGRAÇÕES

### 6.1 Tópicos Kafka

| Tópico | Particionamento | Producers | Consumers |
|--------|-----------------|-----------|-----------|
| `fonte-assignments` | fonte_id | Feed Scheduler | Workers (coletores) |
| `raw-articles` | publisher_id | Workers (coletores) | Classificador |
| `classified-articles` | categoria | Classificador | Worker Pool Reporters |
| `article-published` | post_id | Reporter | Fotógrafo, Revisor, Curador, Monitor |
| `pautas-especiais` | editoria | Pauteiro | Worker Pool Reporters |
| `pautas-gap` | urgencia | Consolidador, Monitor Conc. | Worker Pool Reporters |
| `consolidacao` | tema_id | Monitor Concorrência | Consolidador |
| `homepage-updates` | — | Curador | Monitor Sistema |
| `breaking-candidate` | — | Monitor Concorrência | Curador Homepage |

### 6.2 Redis (Cache + Working Memory)

| Chave | Tipo | TTL | Uso |
|-------|------|-----|-----|
| `dedup:urls` | SET | 72h | Deduplicação rápida de URLs |
| `health:{provider}:{model}` | HASH | 1h | Health scores por modelo LLM |
| `llm:tier_pools:{tier}` | STRING (JSON) | — | Pools dinâmicos de modelos |
| `source:last_etag:{source_id}` | STRING | 24h | ETags para If-Modified-Since |
| `homepage:current` | HASH | 30min | Estado atual da homepage |
| `agent:working_memory:{agent}:{cycle}` | HASH | 4h | Memória de trabalho do ciclo |

### 6.3 PostgreSQL

**Tabelas principais:**

```sql
-- Artigos processados (fonte de verdade)
CREATE TABLE artigos (
    id SERIAL PRIMARY KEY,
    wp_post_id INTEGER UNIQUE,
    url_fonte TEXT NOT NULL,
    url_hash CHAR(64) UNIQUE,  -- SHA-256 para dedup
    titulo TEXT NOT NULL,
    editoria VARCHAR(50),
    urgencia VARCHAR(20),
    score_relevancia FLOAT,
    publicado_em TIMESTAMPTZ DEFAULT NOW(),
    revisado BOOLEAN DEFAULT FALSE,
    imagem_aplicada BOOLEAN DEFAULT FALSE,
    fonte_nome VARCHAR(200)
);
CREATE INDEX idx_artigos_url_hash ON artigos(url_hash);
CREATE INDEX idx_artigos_editoria ON artigos(editoria);
CREATE INDEX idx_artigos_publicado ON artigos(publicado_em);

-- Fontes (648+)
CREATE TABLE fontes (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200),
    url TEXT UNIQUE,
    tipo VARCHAR(20),  -- 'rss' | 'scraper'
    tier VARCHAR(20),  -- 'vip' | 'padrao' | 'secundario'
    config_scraper JSONB,  -- seletores CSS, paginação, etc.
    polling_interval_min INTEGER DEFAULT 30,
    ultimo_sucesso TIMESTAMPTZ,
    ultimo_erro TEXT,
    ativa BOOLEAN DEFAULT TRUE  -- NUNCA muda para false automaticamente
);

-- Memória dos agentes (pgvector)
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
CREATE INDEX idx_memoria_embedding ON memoria_agentes
    USING hnsw (embedding vector_cosine_ops);

-- Health tracking dos provedores LLM
CREATE TABLE llm_health_log (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(30),
    model VARCHAR(100),
    success BOOLEAN,
    latency_ms INTEGER,
    error_type VARCHAR(50),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_health_recent ON llm_health_log(provider, model, timestamp DESC);
```

### 6.4 WordPress REST API

**Endpoints usados:**

| Ação | Método | Endpoint | Quem usa |
|------|--------|----------|----------|
| Publicar artigo | POST | `/wp-json/wp/v2/posts` | Reporter |
| Atualizar artigo | PATCH | `/wp-json/wp/v2/posts/{id}` | Revisor |
| Upload imagem | POST | `/wp-json/wp/v2/media` | Fotógrafo |
| Set featured image | PATCH | `/wp-json/wp/v2/posts/{id}` | Fotógrafo |
| Ler opções ACF | GET | `/wp-json/acf/v3/options/homepage-settings` | Curador |
| Atualizar opções ACF | POST | `/wp-json/acf/v3/options/homepage-settings` | Curador |
| Buscar posts recentes | GET | `/wp-json/wp/v2/posts?per_page=50&orderby=date` | Curador |

**Autenticação:** Application Password (não JWT, não OAuth — Application Password é nativo do WordPress 5.6+ e mais simples para server-to-server).

### 6.5 APIs de Imagem

| API | Endpoint | Auth | Rate Limit | Prioridade |
|-----|----------|------|------------|------------|
| Pexels | `api.pexels.com/v1/search` | API Key (header) | 200 req/h | 1 |
| Unsplash | `api.unsplash.com/search/photos` | API Key (header) | 5.000 req/h (prod) | 2 |
| Wikimedia | `commons.wikimedia.org/w/api.php` | Nenhuma | ~500 req/s | 3 |
| Flickr CC | `api.flickr.com/services/rest/` | API Key | Por contrato | 4 |
| Agência Brasil | Scraping | Nenhuma | Respeitar robots.txt | 5 |

---

## PARTE VII — REGRAS DE NEGÓCIO E DIRETRIZES EDITORIAIS

### 7.1 Regras Absolutas (NUNCA violar)

1. **Publicar primeiro, revisar depois.** Reporter publica direto. Revisor corrige depois.
2. **Sem aprovação antes de publicação.** Não faz sentido. Perde-se o volume e vira gargalo.
3. **100% das fontes processadas.** Nenhuma fonte é ignorada. NUNCA desativar fonte automaticamente.
4. **Nenhuma notícia sem imagem.** Se tudo falha, usa placeholder temático.
5. **Homepage com inteligência PREMIUM.** Curar homepage com modelo econômico é "um erro grotesco".
6. **Tudo imediato.** Não existe timeline de "10 semanas". Todas as aplicações são feitas por IA.
7. **Sem modelos open-source locais.** Não temos Llama, Mixtral ou qualquer modelo local. Apenas APIs.
8. **Roteador inteligente, não engessado.** Nenhum modelo fixo. Sistema escolhe o melhor disponível.

### 7.2 Fluxo Editorial Correto

```
                    ┌─────────────────────┐
                    │    FONTES (648+)     │
                    │  RSS + Scrapers      │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  INGESTÃO PARALELA   │
                    │  30-50 workers       │
                    │  Isolamento total    │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │   CLASSIFICAÇÃO      │
                    │   ML (não LLM)       │
                    │   16 categorias      │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │     REPORTER         │
                    │   Escreve E publica  │
                    │   DIRETO no WP       │
                    └─────────┬───────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                   │
  ┌─────────▼──────┐ ┌───────▼────────┐ ┌───────▼────────┐
  │  FOTÓGRAFO     │ │    REVISOR     │ │    CURADOR     │
  │  Busca imagem  │ │ Corrige in-place│ │ Posiciona home │
  │  Atualiza WP   │ │ NUNCA rejeita  │ │ Layouts dinâm. │
  └────────────────┘ └────────────────┘ └────────────────┘

  EM PARALELO (pós-publicação):
  ┌─────────────────────────────────────────────────┐
  │  PAUTEIRO: gera pautas especiais → Reporters     │
  │  EDITOR-CHEFE: observa analytics → ajusta pesos  │
  │  MONITOR CONC.: detecta gaps → Consolidador       │
  │  CONSOLIDADOR: reescreve/consolida quando preciso │
  │  FOCAS: gerencia fontes, discovery                │
  │  MONITOR: health + throughput                     │
  └─────────────────────────────────────────────────┘
```

### 7.3 Categorias (16 Macrocategorias)

O sistema V2 tinha apenas 4 editorias. A V3 deve suportar no mínimo 16 macrocategorias:

1. Política
2. Economia
3. Esportes
4. Tecnologia
5. Saúde
6. Educação
7. Ciência
8. Cultura / Entretenimento
9. Mundo / Internacional
10. Meio Ambiente
11. Segurança / Justiça
12. Sociedade
13. Brasil (geral)
14. Regionais (por estado/cidade)
15. Opinião / Análise
16. Últimas Notícias (transversal)

### 7.4 Manual de Estilo (System Prompt Base)

```
Você é um jornalista senior de um portal TIER-1 brasileiro (nível G1, Folha, UOL).

REGRAS DE ESCRITA:
- Língua portuguesa brasileira padrão
- Tom objetivo e factual, sem editorializações (salvo seção Opinião)
- Lide responde a: O quê? Quem? Quando? Onde? Por quê? Como?
- Título: direto, informativo, sem clickbait, até 80 caracteres
- Subtítulo: complementar ao título, até 150 caracteres
- Crédito à fonte original OBRIGATÓRIO
- Mínimo 300 palavras (notícia simples), 500+ (análise/consolidação)
- Sem plágio: REESCREVER, não copiar
- Data e hora no formato brasileiro: DD/MM/AAAA HH:MM

ESTRUTURA DO ARTIGO:
1. Título
2. Subtítulo
3. Lide (2 parágrafos: fato principal + contexto imediato)
4. Corpo (desenvolvimento, declarações, dados)
5. Contexto / Histórico (quando relevante)
6. Conclusão / Próximos passos

PROIBIDO:
- Inventar informações ou fontes
- Copiar trechos sem atribuição
- Usar linguagem coloquial ou gírias
- Emitir opinião em notícias factuais
- Publicar sem crédito à fonte
```

---

## PARTE VIII — CONTEXT ENGINEERING PARA AGENTES

### 8.1 Princípios Fundamentais

Cada agente opera com a **quantidade mínima de contexto necessária** para sua tarefa. O contexto é dividido em:

| Tipo | Posição no Prompt | Componentes |
|------|-------------------|-------------|
| **Estático** (início) | Regras editoriais, taxonomia, manual de estilo | Permite prompt caching (até 90% economia) |
| **Dinâmico** (final) | Estado do ciclo, artigo atual, métricas | Aproveita viés de recência |

### 8.2 Memória dos Agentes

**TODOS os agentes devem ter memória real**, não apenas hooks vazios:

| Tipo | O Que Armazena | Storage | TTL |
|------|----------------|---------|-----|
| **Semântica** | Fatos de domínio: taxonomia, perfil de fontes, padrões editoriais | pgvector | Permanente |
| **Episódica** | Experiências: artigos que performaram bem/mal, decisões passadas | pgvector | 90 dias |
| **Procedural** | Instruções: system prompts, regras de roteamento | Git (versionado) | Permanente |
| **Working** | Ciclo atual: artigos em processamento, quotas | Redis | 4h |

### 8.3 Scratchpads por Agente

| Agente | Scratchpad | Conteúdo |
|--------|-----------|----------|
| Editor-Chefe | `plano_editorial_{data}.json` | Temas prioritários, cotas por editoria |
| Pauteiro | `radar_fontes_{ciclo}.json` | Fontes processadas, scores de relevância |
| Fotógrafo | `decisoes_imagem_{ciclo}.json` | Imagens selecionadas, quotas de API consumidas |
| Curador | `homepage_estado_{ciclo}.json` | Composição atual, scores, métricas CTR |

### 8.4 Progressive Disclosure (Divulgação Progressiva)

Agentes descobrem contexto incrementalmente. Exemplo para o Pauteiro:

```
Passo 1: Recebe lista de 50 artigos candidatos
         (apenas: título, fonte, categoria, timestamp, score)
Passo 2: Seleciona 15 mais relevantes → solicita resumos expandidos
Passo 3: Agrupa por tendência → solicita conteúdo completo dos top 5
```

Em NENHUM momento o agente carrega 50 artigos completos na janela de contexto.

### 8.5 Ferramentas por Agente (Máximo 15-20 por fase)

| Agente | Fase | Ferramentas | Total |
|--------|------|-------------|-------|
| Reporter | Coleta | `fetch_rss`, `scrape_html`, `parse_api` | 3 |
| Reporter | Processamento | `gerar_titulo`, `classificar`, `verificar_duplicata` | 3 |
| Reporter | Publicação | `publicar_wp`, `registrar_metrica` | 2 |
| Fotógrafo | Busca | `buscar_pexels`, `buscar_unsplash`, `buscar_wikimedia`, `buscar_flickr` | 4 |
| Fotógrafo | Validação | `clip_score`, `verificar_resolucao` | 2 |
| Fotógrafo | Geração | `gerar_dalle`, `gerar_flux` | 2 |

---

## PARTE IX — TEMPLATES PHP DA HOMEPAGE (WordPress)

### 9.1 Template Principal

```php
<?php
// template-homepage.php

$breaking = get_field('breaking_news_ativo', 'option');
$manchete_modo = get_field('manchete_modo', 'option');

// ZONA 1: Manchete com layout variável
if ($breaking) {
    get_template_part('zones/breaking-fullwidth');
} elseif ($manchete_modo === 'destaque_amplo') {
    get_template_part('zones/manchete-ampla');
} else {
    get_template_part('zones/manchete-padrao');
}

// ZONA 2: Destaques com grid adaptativo
$destaques = [];
for ($i = 0; $i < 4; $i++) {
    $post_id = get_field("destaque_{$i}_post", 'option');
    if ($post_id) {
        $destaques[] = [
            'post' => get_post($post_id),
            'tamanho' => get_field("destaque_{$i}_tamanho", 'option'),
            'label' => get_field("destaque_{$i}_label", 'option'),
        ];
    }
}
get_template_part('zones/destaques-grid', null, ['destaques' => $destaques]);

// ZONA 3: Editorias por categoria
$editorias = ['politica', 'economia', 'esportes', 'tecnologia', 'saude', 'mundo'];
foreach ($editorias as $ed) {
    $posts = get_field("editoria_{$ed}_posts", 'option');
    if ($posts) {
        get_template_part('zones/editoria-carrossel', null, [
            'editoria' => $ed,
            'posts' => $posts,
        ]);
    }
}

// ZONA 4: Mais lidas (automático por analytics)
get_template_part('zones/mais-lidas');
?>
```

### 9.2 ACF Options Page (Setup)

```php
// functions.php ou plugin customizado
add_action('acf/init', function() {
    if (function_exists('acf_add_options_page')) {
        acf_add_options_page([
            'page_title' => 'Configurações da Homepage',
            'menu_title' => 'Homepage',
            'menu_slug'  => 'homepage-settings',
            'capability' => 'edit_posts',
            'redirect'   => false
        ]);
    }
});
```

---

## PARTE X — PADRÕES DE RESILIÊNCIA

### 10.1 Circuit Breaker Pattern

```python
class CircuitBreaker:
    """
    Abre após 10% de falha em janela de 30 segundos.
    Quando aberto: skip modelo por 5 minutos (não retorna erro, vai pro próximo).
    """
    FAILURE_THRESHOLD = 0.1  # 10%
    WINDOW_SECONDS = 30
    COOLDOWN_SECONDS = 300   # 5 min

    def should_allow(self, model_id: str) -> bool:
        if self.is_open(model_id):
            if time.time() - self.opened_at[model_id] > self.COOLDOWN_SECONDS:
                self.half_open(model_id)  # Permite uma tentativa
                return True
            return False  # Skip este modelo
        return True
```

### 10.2 Retry com Exponential Backoff + Jitter

```python
async def call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except TransientError:
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)
    # Após 3 retries: vai para DLQ, NÃO trava o pipeline
```

### 10.3 Dead Letter Queue (DLQ)

```
raw-articles → [processador] → processed-articles
                     ↓ (falha após 3 retries)
              dead-letter-queue
                     ↓ (análise periódica)
              [reprocessamento ou descarte]
```

### 10.4 Backpressure

- Kafka consumer groups com max.poll.records configurado
- Token bucket para controle de custo (sem bloqueio, apenas log + alert)
- Se um agente fica lento, Kafka acumula mas NÃO para os outros

---

## PARTE XI — OBSERVABILIDADE

### 11.1 Métricas-Chave

| Métrica | Alvo | Alerta |
|---------|------|--------|
| Artigos publicados/hora | ≥ 40 | < 20/hora |
| Tempo médio de publicação | < 60s | > 120s |
| Fontes processadas/ciclo | 648+ | < 600 |
| Taxa de sucesso LLM | > 95% | < 90% |
| Artigos sem imagem | 0% | > 5% |
| Cobertura (16 categorias) | 100% | Alguma com 0 artigos em 2h |
| Latência homepage update | < 2 min | > 5 min |
| Health score mínimo provedor | > 50 | < 30 |

### 11.2 Tracing

Cada artigo tem um trace_id que acompanha todo o pipeline:
```
trace_id: art-{source_id}-{timestamp}

Steps rastreados:
1. ingestão (worker_id, fonte, duração)
2. classificação (categoria, confiança, duração)
3. redação (provider, model, tokens_in, tokens_out, custo, duração)
4. publicação (wp_post_id, http_status, duração)
5. imagem (tier_usado, queries, apis_tentadas, resultado, duração)
6. revisão (correções_aplicadas, duração)
7. homepage (posição, zona, duração)
```

---

## PARTE XII — ESTRUTURA DE DIRETÓRIOS RECOMENDADA

```
brasileira/
├── agents/
│   ├── base.py                    # BaseAgent V3 com memória real
│   ├── reporter.py                # Reporter (escreve + publica)
│   ├── fotografo.py               # Pipeline de imagem 4 tiers
│   ├── revisor.py                 # QA pós-publicação
│   ├── consolidador.py            # Reescrever/consolidar
│   ├── curador_homepage.py        # Homepage + layouts dinâmicos
│   ├── pauteiro.py                # Inteligência de pautas
│   ├── editor_chefe.py            # Observador estratégico
│   ├── monitor_concorrencia.py    # Gap analysis
│   ├── monitor_sistema.py         # Health + throughput
│   └── focas.py                   # Gerenciamento de fontes
├── ingestion/
│   ├── feed_scheduler.py          # Distribui fontes
│   ├── rss_collector.py           # Coletor RSS
│   ├── scraper_collector.py       # Coletor Scraper (Playwright)
│   ├── deduplicator.py            # 4 camadas de dedup
│   └── worker_pool.py             # Pool de workers
├── classification/
│   ├── classifier.py              # ML leve para categorização
│   └── models/                    # Modelos de classificação treinados
├── llm/
│   ├── smart_router.py            # Roteador inteligente
│   ├── health_tracker.py          # Health scoring por modelo
│   ├── circuit_breaker.py         # Circuit breaker
│   └── tier_config.py             # Mapeamento task → tier
├── integrations/
│   ├── wordpress_client.py        # WordPress REST API
│   ├── kafka_client.py            # Kafka producer/consumer
│   ├── redis_client.py            # Redis cache/working memory
│   ├── postgres_client.py         # PostgreSQL + pgvector
│   └── image_apis/
│       ├── pexels.py
│       ├── unsplash.py
│       ├── wikimedia.py
│       ├── flickr.py
│       └── agencia_brasil.py
├── memory/
│   ├── semantic.py                # pgvector para memória semântica
│   ├── episodic.py                # Memória episódica
│   ├── working.py                 # Redis working memory
│   └── scratchpad.py              # Scratchpads por agente
├── observability/
│   ├── tracing.py                 # OpenTelemetry traces
│   ├── metrics.py                 # Métricas Prometheus
│   └── alerts.py                  # Sistema de alertas
├── config/
│   ├── sources.yaml               # Todas as 648+ fontes + configs
│   ├── categories.yaml            # 16 macrocategorias
│   ├── prompts/                   # System prompts por agente
│   │   ├── reporter.txt
│   │   ├── fotografo.txt
│   │   ├── revisor.txt
│   │   ├── curador.txt
│   │   └── editor_chefe.txt
│   └── homepage_zones.yaml        # Definição das 6 zonas
├── wordpress/
│   ├── template-homepage.php      # Template adaptativo
│   ├── zones/
│   │   ├── breaking-fullwidth.php
│   │   ├── manchete-padrao.php
│   │   ├── manchete-ampla.php
│   │   ├── destaques-grid.php
│   │   ├── editoria-carrossel.php
│   │   └── mais-lidas.php
│   └── acf-setup.php              # Configuração ACF
├── docker-compose.yml             # Kafka + Redis + PostgreSQL
├── requirements.txt
└── README.md
```

---

## PARTE XIII — CHECKLIST DE IMPLEMENTAÇÃO

### Prioridade 1 — Core Pipeline (o que PRECISA funcionar primeiro)

- [ ] SmartLLMRouter com 7 provedores, health scoring, fallback em cascata
- [ ] Worker pool de coletores (RSS + Scrapers) com isolamento total
- [ ] Deduplicação em 4 camadas
- [ ] Reporter: contextualizar → redigir → SEO → publicar direto no WP
- [ ] Kafka: raw-articles → classified-articles → article-published
- [ ] PostgreSQL: tabelas artigos, fontes, memoria_agentes, llm_health_log

### Prioridade 2 — Agentes Pós-Publicação

- [ ] Fotógrafo: pipeline 4 tiers com queries PREMIUM e persistência
- [ ] Revisor: correção in-place no WordPress, NUNCA rejeita
- [ ] Consolidador: lógica 0/1/2+ baseada em capas de concorrentes

### Prioridade 3 — Curadoria e Inteligência

- [ ] Curador Homepage: 6 zonas, ACF, layouts dinâmicos
- [ ] Templates PHP adaptativos (normal/amplo/breaking)
- [ ] Pauteiro: trending detection + pautas especiais

### Prioridade 4 — Observação e Estratégia

- [ ] Editor-Chefe: analytics, gap analysis, relatórios
- [ ] Monitor Concorrência: scan de capas, gap detection
- [ ] Monitor Sistema: health + throughput
- [ ] Focas: gerenciamento de fontes, discovery

### Prioridade 5 — Observabilidade

- [ ] OpenTelemetry traces por artigo
- [ ] Dashboard de métricas
- [ ] Alertas automáticos

---

*Este briefing compila o trabalho de 12 sessões de análise, incluindo: auditoria de 20 arquivos de código-fonte (329 bugs catalogados), benchmarking de 6 sistemas editoriais em produção (AP, Bloomberg, Reuters, Washington Post, Forbes, BBC), pesquisa extensiva sobre pipelines de imagem, gestão dinâmica de homepage, padrões arquiteturais multi-agente, catálogo completo de 70+ modelos LLM de 7 provedores (março 2026), e diretrizes de context engineering. Os documentos de pesquisa completos estão no workspace: `catalogo_modelos_llm_2026.md`, `pesquisa_pipeline_imagens.md`, `pesquisa_homepage_dinamica.md`, `benchmarking_editorial.md`, `benchmarking_arquitetura.md`, `context-engineering-brasileira-news.pplx.md`.*
