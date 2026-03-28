# Briefing Completo para IA — Editor-Chefe V3 (Observador Estratégico)

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #10 (Prioridade 4)
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / LangGraph / asyncio / PostgreSQL + pgvector / Redis / Google Analytics API / WordPress REST API
**Componente:** `brasileira/agents/editor_chefe.py` + módulos auxiliares

---

## LEIA ISTO PRIMEIRO — O Que Mudou Radicalmente na V3

O Editor-Chefe da V2 era um **gatekeeper criminoso**: ficava no INÍCIO do pipeline bloqueando a publicação de artigos. Resultado: 0 artigos publicados. Na V3, o Editor-Chefe é um **Observador Estratégico** que opera no FIM do pipeline, analisando o que já foi publicado e ajustando a estratégia editorial. Ele **NUNCA bloqueia artigos. NUNCA aprova publicações. NUNCA rejeita conteúdo.**

**Ciclo:** A cada 1 hora, o Editor-Chefe acorda, analisa as métricas das últimas horas, compara com concorrentes, identifica gaps de cobertura nas 16 macrocategorias, ajusta pesos de prioridade, e gera um relatório editorial. Depois dorme 1 hora. Simples e poderoso.

**Este briefing contém TUDO que você precisa para implementar o Editor-Chefe do zero.** Não consulte outros documentos para decisões marcadas como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ ERRADO NA V2

### 1.1 O Problema Central: Gatekeeper Disfarçado de Editor

O arquivo `editor_chefe-10.py` (879 linhas) implementa o Editor-Chefe como um **guardião de qualidade pré-publicação**. Isso é exatamente o oposto do que deve ser.

**Análise do código V2:**

```
Fluxo V2 (QUEBRADO):
Fontes → Pauteiro → [Editor-Chefe: quality_gate] → Reporter → Publisher
                           ↑
                    AQUI É O PROBLEMA
                    Bloqueia tudo antes
                    de publicar qualquer coisa
```

**5 Problemas Fatais no `editor_chefe-10.py`:**

**Problema 1: `QualityDecision.KILL` — Mata artigos antes de publicar**
```python
# V2 — ERRADO: Mata artigos
class QualityDecision(str, Enum):
    PUBLISH = "publish"
    HOLD = "hold"
    KILL = "kill"   # ← ISSO NÃO EXISTE NA V3. NUNCA.

# quality_gate decide se artigo é publicado
if score < self.reject_threshold:
    decision = QualityDecision.KILL  # ← BLOQUEIA PUBLICAÇÃO
```

**Problema 2: `quality_gate` no LangGraph como step central**
```python
# V2 — ERRADO: quality_gate é um node que bloqueia publicação
self.graph.add_node("quality_gate", self._step_quality_gate)
# Router direciona artigos pro quality_gate ANTES de publicar
if mode == "quality_gate":
    return "quality_gate"
```

**Problema 3: Thresholds de rejeição hardcoded**
```python
# V2 — ERRADO: Score mínimo para "hold" e "kill"
DEFAULT_REJECT_THRESHOLD = 5.0
DEFAULT_HOLD_THRESHOLD = 7.0
# Artigos abaixo de 5.0 são MORTOS. Isso viola regra #1 do sistema.
```

**Problema 4: Só 5 editorias ("geral" captura tudo)**
```python
# V2 — ERRADO: Apenas 5 buckets para 16 macrocategorias
EDITORIAS = ["politica", "economia", "esportes", "tecnologia", "geral"]
# "geral" absorve: saúde, educação, ciência, cultura, meio ambiente,
# segurança, sociedade, brasil, regionais, opinião, últimas
# = 11 de 16 macrocategorias jogadas numa vala comum
```

**Problema 5: Usa LLM PREMIUM para decisão editorial (custo errado)**
```python
# V2 — ERRADO: editorial_check usa tier PREMIUM implicitamente
async def _editorial_check(self, article):
    response = await self.llm.acomplete(
        prompt=prompt,
        task_type="editorial_decision",  # ← tier não especificado = PREMIUM por default
    )
```

### 1.2 Tabela Diagnóstico Completo

| # | Problema V2 | Impacto | Solução V3 |
|---|-------------|---------|------------|
| 1 | É gatekeeper pré-publicação | 0 artigos publicados | Observer pós-publicação, ciclo 1h |
| 2 | `QualityDecision.KILL` mata artigos | Bloqueia pipeline | Removido — não existe na V3 |
| 3 | `quality_gate` como node central | Congestionamento | Substituído por `analyze_engagement` |
| 4 | Thresholds de rejeição | Viola regra #1 do sistema | Removidos completamente |
| 5 | Só 5 editorias | 69% das categorias em "geral" | 16 macrocategorias cobertas |
| 6 | LLM PREMIUM para análise | Custo 5-10x desnecessário | LLM PADRÃO para análise de métricas |
| 7 | Sem leitura de analytics | Analisa nada, só classifica | Integração GA4 + WordPress REST API |
| 8 | Sem ciclo temporal | Evento-driven, não temporal | Loop assíncrono de 1h |
| 9 | Sem relatório editorial | Não gera insight nenhum | Relatório HTML/JSON a cada ciclo |
| 10 | Sem ajuste de pesos | Não influencia estratégia | Publica pesos em Redis para outros agentes |
| 11 | EventBus para comunicação | Acoplado demais | Redis + Kafka para outputs |
| 12 | `_step_assign` encaminha pautas | Gargalo editorial | Removido — assignment é automático |

### 1.3 O Que Deve Ser Preservado

Apesar dos problemas graves, o V2 tem boas práticas que a V3 mantém:

1. **`_safe_parse_llm_json()`** — Parsing defensivo de JSON com 3 tentativas. Excelente padrão. Manter.
2. **Estrutura BaseAgent** — Herança de BaseAgent, LangGraph, Pydantic. Manter.
3. **Memória semântica + episódica** — Hooks corretos, mas sem uso real. Na V3, usar de verdade.
4. **Coverage gaps detection** — Lógica certa, mas sem dados reais. Na V3, usar métricas reais.
5. **`_safe_parse_llm_json`** — Logging detalhado de decisões no PostgreSQL. Manter.

---

## PARTE II — ARQUITETURA V3: OBSERVADOR ESTRATÉGICO

### 2.1 Posição no Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PIPELINE PRINCIPAL (1.000+ artigos/dia)                                      │
│                                                                               │
│  Fontes → Ingestão → Classificação → Reporter → [PUBLICA NO WORDPRESS]       │
│                                                         │                     │
│                              ┌──────────────────────────┤                     │
│                              ▼           ▼              ▼                     │
│                          Revisor    Fotógrafo      Curador                    │
│                          (pós-pub)  (pós-pub)    (homepage)                   │
│                                                                               │
│                                                                               │
│  ═══════════════════════════════════════════════════════════════════════════  │
│  CAMADA DE OBSERVAÇÃO (independente, ciclo 1h)                                │
│                                                                               │
│                    ┌────────────────────────────┐                            │
│                    │    EDITOR-CHEFE V3           │                            │
│                    │    (Observador Estratégico)  │                            │
│                    │                              │                            │
│                    │  Input:                      │                            │
│                    │  ├── GA4 (pageviews/CTR)     │                            │
│                    │  ├── WordPress REST API       │                            │
│                    │  │   (artigos publicados)     │                            │
│                    │  └── Redis (dados Monitor     │                            │
│                    │       Concorrência)           │                            │
│                    │                              │                            │
│                    │  Output:                     │                            │
│                    │  ├── Redis (pesos editoriais) │                            │
│                    │  ├── Kafka (pautas-gap)       │                            │
│                    │  └── PostgreSQL (relatório)   │                            │
│                    └────────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Regra de Ouro:** O Editor-Chefe OBSERVA e ACONSELHA. Não manda, não bloqueia, não veta.

### 2.2 Grafo LangGraph V3

```
                    ┌──────────────┐
                    │  START (1h)  │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ collect_data │  ← GA4 + WP API + Redis Monitor
                    └──────┬───────┘
                           │
                    ┌──────▼───────────┐
                    │ analyze_coverage │  ← 16 macrocategorias
                    └──────┬────────────┘
                           │
                    ┌──────▼──────────────┐
                    │ analyze_engagement  │  ← pageviews, CTR, tempo leitura
                    └──────┬──────────────┘
                           │
                    ┌──────▼──────────────┐
                    │ compare_competitors │  ← dados do Monitor Concorrência
                    └──────┬──────────────┘
                           │
                    ┌──────▼──────────────┐
                    │  identify_gaps      │  ← editorias sub-representadas
                    └──────┬──────────────┘
                           │
                    ┌──────▼──────────────┐
                    │  adjust_priorities  │  ← publica pesos no Redis
                    └──────┬──────────────┘
                           │
                    ┌──────▼──────────────┐
                    │  generate_report    │  ← HTML + JSON no PostgreSQL
                    └──────┬──────────────┘
                           │
                    ┌──────▼──────────────┐
                    │  sleep(1h)          │  ← asyncio.sleep(3600)
                    └──────┬──────────────┘
                           │
                           └──── [volta ao START]
```

### 2.3 Princípios OBRIGATÓRIOS

1. **NUNCA bloqueia artigos.** O método `review_article()` não existe na V3. O método `quality_gate()` não existe na V3.
2. **NUNCA rejeita.** Não existe `QualityDecision.KILL` ou `QualityDecision.HOLD`. Removidos.
3. **Ciclo temporal, não evento-driven.** Roda a cada 1 hora via `asyncio.sleep(3600)`.
4. **LLM PADRÃO para análise.** `task_type="analise_metricas"` → tier PADRÃO.
5. **Custo como INFORMAÇÃO.** Se análise custar mais que esperado, loga. Não para.
6. **Outputs via Redis + Kafka.** Pesos editoriais em Redis. Gaps urgentes em Kafka `pautas-gap`.
7. **Lê analytics reais.** GA4 API + WordPress REST API. Sem dados fictícios.
8. **16 macrocategorias.** Não 5 editorias genéricas.
9. **Memória semântica ativa.** Persiste padrões de engajamento para comparação histórica.
10. **Graceful degradation.** Se GA4 indisponível, usa apenas dados WordPress. Se WP indisponível, usa Redis.

### 2.4 Stack do Componente

| Dependência | Versão | Função |
|-------------|--------|--------|
| `langgraph` | `>=0.2` | Orquestração do fluxo de análise |
| `redis[hiredis]` | `>=5.0` | Pesos editoriais, working memory |
| `asyncpg` | `>=0.29` | Relatórios e métricas no PostgreSQL |
| `google-analytics-data` | `>=0.18` | GA4 API — pageviews, CTR, tempo leitura |
| `httpx` | `>=0.27` | WordPress REST API (async) |
| `pydantic` | `>=2.5` | Schemas de dados |
| `aiokafka` | `>=0.10` | Publicar gaps no tópico `pautas-gap` |
| `jinja2` | `>=3.1` | Templates para relatório HTML |

---

## PARTE III — CICLO DE ANÁLISE DE 1 HORA

### 3.1 Fluxo Detalhado do Ciclo

O Editor-Chefe opera em um loop infinito. Cada iteração é um ciclo completo de análise.

```python
# Pseudocódigo do loop principal
async def run_forever(self):
    """Loop eterno. Ciclo a cada 1 hora."""
    while True:
        cycle_start = datetime.utcnow()
        cycle_id = f"editorial-{cycle_start.strftime('%Y%m%d-%H%M')}"
        
        try:
            # Executa o grafo completo
            result = await self.run_analysis_cycle(cycle_id)
            
            # Loga resultado na memória episódica
            await self._save_cycle_to_memory(cycle_id, result)
            
        except Exception as e:
            logger.error(f"Ciclo {cycle_id} falhou: {e}")
            # NUNCA quebra o loop — loga e continua
        
        # Calcula tempo restante para completar 1h
        elapsed = (datetime.utcnow() - cycle_start).total_seconds()
        sleep_time = max(0, 3600 - elapsed)
        
        logger.info(f"Ciclo {cycle_id} concluído em {elapsed:.1f}s. Próximo em {sleep_time:.0f}s.")
        await asyncio.sleep(sleep_time)
```

### 3.2 Timing dos Steps do Ciclo

| Step | Tempo Estimado | Dependências Externas |
|------|---------------|----------------------|
| `collect_data` | 15-30s | GA4 API, WordPress REST API, Redis |
| `analyze_coverage` | 2-5s | Dados locais (PostgreSQL) |
| `analyze_engagement` | 10-20s | LLM PADRÃO (análise) |
| `compare_competitors` | 2-5s | Redis (Monitor Concorrência) |
| `identify_gaps` | 10-15s | LLM PADRÃO (gap analysis) |
| `adjust_priorities` | 2-5s | Redis (escrita) + Kafka (escrita) |
| `generate_report` | 5-10s | PostgreSQL (escrita) |
| **Total** | **~60-90s** | — |
| **Sleep** | **~3510-3540s** | — |

### 3.3 Janelas de Análise

O Editor-Chefe analisa diferentes janelas temporais para entender tendências:

```python
JANELAS_ANALISE = {
    "curto_prazo": timedelta(hours=1),    # Último ciclo — o que acabou de acontecer
    "medio_prazo": timedelta(hours=6),    # Manhã/tarde/noite — padrões diários
    "longo_prazo": timedelta(hours=24),   # Último dia — tendências consolidadas
}

# Artigos publicados por janela
artigos_ultima_hora = await self._get_artigos_publicados(janela=timedelta(hours=1))
artigos_ultimas_6h  = await self._get_artigos_publicados(janela=timedelta(hours=6))
artigos_ultimas_24h = await self._get_artigos_publicados(janela=timedelta(hours=24))
```

---

## PARTE IV — COLETA DE MÉTRICAS DE ENGAJAMENTO

### 4.1 Fontes de Dados

O Editor-Chefe tem 3 fontes de dados de engajamento:

```
┌─────────────────────────────────────────────────────────┐
│ FONTE 1: Google Analytics 4 (GA4)                        │
│ Métricas: pageviews, sessions, avgSessionDuration, CTR  │
│ Granularidade: por artigo (pagePath), por categoria      │
│ Latência: ~5min (dados em tempo real via GA4 API)        │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│ FONTE 2: WordPress REST API                              │
│ Métricas: artigos publicados, categorias, timestamps    │
│ Granularidade: por post, por categoria, por tag          │
│ Latência: ~0 (tempo real)                                │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│ FONTE 3: Redis (Monitor Concorrência)                    │
│ Métricas: capas dos concorrentes, tópicos em destaque   │
│ Granularidade: por concorrente, por tópico               │
│ Latência: ~0 (já no Redis)                               │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Integração GA4 API

```python
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest, OrderBy
)

class GA4Client:
    """
    Cliente assíncrono para Google Analytics 4.
    
    Usa google-analytics-data com credenciais de service account.
    Property ID configurado via GA4_PROPERTY_ID no .env
    """
    
    def __init__(self, property_id: str, credentials_path: str):
        self.property_id = property_id
        self.client = BetaAnalyticsDataClient.from_service_account_file(
            credentials_path
        )
    
    async def get_article_metrics(
        self, 
        horas: int = 1,
        limit: int = 200
    ) -> list[dict]:
        """
        Busca métricas por artigo nas últimas N horas.
        
        Retorna lista com:
        - pagePath: path do artigo (ex: /politica/titulo-artigo/)
        - pageviews: visualizações
        - avgSessionDuration: tempo médio de leitura em segundos
        - sessions: sessões únicas
        """
        # GA4 não tem granularidade de horas diretamente, usamos today
        # e filtramos por timestamp via PostgreSQL
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            dimensions=[
                Dimension(name="pagePath"),
                Dimension(name="pageTitle"),
            ],
            metrics=[
                Metric(name="screenPageViews"),      # pageviews
                Metric(name="averageSessionDuration"), # tempo leitura
                Metric(name="sessions"),
                Metric(name="bounceRate"),
            ],
            date_ranges=[DateRange(start_date="today", end_date="today")],
            order_bys=[
                OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"),
                    desc=True,
                )
            ],
            limit=limit,
        )
        
        # Executa em thread separada (cliente síncrono)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, self.client.run_report, request
        )
        
        return self._parse_ga4_response(response)
    
    async def get_category_metrics(self, horas: int = 6) -> dict[str, dict]:
        """
        Agrega métricas por categoria/editoria.
        
        Usa dimensão customizada `customEvent:categoria` se configurada,
        ou parseia pagePath para inferir categoria.
        
        Retorna:
        {
            "Política": {"pageviews": 1500, "avg_session": 120.5, "artigos": 45},
            "Economia": {"pageviews": 800, "avg_session": 95.0, "artigos": 30},
            ...
        }
        """
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            dimensions=[
                Dimension(name="pagePathPlusQueryString"),
            ],
            metrics=[
                Metric(name="screenPageViews"),
                Metric(name="averageSessionDuration"),
            ],
            date_ranges=[DateRange(start_date="today", end_date="today")],
            limit=1000,
        )
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, self.client.run_report, request
        )
        
        raw = self._parse_ga4_response(response)
        return self._aggregate_by_category(raw)
    
    def _parse_ga4_response(self, response) -> list[dict]:
        """Converte resposta GA4 para lista de dicts."""
        results = []
        for row in response.rows:
            dims = [d.value for d in row.dimension_values]
            metrics = [m.value for m in row.metric_values]
            results.append({
                "pagePath": dims[0] if dims else "",
                "pageTitle": dims[1] if len(dims) > 1 else "",
                "pageviews": int(metrics[0]) if metrics else 0,
                "avgSessionDuration": float(metrics[1]) if len(metrics) > 1 else 0.0,
                "sessions": int(metrics[2]) if len(metrics) > 2 else 0,
                "bounceRate": float(metrics[3]) if len(metrics) > 3 else 0.0,
            })
        return results
    
    def _aggregate_by_category(self, rows: list[dict]) -> dict[str, dict]:
        """Agrupa métricas por categoria inferida do path."""
        MACROCATEGORIAS_SLUGS = {
            "politica": "Política",
            "economia": "Economia",
            "esportes": "Esportes",
            "tecnologia": "Tecnologia",
            "saude": "Saúde",
            "educacao": "Educação",
            "ciencia": "Ciência",
            "cultura": "Cultura/Entretenimento",
            "mundo": "Mundo/Internacional",
            "meio-ambiente": "Meio Ambiente",
            "seguranca": "Segurança/Justiça",
            "sociedade": "Sociedade",
            "brasil": "Brasil",
            "regionais": "Regionais",
            "opiniao": "Opinião/Análise",
            "ultimas": "Últimas Notícias",
        }
        
        aggregated = {}
        for row in rows:
            path = row["pagePath"]
            parts = path.strip("/").split("/")
            categoria_slug = parts[0] if parts else "outros"
            categoria = MACROCATEGORIAS_SLUGS.get(categoria_slug, "Outros")
            
            if categoria not in aggregated:
                aggregated[categoria] = {
                    "pageviews": 0, 
                    "total_duration": 0.0, 
                    "artigos": 0
                }
            
            aggregated[categoria]["pageviews"] += row["pageviews"]
            aggregated[categoria]["total_duration"] += row["avgSessionDuration"] * row["sessions"]
            aggregated[categoria]["artigos"] += 1
        
        # Calcula médias
        for cat, data in aggregated.items():
            n = data["artigos"] or 1
            data["avg_session_duration"] = data["total_duration"] / n
            del data["total_duration"]
        
        return aggregated
```

### 4.3 Integração WordPress REST API

```python
class WordPressAnalyticsClient:
    """
    Coleta dados de publicação diretamente da WordPress REST API.
    
    Fornece: volume por categoria, artigos recentes, timestamps.
    NÃO fornece: pageviews (isso é do GA4).
    """
    
    def __init__(self, wp_url: str, wp_user: str, wp_password: str):
        self.base_url = f"{wp_url}/wp-json/wp/v2"
        self.auth = (wp_user, wp_password)
        self._client = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(
                auth=self.auth,
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
        return self._client
    
    async def get_posts_by_category(
        self, 
        horas: int = 6,
        per_page: int = 100
    ) -> dict[str, int]:
        """
        Contagem de artigos publicados por categoria nas últimas N horas.
        
        Retorna:
        {
            "Política": 45,
            "Economia": 30,
            "Esportes": 120,
            ...
        }
        """
        client = await self._get_client()
        after = (datetime.utcnow() - timedelta(hours=horas)).isoformat() + "Z"
        
        # Busca todas as categorias primeiro
        cats_resp = await client.get(f"{self.base_url}/categories?per_page=100")
        cats_resp.raise_for_status()
        categories = {
            cat["id"]: cat["name"] 
            for cat in cats_resp.json()
        }
        
        # Busca posts recentes
        posts_resp = await client.get(
            f"{self.base_url}/posts",
            params={
                "after": after,
                "per_page": per_page,
                "status": "publish",
                "_fields": "id,categories,date",
            }
        )
        posts_resp.raise_for_status()
        posts = posts_resp.json()
        
        # Conta por categoria
        counts: dict[str, int] = {}
        for post in posts:
            for cat_id in post.get("categories", []):
                cat_name = categories.get(cat_id, "Outros")
                counts[cat_name] = counts.get(cat_name, 0) + 1
        
        return counts
    
    async def get_recent_posts(
        self, 
        horas: int = 1,
        per_page: int = 50
    ) -> list[dict]:
        """
        Lista artigos publicados na última hora com metadados.
        
        Retorna lista com: id, titulo, categoria, url, data_publicacao
        """
        client = await self._get_client()
        after = (datetime.utcnow() - timedelta(hours=horas)).isoformat() + "Z"
        
        resp = await client.get(
            f"{self.base_url}/posts",
            params={
                "after": after,
                "per_page": per_page,
                "status": "publish",
                "_fields": "id,title,categories,link,date",
                "_embed": "wp:term",
            }
        )
        resp.raise_for_status()
        
        posts = []
        for post in resp.json():
            posts.append({
                "id": post["id"],
                "titulo": post["title"]["rendered"],
                "categoria": self._extract_category(post),
                "url": post["link"],
                "publicado_em": post["date"],
            })
        return posts
    
    async def get_publishing_velocity(self) -> dict:
        """
        Taxa de publicação nas últimas 1h, 6h e 24h.
        
        Retorna:
        {
            "ultima_hora": 42,
            "ultimas_6h": 180,
            "ultimas_24h": 1050,
            "meta_diaria": 1000,
            "on_track": True,
        }
        """
        ultima_hora = len(await self.get_recent_posts(horas=1, per_page=100))
        
        # Para janelas maiores, usamos contagem de IDs
        client = await self._get_client()
        
        async def count_posts(horas: int) -> int:
            after = (datetime.utcnow() - timedelta(hours=horas)).isoformat() + "Z"
            resp = await client.head(
                f"{self.base_url}/posts",
                params={"after": after, "status": "publish", "per_page": 1}
            )
            return int(resp.headers.get("X-WP-Total", 0))
        
        ultimas_6h = await count_posts(6)
        ultimas_24h = await count_posts(24)
        
        return {
            "ultima_hora": ultima_hora,
            "ultimas_6h": ultimas_6h,
            "ultimas_24h": ultimas_24h,
            "meta_diaria": 1000,
            "on_track": ultimas_24h >= 800,  # 80% da meta diária
            "projecao_diaria": ultima_hora * 24,
        }
    
    def _extract_category(self, post: dict) -> str:
        """Extrai nome da categoria principal do post."""
        embedded = post.get("_embedded", {})
        terms = embedded.get("wp:term", [[]])
        if terms and terms[0]:
            return terms[0][0].get("name", "Outros")
        return "Outros"
    
    async def close(self):
        if self._client:
            await self._client.aclose()
```

### 4.4 Métricas de Engajamento Calculadas

O Editor-Chefe calcula 6 métricas derivadas para cada categoria:

```python
@dataclass
class EngagementMetrics:
    """Métricas calculadas por categoria editorial."""
    
    categoria: str
    
    # Volume
    artigos_publicados: int           # Quantidade publicada no período
    pageviews_total: int              # Total de visualizações
    pageviews_por_artigo: float       # Média: pageviews / artigos
    
    # Qualidade de engajamento
    avg_session_duration: float       # Tempo médio de leitura (segundos)
    bounce_rate: float                # Taxa de rejeição (0-1)
    engagement_score: float           # Score composto (0-100)
    
    # Tendência
    variacao_vs_ciclo_anterior: float # % variação vs ciclo anterior
    
    def calcular_engagement_score(self) -> float:
        """
        Score 0-100 composto de múltiplas métricas.
        
        Componentes:
        - 40%: Pageviews por artigo (normalizado pelo máximo da categoria)
        - 30%: Tempo de leitura (alvo: 120s = score 100)
        - 30%: Bounce rate invertido (bounce 0% = 100, 100% = 0)
        """
        score_pageviews = min(100, (self.pageviews_por_artigo / 500) * 100)
        score_leitura = min(100, (self.avg_session_duration / 120) * 100)
        score_bounce = max(0, (1 - self.bounce_rate) * 100)
        
        return (
            0.4 * score_pageviews +
            0.3 * score_leitura +
            0.3 * score_bounce
        )
```

---

## PARTE V — ANÁLISE DE COBERTURA (16 MACROCATEGORIAS)

### 5.1 As 16 Macrocategorias

O Editor-Chefe monitora cobertura nas 16 macrocategorias oficiais do sistema V3:

```python
MACROCATEGORIAS_V3 = [
    "Política",
    "Economia",
    "Esportes",
    "Tecnologia",
    "Saúde",
    "Educação",
    "Ciência",
    "Cultura/Entretenimento",
    "Mundo/Internacional",
    "Meio Ambiente",
    "Segurança/Justiça",
    "Sociedade",
    "Brasil",
    "Regionais",
    "Opinião/Análise",
    "Últimas Notícias",
]

# Metas de cobertura mínima por hora (artigos)
METAS_COBERTURA_HORA = {
    "Política": 5,
    "Economia": 4,
    "Esportes": 6,
    "Tecnologia": 3,
    "Saúde": 2,
    "Educação": 1,
    "Ciência": 1,
    "Cultura/Entretenimento": 3,
    "Mundo/Internacional": 4,
    "Meio Ambiente": 1,
    "Segurança/Justiça": 2,
    "Sociedade": 2,
    "Brasil": 3,
    "Regionais": 2,
    "Opinião/Análise": 1,
    "Últimas Notícias": 5,  # Transversal, sempre ativa
}
```

### 5.2 Análise de Cobertura

```python
async def _analyze_coverage(self, state: EditorChefeV3State) -> dict:
    """
    Analisa cobertura das 16 macrocategorias na última hora.
    
    Compara publicações reais com metas mínimas.
    Identifica categorias com cobertura zero (alerta crítico).
    Identifica categorias abaixo da meta (alerta moderado).
    """
    artigos_por_categoria = state["artigos_por_categoria"]
    
    cobertura = {}
    alertas_criticos = []
    alertas_moderados = []
    
    for categoria in MACROCATEGORIAS_V3:
        publicados = artigos_por_categoria.get(categoria, 0)
        meta = METAS_COBERTURA_HORA.get(categoria, 1)
        
        ratio = publicados / meta if meta > 0 else 1.0
        
        status = "ok"
        if publicados == 0:
            status = "critico"
            alertas_criticos.append({
                "categoria": categoria,
                "publicados": 0,
                "meta": meta,
                "deficit": meta,
            })
        elif ratio < 0.5:
            status = "baixo"
            alertas_moderados.append({
                "categoria": categoria,
                "publicados": publicados,
                "meta": meta,
                "deficit": meta - publicados,
            })
        elif ratio < 0.8:
            status = "moderado"
        
        cobertura[categoria] = {
            "publicados": publicados,
            "meta": meta,
            "ratio": ratio,
            "status": status,
        }
    
    state["cobertura_analise"] = cobertura
    state["alertas_criticos"] = alertas_criticos
    state["alertas_moderados"] = alertas_moderados
    
    # Loga na working memory
    await self._save_to_working_memory(
        key=f"cobertura:{state['cycle_id']}",
        data=cobertura,
        ttl=7200,  # 2h
    )
    
    return state
```

### 5.3 Cálculo de Sub-representação

Uma categoria está **sub-representada** quando:
1. Zero artigos publicados na última hora (crítico)
2. Menos de 50% da meta na última hora (baixo)
3. Abaixo de 80% da meta por 3 ciclos consecutivos (tendência)

```python
async def _detect_persistent_gaps(self, categoria: str) -> bool:
    """
    Verifica se uma categoria está sub-representada por 3+ ciclos.
    
    Usa memória episódica para histórico de ciclos anteriores.
    """
    chave = f"cobertura_historico:{categoria}"
    historico = await self.redis.lrange(chave, 0, 5)  # últimos 6 ciclos
    
    if len(historico) < 3:
        return False
    
    # Conta ciclos abaixo da meta
    abaixo_meta = sum(
        1 for h in historico[:3]
        if json.loads(h).get("ratio", 1.0) < 0.8
    )
    
    return abaixo_meta >= 3
```

---

## PARTE VI — COMPARAÇÃO COM CONCORRENTES

### 6.1 Input do Monitor Concorrência

O Monitor de Concorrência (componente separado) publica dados em Redis. O Editor-Chefe consome esses dados sem chamar nenhuma API externa.

```python
# Chaves Redis publicadas pelo Monitor Concorrência
REDIS_CHAVES_CONCORRENCIA = {
    "concorrencia:capas:atual": "HASH — Tópicos em destaque nas capas",
    "concorrencia:topicos:trending": "ZSET — Score de trending por tópico",
    "concorrencia:gap:confirmado": "LIST — Tópicos que concorrentes cobrem mas não cobrimos",
    "concorrencia:breaking:alert": "LIST — Breaking news detectados nos concorrentes",
}

async def _collect_competitor_data(self) -> dict:
    """
    Lê dados do Monitor Concorrência via Redis.
    
    Retorna dict com:
    - capas: {concorrente: [tópicos em destaque]}
    - trending: [{topico, score_concorrencia}]  
    - gaps: [{topico, concorrentes_cobrindo, urgencia}]
    - breaking: [{topico, primeiro_concorrente, detectado_em}]
    """
    capas_raw = await self.redis.hgetall("concorrencia:capas:atual")
    trending_raw = await self.redis.zrevrange(
        "concorrencia:topicos:trending", 0, 19, withscores=True
    )
    gaps_raw = await self.redis.lrange("concorrencia:gap:confirmado", 0, 29)
    breaking_raw = await self.redis.lrange("concorrencia:breaking:alert", 0, 9)
    
    capas = {}
    for concorrente, topicos_json in capas_raw.items():
        try:
            capas[concorrente.decode()] = json.loads(topicos_json)
        except Exception:
            pass
    
    trending = [
        {"topico": t.decode(), "score": s}
        for t, s in trending_raw
    ]
    
    gaps = [json.loads(g) for g in gaps_raw if g]
    breaking = [json.loads(b) for b in breaking_raw if b]
    
    return {
        "capas": capas,
        "trending": trending,
        "gaps": gaps,
        "breaking": breaking,
        "coletado_em": datetime.utcnow().isoformat(),
    }
```

### 6.2 Análise de Alinhamento com Concorrentes

```python
async def _compare_with_competitors(self, state: EditorChefeV3State) -> dict:
    """
    Compara nossa cobertura com o que os concorrentes estão publicando.
    
    Identifica:
    1. Tópicos que todos cobrem mas nós não (URGENTE)
    2. Tópicos que a maioria cobre mas nós não (MODERADO)
    3. Tópicos exclusivos nossos (DIFERENCIAL)
    4. Alinhamento geral de agenda (%)
    """
    competitor_data = state["competitor_data"]
    nossos_artigos = state["artigos_recentes"]  # últimas 6h
    
    # Extrai tópicos cobertos por nós
    nossos_topicos = set(
        a["titulo"].lower()[:50] 
        for a in nossos_artigos
    )
    
    # Analisa gaps confirmados pelo Monitor
    gaps_urgentes = [
        g for g in competitor_data["gaps"]
        if g.get("urgencia") == "alta" or g.get("concorrentes_cobrindo", 0) >= 3
    ]
    
    gaps_moderados = [
        g for g in competitor_data["gaps"]
        if g.get("urgencia") != "alta" and g.get("concorrentes_cobrindo", 0) < 3
    ]
    
    # Calcula cobertura de breaking news
    breaking_coverage = {
        "detectados": len(competitor_data["breaking"]),
        "cobertos_por_nos": sum(
            1 for b in competitor_data["breaking"]
            if any(b["topico"][:30].lower() in t for t in nossos_topicos)
        ),
    }
    
    alinhamento = (
        breaking_coverage["cobertos_por_nos"] / 
        max(1, breaking_coverage["detectados"])
    ) * 100
    
    state["competitor_analysis"] = {
        "gaps_urgentes": gaps_urgentes,
        "gaps_moderados": gaps_moderados,
        "breaking_coverage": breaking_coverage,
        "alinhamento_agenda_pct": alinhamento,
        "trending_nao_cobertos": [
            t for t in competitor_data["trending"][:10]
            if not any(t["topico"][:20].lower() in tp for tp in nossos_topicos)
        ],
    }
    
    return state
```

---

## PARTE VII — GAP ANALYSIS COM LLM

### 7.1 Gap Analysis via LLM PADRÃO

O Editor-Chefe usa LLM PADRÃO (não PREMIUM) para analisar os gaps e gerar recomendações.

```python
async def _identify_gaps_with_llm(self, state: EditorChefeV3State) -> dict:
    """
    Usa LLM PADRÃO para analisar gaps e gerar recomendações editoriais.
    
    Input:
    - Cobertura atual (16 categorias)
    - Análise de concorrentes
    - Métricas de engajamento
    
    Output:
    - Lista priorizada de gaps
    - Recomendações de ajuste
    - Categorias para boost
    """
    
    # Prepara contexto compacto (não precisa de 100k tokens)
    contexto = self._prepare_llm_context(state)
    
    prompt = f"""Você é o Editor-Chefe estratégico da brasileira.news. 
Analise os dados do ciclo editorial e identifique os principais gaps de cobertura.

DADOS DO CICLO {state['cycle_id']}:
{json.dumps(contexto, ensure_ascii=False, indent=2)}

Com base nestes dados, identifique:
1. As 3 categorias mais sub-representadas que precisam de mais cobertura
2. Os 5 tópicos mais urgentes que deveríamos cobrir mas não estamos cobrindo
3. As 2 categorias com melhor engajamento (para manter/ampliar)
4. Ajustes de prioridade recomendados (de 0.5 a 2.0, sendo 1.0 = normal)

Responda em JSON estruturado:
{{
  "gaps_principais": [
    {{"categoria": "...", "urgencia": "alta|media|baixa", "motivo": "..."}}
  ],
  "topicos_urgentes": [
    {{"topico": "...", "categoria": "...", "motivo": "..."}}
  ],
  "categorias_destaque": [
    {{"categoria": "...", "engajamento_score": 0-100, "recomendacao": "..."}}
  ],
  "ajustes_prioridade": {{
    "Política": 1.2,
    "Economia": 0.8,
    ...
  }},
  "observacoes_editoriais": "texto livre com análise estratégica"
}}"""

    response = await self.llm.acomplete(
        prompt=prompt,
        task_type="analise_metricas",   # ← TIER PADRÃO, não PREMIUM
        agent_id=self.agent_id,
        max_tokens=2000,
        temperature=0.3,
    )
    
    analysis = self._safe_parse_llm_json(
        response.content,
        default={
            "gaps_principais": [],
            "topicos_urgentes": [],
            "categorias_destaque": [],
            "ajustes_prioridade": {},
            "observacoes_editoriais": "Análise LLM indisponível",
        },
        context="gap_analysis"
    )
    
    state["gap_analysis"] = analysis
    return state

def _prepare_llm_context(self, state: EditorChefeV3State) -> dict:
    """
    Prepara contexto compacto para o LLM.
    Evita enviar dados brutos volumosos.
    """
    cobertura = state.get("cobertura_analise", {})
    engagement = state.get("engagement_metrics", {})
    competitor = state.get("competitor_analysis", {})
    velocity = state.get("publishing_velocity", {})
    
    # Simplifica cobertura para LLM
    cobertura_resumo = {
        cat: {
            "publicados": data["publicados"],
            "meta": data["meta"],
            "status": data["status"],
        }
        for cat, data in cobertura.items()
    }
    
    # Top 5 categorias por engajamento
    top_engagement = sorted(
        engagement.items(),
        key=lambda x: x[1].get("pageviews", 0),
        reverse=True
    )[:5]
    
    return {
        "periodo": "última 1 hora",
        "velocity": {
            "ultima_hora": velocity.get("ultima_hora", 0),
            "meta_diaria": velocity.get("meta_diaria", 1000),
            "on_track": velocity.get("on_track", True),
        },
        "cobertura_categorias": cobertura_resumo,
        "categorias_sem_cobertura": [
            cat for cat, data in cobertura.items()
            if data["status"] == "critico"
        ],
        "top_engajamento": dict(top_engagement),
        "gaps_concorrencia": competitor.get("gaps_urgentes", [])[:5],
        "breaking_nao_cobertos": competitor.get("trending_nao_cobertos", [])[:3],
    }
```

---

## PARTE VIII — AJUSTE DE PESOS E PRIORIDADES

### 8.1 O Que São os Pesos Editoriais

Os pesos editoriais são multiplicadores (0.5 a 2.0) que outros agentes usam para priorizar conteúdo. Por exemplo:
- Se o Editor-Chefe sobe o peso de "Esportes" para 1.8, o Reporter vai priorizar artigos de esportes
- Se baixa "Economia" para 0.7, artigos de economia ficam na fila mais tempo

**IMPORTANTE:** Esses pesos NÃO bloqueiam nada. São sinais de prioridade, não gates.

### 8.2 Publicação de Pesos no Redis

```python
async def _adjust_priorities(self, state: EditorChefeV3State) -> dict:
    """
    Publica pesos editoriais ajustados no Redis.
    
    Outros agentes leem:
    - redis.hget("editorial:pesos", "Política") → multiplicador
    - redis.hget("editorial:pesos", "Economia") → multiplicador
    
    TTL: 2 horas (próximo ciclo sobrescreve)
    """
    gap_analysis = state.get("gap_analysis", {})
    ajustes_llm = gap_analysis.get("ajustes_prioridade", {})
    alertas_criticos = state.get("alertas_criticos", [])
    
    # Calcula pesos finais
    pesos_finais = {}
    
    for categoria in MACROCATEGORIAS_V3:
        peso_base = 1.0
        
        # Boost automático para categorias críticas
        if any(a["categoria"] == categoria for a in alertas_criticos):
            peso_base = 1.8  # Boost forte para recuperar cobertura perdida
        
        # Ajuste do LLM (se disponível)
        if categoria in ajustes_llm:
            peso_llm = float(ajustes_llm[categoria])
            # Aplica ajuste LLM com moderação (blenda 50/50)
            peso_base = (peso_base + peso_llm) / 2
        
        # Clamp: nunca abaixo de 0.5 ou acima de 2.0
        pesos_finais[categoria] = max(0.5, min(2.0, peso_base))
    
    # Publica no Redis
    pipe = self.redis.pipeline()
    
    # Pesos por categoria
    pipe.hset("editorial:pesos", mapping={
        cat: str(peso)
        for cat, peso in pesos_finais.items()
    })
    pipe.expire("editorial:pesos", 7200)  # TTL 2h
    
    # Timestamp do último ajuste
    pipe.set(
        "editorial:pesos:updated_at",
        datetime.utcnow().isoformat(),
        ex=7200
    )
    
    # Ciclo atual para auditoria
    pipe.set(
        "editorial:pesos:cycle_id",
        state["cycle_id"],
        ex=7200
    )
    
    await pipe.execute()
    
    state["pesos_publicados"] = pesos_finais
    
    # Publica tópicos urgentes no Kafka (pautas-gap)
    await self._publish_urgent_gaps_to_kafka(state)
    
    return state

async def _publish_urgent_gaps_to_kafka(self, state: EditorChefeV3State) -> None:
    """
    Publica gaps urgentes no tópico Kafka pautas-gap.
    
    Esses gaps chegam para Reporters e Consolidador como
    sugestões de cobertura — NÃO como ordens.
    """
    gap_analysis = state.get("gap_analysis", {})
    topicos_urgentes = gap_analysis.get("topicos_urgentes", [])
    competitor_breaking = state.get("competitor_analysis", {}).get("gaps_urgentes", [])
    
    # Unifica gaps urgentes
    todos_gaps = []
    
    for topico in topicos_urgentes[:5]:  # Top 5
        todos_gaps.append({
            "topico": topico["topico"],
            "categoria": topico["categoria"],
            "origem": "editor_chefe_analise",
            "urgencia": topico.get("urgencia", "media"),
            "motivo": topico.get("motivo", ""),
            "sugerido_em": datetime.utcnow().isoformat(),
            "sugerido_por": self.agent_id,
        })
    
    for gap in competitor_breaking[:3]:  # Top 3 do Monitor Concorrência
        todos_gaps.append({
            "topico": gap.get("topico", ""),
            "categoria": gap.get("categoria", "Geral"),
            "origem": "competitor_gap",
            "urgencia": "alta",
            "motivo": f"Coberto por {gap.get('concorrentes_cobrindo', 0)} concorrentes",
            "sugerido_em": datetime.utcnow().isoformat(),
            "sugerido_por": self.agent_id,
        })
    
    if not todos_gaps:
        return
    
    # Publica no Kafka
    try:
        for gap in todos_gaps:
            await self.kafka_producer.send_and_wait(
                "pautas-gap",
                key=gap["categoria"].encode(),
                value=json.dumps(gap, ensure_ascii=False).encode(),
            )
        self.logger.info(f"Publicados {len(todos_gaps)} gaps no Kafka pautas-gap")
    except Exception as e:
        self.logger.warning(f"Falha ao publicar gaps no Kafka: {e}")
```

---

## PARTE IX — RELATÓRIOS EDITORIAIS

### 9.1 Estrutura do Relatório

A cada ciclo, o Editor-Chefe gera um relatório editorial completo salvo no PostgreSQL e opcionalmente em HTML estático.

```python
@dataclass
class RelatorioEditorial:
    """Relatório editorial gerado a cada ciclo."""
    
    cycle_id: str
    gerado_em: datetime
    periodo_analisado_horas: int
    
    # Volume
    artigos_publicados_1h: int
    artigos_publicados_6h: int
    artigos_publicados_24h: int
    projecao_diaria: int
    meta_diaria: int
    
    # Cobertura
    categorias_criticas: list[str]     # Cobertura zero
    categorias_baixas: list[str]       # Abaixo de 50% da meta
    categorias_ok: list[str]           # Dentro ou acima da meta
    
    # Engajamento
    categoria_mais_engajada: str
    categoria_menos_engajada: str
    pageviews_total_1h: int
    avg_session_duration_geral: float  # segundos
    
    # Concorrentes
    gaps_urgentes: list[dict]
    alinhamento_agenda_pct: float
    breaking_cobertos_pct: float
    
    # Análise LLM
    observacoes_editoriais: str
    
    # Ações tomadas
    pesos_ajustados: dict[str, float]
    gaps_publicados_kafka: int
```

### 9.2 Geração do Relatório

```python
async def _generate_report(self, state: EditorChefeV3State) -> dict:
    """
    Gera relatório editorial completo do ciclo.
    
    Salva em:
    1. PostgreSQL (tabela relatorios_editoriais) — permanente
    2. Redis (key editorial:relatorio:ultimo) — para consulta rápida
    3. HTML gerado por Jinja2 — opcional
    """
    
    relatorio = {
        "cycle_id": state["cycle_id"],
        "gerado_em": datetime.utcnow().isoformat(),
        "periodo_horas": 1,
        
        # Volume
        "volume": state.get("publishing_velocity", {}),
        
        # Cobertura
        "cobertura": {
            "criticas": [a["categoria"] for a in state.get("alertas_criticos", [])],
            "baixas": [a["categoria"] for a in state.get("alertas_moderados", [])],
            "ok": [
                cat for cat, data in state.get("cobertura_analise", {}).items()
                if data["status"] in ("ok",)
            ],
            "detalhes": state.get("cobertura_analise", {}),
        },
        
        # Engajamento
        "engajamento": {
            "por_categoria": state.get("engagement_metrics", {}),
            "top_artigos": state.get("top_artigos", []),
        },
        
        # Concorrentes
        "concorrentes": state.get("competitor_analysis", {}),
        
        # Gap analysis
        "gaps": state.get("gap_analysis", {}),
        
        # Pesos publicados
        "pesos_editoriais": state.get("pesos_publicados", {}),
        
        # Custo do ciclo
        "custo_ciclo": state.get("custo_llm_ciclo", 0.0),
    }
    
    # Salva no PostgreSQL
    await self._save_report_to_postgres(relatorio)
    
    # Salva no Redis para consulta rápida
    await self.redis.set(
        "editorial:relatorio:ultimo",
        json.dumps(relatorio, ensure_ascii=False),
        ex=7200,  # 2h
    )
    
    # Gera HTML se Jinja2 disponível
    try:
        html = await self._render_report_html(relatorio)
        await self._save_html_report(relatorio["cycle_id"], html)
    except Exception as e:
        self.logger.debug(f"HTML report generation failed (non-critical): {e}")
    
    state["relatorio_gerado"] = relatorio
    
    self.logger.info(
        f"Relatório {state['cycle_id']} gerado: "
        f"{relatorio['volume'].get('ultima_hora', 0)} artigos/h, "
        f"{len(relatorio['cobertura']['criticas'])} categorias críticas, "
        f"{len(state.get('gap_analysis', {}).get('gaps_principais', []))} gaps identificados"
    )
    
    return state

async def _save_report_to_postgres(self, relatorio: dict) -> None:
    """Persiste relatório no PostgreSQL."""
    query = """
        INSERT INTO relatorios_editoriais (
            cycle_id,
            gerado_em,
            artigos_hora,
            artigos_24h,
            categorias_criticas,
            categorias_baixas,
            gaps_urgentes,
            pesos_editoriais,
            custo_llm,
            dados_completos
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
        )
        ON CONFLICT (cycle_id) DO UPDATE SET
            dados_completos = EXCLUDED.dados_completos,
            custo_llm = EXCLUDED.custo_llm
    """
    
    volume = relatorio.get("volume", {})
    cobertura = relatorio.get("cobertura", {})
    
    await self.db.execute(
        query,
        relatorio["cycle_id"],
        datetime.fromisoformat(relatorio["gerado_em"]),
        volume.get("ultima_hora", 0),
        volume.get("ultimas_24h", 0),
        json.dumps(cobertura.get("criticas", [])),
        json.dumps(cobertura.get("baixas", [])),
        json.dumps(relatorio.get("concorrentes", {}).get("gaps_urgentes", [])),
        json.dumps(relatorio.get("pesos_editoriais", {})),
        relatorio.get("custo_ciclo", 0.0),
        json.dumps(relatorio, ensure_ascii=False),
    )
```

### 9.3 Template HTML do Relatório (Jinja2)

```python
REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Relatório Editorial — {{ relatorio.cycle_id }}</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
        .status-critico { background: #ffebee; border-left: 4px solid #f44336; padding: 8px; }
        .status-baixo { background: #fff8e1; border-left: 4px solid #ff9800; padding: 8px; }
        .status-ok { background: #e8f5e9; border-left: 4px solid #4caf50; padding: 8px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
        .metric-box { display: inline-block; padding: 16px; margin: 8px; background: #f5f5f5; border-radius: 8px; }
        .metric-value { font-size: 2em; font-weight: bold; color: #1976d2; }
    </style>
</head>
<body>
    <h1>📊 Relatório Editorial</h1>
    <p>Ciclo: <strong>{{ relatorio.cycle_id }}</strong> | Gerado em: {{ relatorio.gerado_em }}</p>
    
    <section>
        <h2>Volume de Publicação</h2>
        <div class="metric-box">
            <div class="metric-value">{{ volume.ultima_hora }}</div>
            artigos/hora
        </div>
        <div class="metric-box">
            <div class="metric-value">{{ volume.ultimas_24h }}</div>
            artigos/24h (meta: {{ volume.meta_diaria }})
        </div>
        <div class="metric-box">
            <div class="metric-value">{{ volume.projecao_diaria }}</div>
            projeção diária
        </div>
    </section>
    
    <section>
        <h2>Cobertura das 16 Categorias</h2>
        {% if cobertura.criticas %}
        <div class="status-critico">
            <strong>⚠️ Cobertura ZERO:</strong> {{ cobertura.criticas | join(', ') }}
        </div>
        {% endif %}
        {% if cobertura.baixas %}
        <div class="status-baixo">
            <strong>⚡ Cobertura BAIXA:</strong> {{ cobertura.baixas | join(', ') }}
        </div>
        {% endif %}
        <table>
            <tr><th>Categoria</th><th>Publicados</th><th>Meta/h</th><th>Ratio</th><th>Status</th></tr>
            {% for cat, data in cobertura.detalhes.items() %}
            <tr>
                <td>{{ cat }}</td>
                <td>{{ data.publicados }}</td>
                <td>{{ data.meta }}</td>
                <td>{{ "%.0f%%" | format(data.ratio * 100) }}</td>
                <td class="status-{{ data.status }}">{{ data.status.upper() }}</td>
            </tr>
            {% endfor %}
        </table>
    </section>
    
    <section>
        <h2>Análise Editorial (IA)</h2>
        <p>{{ gaps.observacoes_editoriais }}</p>
        {% if gaps.gaps_principais %}
        <h3>Principais Gaps</h3>
        <ul>
            {% for gap in gaps.gaps_principais %}
            <li><strong>{{ gap.categoria }}:</strong> {{ gap.motivo }} ({{ gap.urgencia }})</li>
            {% endfor %}
        </ul>
        {% endif %}
    </section>
    
    <section>
        <h2>Pesos Editoriais Publicados</h2>
        <table>
            <tr><th>Categoria</th><th>Peso</th><th>Interpretação</th></tr>
            {% for cat, peso in pesos.items() | sort(attribute='1', reverse=True) %}
            <tr>
                <td>{{ cat }}</td>
                <td>{{ "%.2f" | format(peso) }}</td>
                <td>
                    {% if peso >= 1.5 %}🔴 Boost forte
                    {% elif peso >= 1.2 %}🟡 Boost moderado
                    {% elif peso <= 0.6 %}🔵 Redução
                    {% else %}✅ Normal{% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </section>
</body>
</html>
"""
```

---

## PARTE X — MEMÓRIA DO AGENTE

### 10.1 Três Camadas de Memória

O Editor-Chefe usa as três camadas de memória do BaseAgent:

```python
# WORKING MEMORY (Redis) — dados do ciclo atual
WORKING_MEMORY_KEYS = {
    "ciclo:atual": "agent:working_memory:editor_chefe:{cycle_id}",
    "cobertura:snapshot": "editor_chefe:cobertura:{cycle_id}",
    "pesos:ativos": "editorial:pesos",
    "relatorio:ultimo": "editorial:relatorio:ultimo",
    "cobertura:historico:{cat}": "lista dos últimos 6 ratios por categoria",
}

# EPISODIC MEMORY (PostgreSQL) — histórico de ciclos
# Tabela: memoria_agentes (tipo=episodica)
# Armazena: resultado de cada ciclo, gaps detectados, pesos aplicados
# Permite: comparar hoje com semana passada

# SEMANTIC MEMORY (pgvector) — padrões de engajamento
# Tabela: memoria_agentes (tipo=semantica)
# Armazena: embeddings de padrões de cobertura bem-sucedidos
# Permite: "esse padrão de Economia + Política + Esportes teve alto engajamento antes?"
```

### 10.2 Uso da Memória Semântica

```python
async def _check_historical_patterns(
    self, 
    categoria: str,
    hora_do_dia: int
) -> dict:
    """
    Busca padrões históricos similares na memória semântica.
    
    Pergunta: "Em horários similares, como foi o engajamento de {categoria}?"
    
    Retorna padrão histórico para comparação contextual.
    """
    query_text = f"cobertura editorial {categoria} hora {hora_do_dia}:00"
    
    if not self.semantic_memory:
        return {}
    
    try:
        similar = await self.semantic_memory.search_similar_text(
            query_text=query_text,
            limit=3,
            min_similarity=0.75,
        )
        
        if similar:
            return {
                "padroes_encontrados": len(similar),
                "engajamento_historico": similar[0].get("metadata", {}).get("engagement_score"),
                "contexto": similar[0].get("conteudo", ""),
            }
    except Exception as e:
        self.logger.debug(f"Semantic memory search failed: {e}")
    
    return {}

async def _save_pattern_to_semantic_memory(
    self, 
    categoria: str,
    metricas: dict,
    resultado: str
) -> None:
    """
    Salva padrão de engajamento na memória semântica.
    
    Texto: "categoria em horário X teve engajamento Y com Z artigos"
    Metadata: métricas completas
    """
    hora_atual = datetime.utcnow().hour
    
    texto = (
        f"cobertura editorial {categoria} hora {hora_atual}:00 "
        f"engajamento {resultado} "
        f"pageviews {metricas.get('pageviews', 0)} "
        f"duracao {metricas.get('avg_session_duration', 0):.0f}s "
        f"artigos {metricas.get('artigos', 0)}"
    )
    
    if self.semantic_memory:
        await self.semantic_memory.store(
            agente="editor_chefe",
            conteudo=texto,
            metadata={
                "categoria": categoria,
                "hora": hora_atual,
                "engagement_score": metricas.get("engagement_score", 0),
                "pageviews": metricas.get("pageviews", 0),
                "avg_session_duration": metricas.get("avg_session_duration", 0),
            }
        )
```

### 10.3 Histórico de Cobertura (Working Memory)

```python
async def _update_cobertura_historico(
    self, 
    cobertura_atual: dict
) -> None:
    """
    Mantém histórico dos últimos 6 ratios de cobertura por categoria.
    Usado para detectar sub-representação persistente (3+ ciclos).
    """
    pipe = self.redis.pipeline()
    
    for categoria, dados in cobertura_atual.items():
        chave = f"editor_chefe:cobertura_historico:{categoria}"
        snap = json.dumps({
            "ratio": dados["ratio"],
            "publicados": dados["publicados"],
            "meta": dados["meta"],
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Push na frente da lista
        pipe.lpush(chave, snap)
        # Mantém apenas os últimos 6 (6 horas)
        pipe.ltrim(chave, 0, 5)
        # TTL de 12h
        pipe.expire(chave, 43200)
    
    await pipe.execute()
```

---

## PARTE XI — SCHEMAS PYDANTIC

### 11.1 Estado do Agente V3

```python
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime

class EditorChefeV3State(BaseModel):
    """
    Estado completo do Editor-Chefe V3.
    
    Diferença fundamental do V2:
    - Sem quality_decision (não aprova nem rejeita)
    - Sem article_for_review (não revisa artigos)
    - Sem assignments_made (não atribui pautas)
    - Com cycle_id, métricas, análises e relatório
    """
    
    # Identificação do ciclo
    cycle_id: str = ""
    cycle_start: Optional[str] = None
    
    # Step atual no grafo
    current_step: str = "idle"
    step_count: int = 0
    
    # Dados coletados
    artigos_por_categoria: Dict[str, int] = Field(default_factory=dict)
    artigos_recentes: List[Dict[str, Any]] = Field(default_factory=list)
    publishing_velocity: Dict[str, Any] = Field(default_factory=dict)
    ga4_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    engagement_metrics: Dict[str, Any] = Field(default_factory=dict)
    competitor_data: Dict[str, Any] = Field(default_factory=dict)
    
    # Análises calculadas
    cobertura_analise: Dict[str, Any] = Field(default_factory=dict)
    alertas_criticos: List[Dict[str, Any]] = Field(default_factory=list)
    alertas_moderados: List[Dict[str, Any]] = Field(default_factory=list)
    competitor_analysis: Dict[str, Any] = Field(default_factory=dict)
    gap_analysis: Dict[str, Any] = Field(default_factory=dict)
    
    # Outputs
    pesos_publicados: Dict[str, float] = Field(default_factory=dict)
    gaps_publicados_kafka: int = 0
    relatorio_gerado: Optional[Dict[str, Any]] = None
    
    # Custo do ciclo
    custo_llm_ciclo: float = 0.0
    
    # Erros não-fatais
    erros_coleta: List[str] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


class CoberturaCategoria(BaseModel):
    """Snapshot de cobertura de uma categoria no ciclo."""
    categoria: str
    publicados: int
    meta: int
    ratio: float
    status: str  # "critico", "baixo", "moderado", "ok"
    engagement_score: float = 0.0


class AlertaCobertura(BaseModel):
    """Alerta de categoria sub-representada."""
    categoria: str
    tipo: str  # "critico" | "baixo" | "persistente"
    publicados: int
    meta: int
    deficit: int
    ciclos_consecutivos: int = 1


class GapAnalysisResult(BaseModel):
    """Resultado da análise de gaps via LLM."""
    gaps_principais: List[Dict[str, Any]] = Field(default_factory=list)
    topicos_urgentes: List[Dict[str, Any]] = Field(default_factory=list)
    categorias_destaque: List[Dict[str, Any]] = Field(default_factory=list)
    ajustes_prioridade: Dict[str, float] = Field(default_factory=dict)
    observacoes_editoriais: str = ""


class PesoEditorial(BaseModel):
    """Peso editorial para uma categoria."""
    categoria: str
    peso: float  # 0.5 a 2.0, default 1.0
    motivo: str
    ciclo_id: str
    expira_em: str
```

### 11.2 Schema da Tabela PostgreSQL

```sql
-- Relatórios editoriais (novo, criado pela V3)
CREATE TABLE IF NOT EXISTS relatorios_editoriais (
    id              SERIAL PRIMARY KEY,
    cycle_id        VARCHAR(50) UNIQUE NOT NULL,
    gerado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    artigos_hora    INTEGER NOT NULL DEFAULT 0,
    artigos_24h     INTEGER NOT NULL DEFAULT 0,
    categorias_criticas  JSONB DEFAULT '[]',
    categorias_baixas    JSONB DEFAULT '[]',
    gaps_urgentes        JSONB DEFAULT '[]',
    pesos_editoriais     JSONB DEFAULT '{}',
    custo_llm       DECIMAL(10, 6) DEFAULT 0,
    dados_completos JSONB,
    criado_em       TIMESTAMPTZ DEFAULT NOW()
);

-- Index para consultas por data
CREATE INDEX IF NOT EXISTS idx_relatorios_gerado_em 
    ON relatorios_editoriais(gerado_em DESC);

-- View para dashboard rápido
CREATE OR REPLACE VIEW vw_editorial_dashboard AS
SELECT
    cycle_id,
    gerado_em,
    artigos_hora,
    artigos_24h,
    jsonb_array_length(categorias_criticas) AS n_categorias_criticas,
    jsonb_array_length(gaps_urgentes) AS n_gaps_urgentes,
    custo_llm,
    dados_completos->'volume'->>'on_track' AS on_track
FROM relatorios_editoriais
ORDER BY gerado_em DESC
LIMIT 24;  -- últimas 24 horas

-- Pesos históricos para análise de tendência
CREATE TABLE IF NOT EXISTS historico_pesos_editoriais (
    id          SERIAL PRIMARY KEY,
    cycle_id    VARCHAR(50) REFERENCES relatorios_editoriais(cycle_id),
    categoria   VARCHAR(100) NOT NULL,
    peso        DECIMAL(4, 2) NOT NULL,
    motivo      TEXT,
    aplicado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pesos_categoria 
    ON historico_pesos_editoriais(categoria, aplicado_em DESC);
```

---

## PARTE XII — ESTRUTURA DE DIRETÓRIOS

```
brasileira/
├── agents/
│   └── editor_chefe.py               # Agente principal (este briefing)
│
├── analytics/
│   ├── ga4_client.py                 # Cliente Google Analytics 4
│   │   ├── class GA4Client
│   │   ├── async get_article_metrics()
│   │   ├── async get_category_metrics()
│   │   └── _aggregate_by_category()
│   │
│   ├── wp_analytics_client.py        # WordPress REST API analytics
│   │   ├── class WordPressAnalyticsClient
│   │   ├── async get_posts_by_category()
│   │   ├── async get_recent_posts()
│   │   └── async get_publishing_velocity()
│   │
│   └── engagement_calculator.py     # Cálculo de métricas derivadas
│       ├── class EngagementMetrics
│       ├── calcular_engagement_score()
│       └── calcular_variacao_ciclo()
│
├── editorial/
│   ├── coverage_analyzer.py          # Análise das 16 categorias
│   │   ├── MACROCATEGORIAS_V3
│   │   ├── METAS_COBERTURA_HORA
│   │   └── analyze_coverage()
│   │
│   ├── gap_detector.py               # Detecção de gaps editoriais
│   │   ├── detect_persistent_gaps()
│   │   └── identify_trending_gaps()
│   │
│   └── priority_manager.py           # Gestão de pesos editoriais
│       ├── calculate_weights()
│       ├── publish_weights_to_redis()
│       └── publish_gaps_to_kafka()
│
├── reports/
│   ├── editorial_report.py           # Geração de relatório
│   │   ├── generate_report()
│   │   ├── save_to_postgres()
│   │   └── render_html()
│   │
│   └── templates/
│       └── editorial_report.html.j2  # Template Jinja2
│
├── config/
│   ├── editorial_config.yaml         # Metas por categoria, pesos padrão
│   └── prompts/
│       └── editor_chefe.txt          # System prompt do agente
│
└── tests/
    └── test_editor_chefe.py          # Testes do componente
```

### 12.1 Arquivo de Configuração YAML

```yaml
# brasileira/config/editorial_config.yaml

metas_cobertura_hora:
  Política: 5
  Economia: 4
  Esportes: 6
  Tecnologia: 3
  Saúde: 2
  Educação: 1
  Ciência: 1
  Cultura/Entretenimento: 3
  Mundo/Internacional: 4
  Meio Ambiente: 1
  Segurança/Justiça: 2
  Sociedade: 2
  Brasil: 3
  Regionais: 2
  Opinião/Análise: 1
  Últimas Notícias: 5

pesos_default:
  # Peso 1.0 = normal, 1.5 = boost, 0.7 = redução
  global: 1.0

limites_pesos:
  minimo: 0.5
  maximo: 2.0
  boost_critico: 1.8  # boost automático para cobertura zero

ciclo:
  intervalo_segundos: 3600  # 1 hora
  janelas:
    curto_prazo_horas: 1
    medio_prazo_horas: 6
    longo_prazo_horas: 24

llm:
  task_type: "analise_metricas"  # → tier PADRÃO
  max_tokens: 2000
  temperature: 0.3

alertas:
  critico_threshold: 0     # zero artigos = crítico
  baixo_threshold: 0.5     # <50% da meta = baixo
  persistente_ciclos: 3    # 3+ ciclos abaixo = tendência

kafka:
  topico_gaps: "pautas-gap"
  max_gaps_por_ciclo: 8    # máximo de gaps publicados por ciclo

redis:
  ttl_pesos_segundos: 7200     # 2 horas
  ttl_relatorio_segundos: 7200  # 2 horas
  ttl_historico_segundos: 43200 # 12 horas
  max_historico_por_categoria: 6
```

---

## PARTE XIII — ENTRYPOINT E CÓDIGO COMPLETO

### 13.1 Classe Principal do Agente

```python
"""
editor_chefe.py — Editor-Chefe V3: Observador Estratégico

REGRAS INVIOLÁVEIS:
1. NÃO é gatekeeper. NÃO aprova publicações. NÃO rejeita artigos.
2. Opera no FIM do pipeline como observador, não no início como bloqueador.
3. Ciclo a cada 1 hora. Não é evento-driven.
4. Usa LLM PADRÃO (task_type="analise_metricas"), não PREMIUM.
5. Custo como INFORMAÇÃO, nunca como bloqueio.
6. Outputs via Redis (pesos) e Kafka (gaps) — nunca bloqueia outros agentes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncpg
import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from brasileira.agents.base import BaseAgent
from brasileira.analytics.ga4_client import GA4Client
from brasileira.analytics.wp_analytics_client import WordPressAnalyticsClient
from brasileira.llm.smart_router import SmartLLMRouter
from brasileira.config import Settings

logger = logging.getLogger("editor_chefe_v3")


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════════

MACROCATEGORIAS_V3 = [
    "Política", "Economia", "Esportes", "Tecnologia",
    "Saúde", "Educação", "Ciência", "Cultura/Entretenimento",
    "Mundo/Internacional", "Meio Ambiente", "Segurança/Justiça",
    "Sociedade", "Brasil", "Regionais", "Opinião/Análise",
    "Últimas Notícias",
]

METAS_COBERTURA_HORA: Dict[str, int] = {
    "Política": 5, "Economia": 4, "Esportes": 6, "Tecnologia": 3,
    "Saúde": 2, "Educação": 1, "Ciência": 1, "Cultura/Entretenimento": 3,
    "Mundo/Internacional": 4, "Meio Ambiente": 1, "Segurança/Justiça": 2,
    "Sociedade": 2, "Brasil": 3, "Regionais": 2, "Opinião/Análise": 1,
    "Últimas Notícias": 5,
}

CICLO_SEGUNDOS = 3600  # 1 hora

SYSTEM_PROMPT = """Você é o Editor-Chefe estratégico da brasileira.news — um observador analítico, não um gatekeeper.

Sua função é ANALISAR dados de engajamento e cobertura já publicada, e gerar insights editoriais.
Você NUNCA bloqueia artigos. Você NUNCA rejeita conteúdo. Você NUNCA aprova publicações.
Você OBSERVA, ANALISA e RECOMENDA.

Ao analisar gaps editoriais, considere:
1. Volume: Quais categorias estão com cobertura abaixo da meta?
2. Engajamento: Quais categorias geram mais interesse dos leitores?
3. Concorrência: O que os concorrentes estão cobrindo que não cobrimos?
4. Tendências: Quais padrões se repetem em horários específicos?

Suas recomendações vão para outros agentes como SUGESTÕES com pesos de prioridade,
nunca como ordens ou bloqueios. O sistema publica primeiro e observa depois.

Responda sempre em JSON estruturado conforme solicitado."""


# ═══════════════════════════════════════════════════════════════════════════════
# STATE
# ═══════════════════════════════════════════════════════════════════════════════

class EditorChefeV3State(BaseModel):
    """Estado completo do Editor-Chefe V3."""
    
    cycle_id: str = ""
    cycle_start: Optional[str] = None
    current_step: str = "idle"
    step_count: int = 0
    
    # Dados coletados
    artigos_por_categoria: Dict[str, int] = Field(default_factory=dict)
    artigos_recentes: List[Dict[str, Any]] = Field(default_factory=list)
    publishing_velocity: Dict[str, Any] = Field(default_factory=dict)
    ga4_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    engagement_metrics: Dict[str, Any] = Field(default_factory=dict)
    competitor_data: Dict[str, Any] = Field(default_factory=dict)
    top_artigos: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Análises
    cobertura_analise: Dict[str, Any] = Field(default_factory=dict)
    alertas_criticos: List[Dict[str, Any]] = Field(default_factory=list)
    alertas_moderados: List[Dict[str, Any]] = Field(default_factory=list)
    competitor_analysis: Dict[str, Any] = Field(default_factory=dict)
    gap_analysis: Dict[str, Any] = Field(default_factory=dict)
    
    # Outputs
    pesos_publicados: Dict[str, float] = Field(default_factory=dict)
    gaps_publicados_kafka: int = 0
    relatorio_gerado: Optional[Dict[str, Any]] = None
    
    # Custo e erros
    custo_llm_ciclo: float = 0.0
    erros_coleta: List[str] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


# ═══════════════════════════════════════════════════════════════════════════════
# AGENTE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class EditorChefeAgentV3(BaseAgent):
    """
    Editor-Chefe V3 — Observador Estratégico.
    
    NÃO é gatekeeper. NÃO bloqueia artigos. NÃO aprova publicações.
    
    Ciclo de 1 hora:
    1. collect_data    — GA4 + WordPress + Redis Monitor Concorrência
    2. analyze_coverage — 16 macrocategorias vs metas
    3. analyze_engagement — pageviews, CTR, tempo leitura
    4. compare_competitors — gaps vs concorrentes
    5. identify_gaps   — LLM PADRÃO para análise estratégica
    6. adjust_priorities — pesos em Redis + gaps em Kafka
    7. generate_report  — relatório no PostgreSQL
    8. sleep(1h)        — aguarda próximo ciclo
    """
    
    def __init__(
        self,
        name: str = "editor-chefe-v3",
        settings: Optional[Settings] = None,
        llm_router: Optional[SmartLLMRouter] = None,
        redis_client: Optional[aioredis.Redis] = None,
        db_pool: Optional[asyncpg.Pool] = None,
        ga4_client: Optional[GA4Client] = None,
        wp_client: Optional[WordPressAnalyticsClient] = None,
        kafka_producer: Optional[AIOKafkaProducer] = None,
    ):
        super().__init__(
            name=name,
            agent_type="editor_chefe",
            settings=settings,
        )
        
        self.llm = llm_router
        self.redis = redis_client
        self.db = db_pool
        self.ga4 = ga4_client
        self.wp = wp_client
        self.kafka = kafka_producer
        
        self._graph = None
        self._running = False
    
    def _build_graph(self) -> StateGraph:
        """Constrói o grafo LangGraph do Editor-Chefe V3."""
        graph = StateGraph(EditorChefeV3State)
        
        # Nodes — 7 steps do ciclo
        graph.add_node("collect_data", self._step_collect_data)
        graph.add_node("analyze_coverage", self._step_analyze_coverage)
        graph.add_node("analyze_engagement", self._step_analyze_engagement)
        graph.add_node("compare_competitors", self._step_compare_competitors)
        graph.add_node("identify_gaps", self._step_identify_gaps)
        graph.add_node("adjust_priorities", self._step_adjust_priorities)
        graph.add_node("generate_report", self._step_generate_report)
        
        # Edges — fluxo linear (sem gates)
        graph.set_entry_point("collect_data")
        graph.add_edge("collect_data", "analyze_coverage")
        graph.add_edge("analyze_coverage", "analyze_engagement")
        graph.add_edge("analyze_engagement", "compare_competitors")
        graph.add_edge("compare_competitors", "identify_gaps")
        graph.add_edge("identify_gaps", "adjust_priorities")
        graph.add_edge("adjust_priorities", "generate_report")
        graph.add_edge("generate_report", END)
        
        return graph.compile()
    
    async def run_forever(self):
        """
        Loop eterno de análise. Ciclo a cada 1 hora.
        
        Nunca para, mesmo com erros em steps individuais.
        """
        self._running = True
        self._graph = self._build_graph()
        
        logger.info("Editor-Chefe V3 iniciado. Ciclo a cada 1 hora.")
        
        while self._running:
            cycle_start = datetime.utcnow()
            cycle_id = f"editorial-{cycle_start.strftime('%Y%m%d-%H%M')}"
            
            try:
                initial_state = EditorChefeV3State(
                    cycle_id=cycle_id,
                    cycle_start=cycle_start.isoformat(),
                )
                
                result = await self._graph.ainvoke(initial_state.model_dump())
                
                logger.info(
                    f"[{cycle_id}] Ciclo concluído: "
                    f"{result.get('publishing_velocity', {}).get('ultima_hora', '?')} artigos/h, "
                    f"{len(result.get('alertas_criticos', []))} alertas críticos, "
                    f"custo R${result.get('custo_llm_ciclo', 0):.4f}"
                )
                
            except Exception as e:
                logger.error(f"[{cycle_id}] Erro no ciclo: {e}", exc_info=True)
                # NUNCA quebra o loop — próximo ciclo vai tentar de novo
            
            # Dorme o tempo restante para completar 1h
            elapsed = (datetime.utcnow() - cycle_start).total_seconds()
            sleep_time = max(60, CICLO_SEGUNDOS - elapsed)  # mínimo 60s de sleep
            
            logger.debug(f"[{cycle_id}] Próximo ciclo em {sleep_time:.0f}s")
            await asyncio.sleep(sleep_time)
    
    def stop(self):
        """Para o loop graciosamente."""
        self._running = False
        logger.info("Editor-Chefe V3: stop solicitado.")
    
    # ─────────────────────────────────────────────────────────────────────────
    # STEPS DO GRAFO
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _step_collect_data(self, state: dict) -> dict:
        """
        Step 1: Coleta dados de múltiplas fontes em paralelo.
        
        Fontes: GA4 API, WordPress REST API, Redis (Monitor Concorrência)
        Graceful degradation: se uma fonte falha, continua com as outras.
        """
        logger.info(f"[{state['cycle_id']}] Step 1: collect_data")
        state["current_step"] = "collect_data"
        state["step_count"] = state.get("step_count", 0) + 1
        
        # Coleta paralela
        tasks = {
            "ga4": self._collect_ga4_metrics(),
            "wp": self._collect_wp_data(),
            "competitors": self._collect_competitor_data(),
        }
        
        results = {}
        erros = []
        
        for source, coro in tasks.items():
            try:
                results[source] = await asyncio.wait_for(coro, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout na coleta de {source}")
                erros.append(f"timeout:{source}")
                results[source] = {}
            except Exception as e:
                logger.warning(f"Erro na coleta de {source}: {e}")
                erros.append(f"error:{source}:{type(e).__name__}")
                results[source] = {}
        
        # Atualiza estado
        ga4_data = results.get("ga4", {})
        wp_data = results.get("wp", {})
        comp_data = results.get("competitors", {})
        
        state["ga4_metrics"] = ga4_data.get("artigos", [])
        state["engagement_metrics"] = ga4_data.get("por_categoria", {})
        state["top_artigos"] = ga4_data.get("artigos", [])[:10]
        
        state["artigos_por_categoria"] = wp_data.get("por_categoria", {})
        state["artigos_recentes"] = wp_data.get("recentes", [])
        state["publishing_velocity"] = wp_data.get("velocity", {})
        
        state["competitor_data"] = comp_data
        state["erros_coleta"] = erros
        
        return state
    
    async def _collect_ga4_metrics(self) -> dict:
        """Coleta métricas do GA4."""
        if not self.ga4:
            return {}
        
        artigos = await self.ga4.get_article_metrics(horas=1)
        por_categoria = await self.ga4.get_category_metrics(horas=1)
        
        return {
            "artigos": artigos,
            "por_categoria": por_categoria,
        }
    
    async def _collect_wp_data(self) -> dict:
        """Coleta dados do WordPress."""
        if not self.wp:
            return {}
        
        por_categoria, recentes, velocity = await asyncio.gather(
            self.wp.get_posts_by_category(horas=1),
            self.wp.get_recent_posts(horas=1),
            self.wp.get_publishing_velocity(),
            return_exceptions=True,
        )
        
        return {
            "por_categoria": por_categoria if not isinstance(por_categoria, Exception) else {},
            "recentes": recentes if not isinstance(recentes, Exception) else [],
            "velocity": velocity if not isinstance(velocity, Exception) else {},
        }
    
    async def _collect_competitor_data(self) -> dict:
        """Lê dados do Monitor Concorrência via Redis."""
        if not self.redis:
            return {}
        
        try:
            capas_raw = await self.redis.hgetall("concorrencia:capas:atual")
            trending_raw = await self.redis.zrevrange(
                "concorrencia:topicos:trending", 0, 19, withscores=True
            )
            gaps_raw = await self.redis.lrange("concorrencia:gap:confirmado", 0, 29)
            breaking_raw = await self.redis.lrange("concorrencia:breaking:alert", 0, 9)
            
            capas = {
                k.decode() if isinstance(k, bytes) else k: 
                json.loads(v)
                for k, v in capas_raw.items()
            }
            
            trending = [
                {"topico": t.decode() if isinstance(t, bytes) else t, "score": s}
                for t, s in (trending_raw or [])
            ]
            
            gaps = [json.loads(g) for g in (gaps_raw or []) if g]
            breaking = [json.loads(b) for b in (breaking_raw or []) if b]
            
            return {
                "capas": capas,
                "trending": trending,
                "gaps": gaps,
                "breaking": breaking,
                "coletado_em": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.warning(f"Erro ao coletar dados de concorrência: {e}")
            return {}
    
    async def _step_analyze_coverage(self, state: dict) -> dict:
        """
        Step 2: Analisa cobertura das 16 macrocategorias vs metas.
        """
        logger.info(f"[{state['cycle_id']}] Step 2: analyze_coverage")
        state["current_step"] = "analyze_coverage"
        state["step_count"] = state.get("step_count", 0) + 1
        
        artigos_por_categoria = state.get("artigos_por_categoria", {})
        
        cobertura = {}
        alertas_criticos = []
        alertas_moderados = []
        
        for categoria in MACROCATEGORIAS_V3:
            publicados = artigos_por_categoria.get(categoria, 0)
            meta = METAS_COBERTURA_HORA.get(categoria, 1)
            ratio = publicados / meta if meta > 0 else 1.0
            
            if publicados == 0:
                status = "critico"
                alertas_criticos.append({
                    "categoria": categoria,
                    "publicados": 0,
                    "meta": meta,
                    "deficit": meta,
                })
            elif ratio < 0.5:
                status = "baixo"
                alertas_moderados.append({
                    "categoria": categoria,
                    "publicados": publicados,
                    "meta": meta,
                    "deficit": meta - publicados,
                })
            elif ratio < 0.8:
                status = "moderado"
            else:
                status = "ok"
            
            cobertura[categoria] = {
                "publicados": publicados,
                "meta": meta,
                "ratio": round(ratio, 2),
                "status": status,
            }
        
        state["cobertura_analise"] = cobertura
        state["alertas_criticos"] = alertas_criticos
        state["alertas_moderados"] = alertas_moderados
        
        # Atualiza histórico no Redis
        if self.redis:
            try:
                await self._update_cobertura_historico(cobertura)
            except Exception as e:
                logger.debug(f"Falha ao atualizar histórico de cobertura: {e}")
        
        logger.info(
            f"Cobertura: {len(alertas_criticos)} críticos, "
            f"{len(alertas_moderados)} moderados, "
            f"{sum(1 for d in cobertura.values() if d['status'] == 'ok')} ok"
        )
        
        return state
    
    async def _step_analyze_engagement(self, state: dict) -> dict:
        """
        Step 3: Analisa métricas de engajamento (pageviews, CTR, tempo leitura).
        """
        logger.info(f"[{state['cycle_id']}] Step 3: analyze_engagement")
        state["current_step"] = "analyze_engagement"
        state["step_count"] = state.get("step_count", 0) + 1
        
        engagement = state.get("engagement_metrics", {})
        cobertura = state.get("cobertura_analise", {})
        
        # Enriquece engagement com dados de cobertura
        engagement_enriquecido = {}
        for categoria in MACROCATEGORIAS_V3:
            eng_data = engagement.get(categoria, {})
            cov_data = cobertura.get(categoria, {})
            
            pageviews = eng_data.get("pageviews", 0)
            artigos = cov_data.get("publicados", 1) or 1
            avg_duration = eng_data.get("avg_session_duration", 0.0)
            
            # Score de engajamento composto
            score_pv = min(100.0, (pageviews / max(artigos, 1) / 500) * 100)
            score_dur = min(100.0, (avg_duration / 120) * 100)
            engagement_score = (0.6 * score_pv) + (0.4 * score_dur)
            
            engagement_enriquecido[categoria] = {
                **eng_data,
                "artigos": artigos,
                "pageviews_por_artigo": round(pageviews / artigos, 1),
                "engagement_score": round(engagement_score, 1),
            }
        
        # Ordena por engajamento
        ranking = sorted(
            engagement_enriquecido.items(),
            key=lambda x: x[1].get("engagement_score", 0),
            reverse=True,
        )
        
        state["engagement_metrics"] = engagement_enriquecido
        state["engagement_ranking"] = [r[0] for r in ranking]
        
        logger.debug(
            f"Top engajamento: {', '.join([r[0] for r in ranking[:3]])}"
        )
        
        return state
    
    async def _step_compare_competitors(self, state: dict) -> dict:
        """
        Step 4: Compara cobertura com concorrentes.
        """
        logger.info(f"[{state['cycle_id']}] Step 4: compare_competitors")
        state["current_step"] = "compare_competitors"
        state["step_count"] = state.get("step_count", 0) + 1
        
        competitor_data = state.get("competitor_data", {})
        artigos_recentes = state.get("artigos_recentes", [])
        
        # Extrai tópicos cobertos
        nossos_topicos = set(
            a.get("titulo", "").lower()[:40]
            for a in artigos_recentes
        )
        
        # Analisa gaps
        gaps_urgentes = [
            g for g in competitor_data.get("gaps", [])
            if g.get("urgencia") == "alta" or 
               int(g.get("concorrentes_cobrindo", 0)) >= 3
        ]
        
        gaps_moderados = [
            g for g in competitor_data.get("gaps", [])
            if g not in gaps_urgentes
        ]
        
        # Trending não coberto
        trending_nao_coberto = [
            t for t in competitor_data.get("trending", [])[:15]
            if not any(
                t.get("topico", "")[:20].lower() in tp
                for tp in nossos_topicos
            )
        ]
        
        # Cobertura de breaking news
        breaking = competitor_data.get("breaking", [])
        breaking_cobertos = sum(
            1 for b in breaking
            if any(
                b.get("topico", "")[:25].lower() in tp
                for tp in nossos_topicos
            )
        )
        
        alinhamento_pct = (
            breaking_cobertos / max(1, len(breaking))
        ) * 100 if breaking else 100.0
        
        state["competitor_analysis"] = {
            "gaps_urgentes": gaps_urgentes[:5],
            "gaps_moderados": gaps_moderados[:10],
            "trending_nao_cobertos": trending_nao_coberto[:5],
            "breaking_detectados": len(breaking),
            "breaking_cobertos": breaking_cobertos,
            "alinhamento_agenda_pct": round(alinhamento_pct, 1),
        }
        
        return state
    
    async def _step_identify_gaps(self, state: dict) -> dict:
        """
        Step 5: Usa LLM PADRÃO para identificar e priorizar gaps editoriais.
        """
        logger.info(f"[{state['cycle_id']}] Step 5: identify_gaps (LLM PADRÃO)")
        state["current_step"] = "identify_gaps"
        state["step_count"] = state.get("step_count", 0) + 1
        
        if not self.llm:
            logger.warning("LLM não configurado — usando análise sem IA")
            state["gap_analysis"] = self._fallback_gap_analysis(state)
            return state
        
        contexto = self._prepare_llm_context(state)
        
        prompt = f"""Você é o Editor-Chefe estratégico da brasileira.news.
Analise os dados do ciclo editorial e identifique gaps de cobertura.

DADOS DO CICLO {state['cycle_id']}:
{json.dumps(contexto, ensure_ascii=False, indent=2)}

Identifique:
1. As 3 categorias mais sub-representadas que precisam de mais cobertura imediata
2. Os 5 tópicos mais urgentes não cobertos (baseado em concorrência + trending)
3. As 2 categorias com melhor engajamento (manter/ampliar)
4. Ajustes de prioridade recomendados (escala 0.5 a 2.0, sendo 1.0 = normal)

IMPORTANTE: Suas recomendações são sugestões. Nenhum artigo é bloqueado.
Os pesos vão para o Redis como sinais de prioridade, não como ordens.

Responda em JSON:
{{
  "gaps_principais": [
    {{"categoria": "...", "urgencia": "alta|media|baixa", "motivo": "..."}}
  ],
  "topicos_urgentes": [
    {{"topico": "...", "categoria": "...", "motivo": "...", "urgencia": "alta|media"}}
  ],
  "categorias_destaque": [
    {{"categoria": "...", "engagement_score": 0-100, "recomendacao": "..."}}
  ],
  "ajustes_prioridade": {{
    "Política": 1.0,
    "Economia": 1.0
  }},
  "observacoes_editoriais": "análise estratégica em texto livre"
}}"""

        try:
            response = await self.llm.route_request(
                task_type="analise_metricas",  # ← TIER PADRÃO
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                agent_id=self.agent_id,
                max_tokens=2000,
                temperature=0.3,
            )
            
            content = response.content if hasattr(response, "content") else str(response)
            
            # Registra custo
            if hasattr(response, "usage") and response.usage:
                custo_estimado = (
                    response.usage.prompt_tokens * 0.0003 +
                    response.usage.completion_tokens * 0.0006
                ) / 1000  # em USD aproximado
                state["custo_llm_ciclo"] = state.get("custo_llm_ciclo", 0.0) + custo_estimado
            
            analysis = self._safe_parse_llm_json(
                content,
                default=self._fallback_gap_analysis(state),
                context="gap_analysis"
            )
            
            state["gap_analysis"] = analysis
            
        except Exception as e:
            logger.warning(f"LLM gap analysis falhou: {e}. Usando fallback.")
            state["gap_analysis"] = self._fallback_gap_analysis(state)
        
        return state
    
    def _fallback_gap_analysis(self, state: dict) -> dict:
        """Gap analysis sem LLM — baseado apenas nas métricas brutas."""
        alertas_criticos = state.get("alertas_criticos", [])
        alertas_moderados = state.get("alertas_moderados", [])
        competitor = state.get("competitor_analysis", {})
        
        gaps_principais = [
            {"categoria": a["categoria"], "urgencia": "alta", "motivo": "cobertura zero"}
            for a in alertas_criticos[:3]
        ] + [
            {"categoria": a["categoria"], "urgencia": "media", "motivo": "abaixo da meta"}
            for a in alertas_moderados[:2]
        ]
        
        return {
            "gaps_principais": gaps_principais,
            "topicos_urgentes": competitor.get("gaps_urgentes", [])[:5],
            "categorias_destaque": [],
            "ajustes_prioridade": {
                a["categoria"]: 1.8 for a in alertas_criticos[:3]
            },
            "observacoes_editoriais": (
                f"Análise automática (LLM indisponível): "
                f"{len(alertas_criticos)} categorias com cobertura zero, "
                f"{len(alertas_moderados)} categorias abaixo da meta."
            ),
        }
    
    async def _step_adjust_priorities(self, state: dict) -> dict:
        """
        Step 6: Ajusta pesos editoriais e publica no Redis e Kafka.
        
        REGRA: Pesos são SUGESTÕES. Não bloqueiam nada.
        """
        logger.info(f"[{state['cycle_id']}] Step 6: adjust_priorities")
        state["current_step"] = "adjust_priorities"
        state["step_count"] = state.get("step_count", 0) + 1
        
        gap_analysis = state.get("gap_analysis", {})
        alertas_criticos = state.get("alertas_criticos", [])
        ajustes_llm = gap_analysis.get("ajustes_prioridade", {})
        
        pesos_finais = {}
        
        for categoria in MACROCATEGORIAS_V3:
            peso_base = 1.0
            
            # Boost automático para cobertura zero
            if any(a["categoria"] == categoria for a in alertas_criticos):
                peso_base = 1.8
            
            # Blenda com ajuste LLM
            if categoria in ajustes_llm:
                try:
                    peso_llm = float(ajustes_llm[categoria])
                    peso_base = (peso_base + peso_llm) / 2.0
                except (ValueError, TypeError):
                    pass
            
            # Clamp rigoroso
            pesos_finais[categoria] = round(max(0.5, min(2.0, peso_base)), 2)
        
        # Publica no Redis
        if self.redis:
            try:
                pipe = self.redis.pipeline()
                pipe.hset("editorial:pesos", mapping={
                    cat: str(peso) for cat, peso in pesos_finais.items()
                })
                pipe.expire("editorial:pesos", 7200)
                pipe.set("editorial:pesos:updated_at", datetime.utcnow().isoformat(), ex=7200)
                pipe.set("editorial:pesos:cycle_id", state["cycle_id"], ex=7200)
                await pipe.execute()
                logger.info(f"Pesos publicados no Redis: {len(pesos_finais)} categorias")
            except Exception as e:
                logger.warning(f"Falha ao publicar pesos no Redis: {e}")
        
        state["pesos_publicados"] = pesos_finais
        
        # Publica gaps urgentes no Kafka
        gaps_publicados = await self._publish_gaps_to_kafka(state)
        state["gaps_publicados_kafka"] = gaps_publicados
        
        return state
    
    async def _publish_gaps_to_kafka(self, state: dict) -> int:
        """
        Publica gaps urgentes no Kafka pautas-gap.
        
        Retorna número de gaps publicados.
        """
        if not self.kafka:
            return 0
        
        gap_analysis = state.get("gap_analysis", {})
        competitor = state.get("competitor_analysis", {})
        
        todos_gaps = []
        
        for topico in gap_analysis.get("topicos_urgentes", [])[:5]:
            todos_gaps.append({
                "topico": topico.get("topico", ""),
                "categoria": topico.get("categoria", "Geral"),
                "origem": "editor_chefe_analise",
                "urgencia": topico.get("urgencia", "media"),
                "motivo": topico.get("motivo", ""),
                "sugerido_em": datetime.utcnow().isoformat(),
                "sugerido_por": self.agent_id,
            })
        
        for gap in competitor.get("gaps_urgentes", [])[:3]:
            todos_gaps.append({
                "topico": gap.get("topico", ""),
                "categoria": gap.get("categoria", "Geral"),
                "origem": "competitor_gap",
                "urgencia": "alta",
                "motivo": f"Coberto por concorrentes",
                "sugerido_em": datetime.utcnow().isoformat(),
                "sugerido_por": self.agent_id,
            })
        
        publicados = 0
        for gap in todos_gaps[:8]:  # máximo 8 por ciclo
            try:
                await self.kafka.send_and_wait(
                    "pautas-gap",
                    key=gap["categoria"].encode(),
                    value=json.dumps(gap, ensure_ascii=False).encode(),
                )
                publicados += 1
            except Exception as e:
                logger.warning(f"Falha ao publicar gap no Kafka: {e}")
        
        if publicados:
            logger.info(f"Publicados {publicados} gaps no Kafka pautas-gap")
        
        return publicados
    
    async def _step_generate_report(self, state: dict) -> dict:
        """
        Step 7: Gera relatório editorial completo.
        
        Salva no PostgreSQL e Redis.
        """
        logger.info(f"[{state['cycle_id']}] Step 7: generate_report")
        state["current_step"] = "generate_report"
        state["step_count"] = state.get("step_count", 0) + 1
        
        velocity = state.get("publishing_velocity", {})
        cobertura = state.get("cobertura_analise", {})
        gap_analysis = state.get("gap_analysis", {})
        competitor = state.get("competitor_analysis", {})
        
        relatorio = {
            "cycle_id": state["cycle_id"],
            "gerado_em": datetime.utcnow().isoformat(),
            "periodo_horas": 1,
            "volume": velocity,
            "cobertura": {
                "criticas": [a["categoria"] for a in state.get("alertas_criticos", [])],
                "baixas": [a["categoria"] for a in state.get("alertas_moderados", [])],
                "ok": [
                    cat for cat, d in cobertura.items()
                    if d.get("status") == "ok"
                ],
                "detalhes": cobertura,
            },
            "engajamento": {
                "por_categoria": state.get("engagement_metrics", {}),
                "ranking": state.get("engagement_ranking", []),
                "top_artigos": state.get("top_artigos", []),
            },
            "concorrentes": competitor,
            "gaps": gap_analysis,
            "pesos_editoriais": state.get("pesos_publicados", {}),
            "gaps_publicados_kafka": state.get("gaps_publicados_kafka", 0),
            "custo_ciclo_usd": state.get("custo_llm_ciclo", 0.0),
            "erros_coleta": state.get("erros_coleta", []),
        }
        
        # Salva no PostgreSQL
        if self.db:
            try:
                await self._save_report_to_postgres(relatorio)
            except Exception as e:
                logger.warning(f"Falha ao salvar relatório no PostgreSQL: {e}")
        
        # Salva no Redis para consulta rápida
        if self.redis:
            try:
                await self.redis.set(
                    "editorial:relatorio:ultimo",
                    json.dumps(relatorio, ensure_ascii=False, default=str),
                    ex=7200,
                )
            except Exception as e:
                logger.debug(f"Falha ao salvar relatório no Redis: {e}")
        
        # Salva na memória episódica
        if self.episodic_memory:
            try:
                await self.episodic_memory.store(
                    agente="editor_chefe",
                    tipo="ciclo_editorial",
                    conteudo=json.dumps(relatorio, default=str),
                )
            except Exception as e:
                logger.debug(f"Falha ao salvar memória episódica: {e}")
        
        state["relatorio_gerado"] = relatorio
        return state
    
    async def _save_report_to_postgres(self, relatorio: dict) -> None:
        """Persiste relatório editorial no PostgreSQL."""
        if not self.db:
            return
        
        query = """
            INSERT INTO relatorios_editoriais (
                cycle_id, gerado_em, artigos_hora, artigos_24h,
                categorias_criticas, categorias_baixas,
                gaps_urgentes, pesos_editoriais,
                custo_llm, dados_completos
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (cycle_id) DO UPDATE SET
                dados_completos = EXCLUDED.dados_completos
        """
        
        vol = relatorio.get("volume", {})
        cob = relatorio.get("cobertura", {})
        gaps = relatorio.get("concorrentes", {})
        
        await self.db.execute(
            query,
            relatorio["cycle_id"],
            datetime.fromisoformat(relatorio["gerado_em"]),
            vol.get("ultima_hora", 0),
            vol.get("ultimas_24h", 0),
            json.dumps(cob.get("criticas", [])),
            json.dumps(cob.get("baixas", [])),
            json.dumps(gaps.get("gaps_urgentes", [])),
            json.dumps(relatorio.get("pesos_editoriais", {})),
            relatorio.get("custo_ciclo_usd", 0.0),
            json.dumps(relatorio, default=str),
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────
    
    def _prepare_llm_context(self, state: dict) -> dict:
        """Prepara contexto compacto para o LLM."""
        cobertura = state.get("cobertura_analise", {})
        engagement = state.get("engagement_metrics", {})
        competitor = state.get("competitor_analysis", {})
        velocity = state.get("publishing_velocity", {})
        
        return {
            "periodo": "última 1 hora",
            "velocity": {
                "artigos_ultima_hora": velocity.get("ultima_hora", 0),
                "meta_diaria": velocity.get("meta_diaria", 1000),
                "on_track": velocity.get("on_track", True),
                "projecao_diaria": velocity.get("projecao_diaria", 0),
            },
            "cobertura_por_categoria": {
                cat: {
                    "publicados": data["publicados"],
                    "meta": data["meta"],
                    "status": data["status"],
                }
                for cat, data in cobertura.items()
            },
            "categorias_sem_cobertura": [
                cat for cat, data in cobertura.items()
                if data.get("status") == "critico"
            ],
            "categorias_baixas": [
                cat for cat, data in cobertura.items()
                if data.get("status") == "baixo"
            ],
            "top_engajamento": {
                cat: {
                    "pageviews": eng.get("pageviews", 0),
                    "score": eng.get("engagement_score", 0),
                }
                for cat, eng in sorted(
                    engagement.items(),
                    key=lambda x: x[1].get("engagement_score", 0),
                    reverse=True,
                )[:5]
            },
            "gaps_concorrencia_urgentes": competitor.get("gaps_urgentes", [])[:3],
            "alinhamento_agenda_pct": competitor.get("alinhamento_agenda_pct", 100),
        }
    
    def _safe_parse_llm_json(
        self,
        content: str,
        default: dict,
        context: str = "LLM response",
    ) -> dict:
        """Parse defensivo de JSON com 3 estratégias."""
        import re
        
        # Estratégia 1: regex para extrair JSON
        try:
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                return json.loads(match.group())
        except json.JSONDecodeError:
            pass
        
        # Estratégia 2: parse direto
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass
        
        # Estratégia 3: remove markdown code blocks
        try:
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split('\n')
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = '\n'.join(lines)
            return json.loads(cleaned)
        except Exception:
            pass
        
        logger.warning(f"Falha ao parsear JSON em {context}. Usando default.")
        return default
    
    async def _update_cobertura_historico(self, cobertura: dict) -> None:
        """Atualiza histórico de cobertura por categoria no Redis."""
        if not self.redis:
            return
        
        pipe = self.redis.pipeline()
        for categoria, dados in cobertura.items():
            chave = f"editor_chefe:cobertura_historico:{categoria}"
            snap = json.dumps({
                "ratio": dados["ratio"],
                "publicados": dados["publicados"],
                "timestamp": datetime.utcnow().isoformat(),
            })
            pipe.lpush(chave, snap)
            pipe.ltrim(chave, 0, 5)
            pipe.expire(chave, 43200)
        
        await pipe.execute()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    """Entrypoint do Editor-Chefe V3."""
    import os
    from brasileira.config import Settings
    from brasileira.llm.smart_router import SmartLLMRouter
    
    settings = Settings()
    
    # Inicializa clientes
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False,
    )
    
    db_pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=2,
        max_size=5,
    )
    
    llm_router = SmartLLMRouter(settings=settings)
    
    # GA4 (opcional — graceful se não configurado)
    ga4_client = None
    if os.getenv("GA4_PROPERTY_ID") and os.getenv("GA4_CREDENTIALS_PATH"):
        try:
            ga4_client = GA4Client(
                property_id=os.getenv("GA4_PROPERTY_ID"),
                credentials_path=os.getenv("GA4_CREDENTIALS_PATH"),
            )
            logger.info("GA4 client inicializado")
        except Exception as e:
            logger.warning(f"GA4 client falhou: {e}. Continuando sem GA4.")
    
    # WordPress client
    wp_client = WordPressAnalyticsClient(
        wp_url=settings.WP_URL,
        wp_user=settings.WP_USER,
        wp_password=settings.WP_APP_PASSWORD,
    )
    
    # Kafka producer
    kafka_producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BROKERS,
        value_serializer=lambda v: v,
        key_serializer=lambda k: k,
    )
    await kafka_producer.start()
    
    # Agente
    agente = EditorChefeAgentV3(
        name="editor-chefe-v3-01",
        settings=settings,
        llm_router=llm_router,
        redis_client=redis_client,
        db_pool=db_pool,
        ga4_client=ga4_client,
        wp_client=wp_client,
        kafka_producer=kafka_producer,
    )
    
    logger.info("Iniciando Editor-Chefe V3...")
    
    try:
        await agente.run_forever()
    except KeyboardInterrupt:
        logger.info("Interrupt recebido. Parando...")
    finally:
        agente.stop()
        await kafka_producer.stop()
        await db_pool.close()
        await redis_client.close()
        if wp_client:
            await wp_client.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(main())
```

---

## PARTE XIV — TESTES

### 14.1 Estrutura de Testes

```python
# tests/test_editor_chefe.py

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from brasileira.agents.editor_chefe import (
    EditorChefeAgentV3,
    EditorChefeV3State,
    MACROCATEGORIAS_V3,
    METAS_COBERTURA_HORA,
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.hgetall.return_value = {}
    redis.zrevrange.return_value = []
    redis.lrange.return_value = []
    redis.hset.return_value = True
    redis.set.return_value = True
    redis.expire.return_value = True
    redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    redis.pipeline.return_value.__aexit__ = AsyncMock(return_value=False)
    return redis

@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    response = MagicMock()
    response.content = """
    {
        "gaps_principais": [
            {"categoria": "Educação", "urgencia": "alta", "motivo": "cobertura zero"}
        ],
        "topicos_urgentes": [
            {"topico": "Novo Enem", "categoria": "Educação", "urgencia": "alta", "motivo": "trending"}
        ],
        "categorias_destaque": [
            {"categoria": "Esportes", "engagement_score": 85, "recomendacao": "manter volume"}
        ],
        "ajustes_prioridade": {"Educação": 1.8, "Esportes": 1.0},
        "observacoes_editoriais": "Cobertura de Educação precisa de atenção urgente."
    }
    """
    response.usage = MagicMock(prompt_tokens=500, completion_tokens=200)
    llm.route_request.return_value = response
    return llm

@pytest.fixture
def mock_wp():
    wp = AsyncMock()
    wp.get_posts_by_category.return_value = {
        "Política": 8,
        "Esportes": 15,
        "Economia": 3,
        "Tecnologia": 5,
        # Educação ausente = 0 artigos
    }
    wp.get_recent_posts.return_value = [
        {"id": 1, "titulo": "Artigo Teste", "categoria": "Política", "url": "http://test.com/1"},
    ]
    wp.get_publishing_velocity.return_value = {
        "ultima_hora": 42,
        "ultimas_6h": 200,
        "ultimas_24h": 980,
        "meta_diaria": 1000,
        "on_track": True,
        "projecao_diaria": 1008,
    }
    return wp

@pytest.fixture
def agente(mock_redis, mock_llm, mock_wp):
    return EditorChefeAgentV3(
        name="test-editor-chefe",
        redis_client=mock_redis,
        llm_router=mock_llm,
        wp_client=mock_wp,
    )

@pytest.fixture
def state_inicial():
    return EditorChefeV3State(
        cycle_id="editorial-test-20260326-1000",
        cycle_start=datetime.utcnow().isoformat(),
    ).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# TESTES DE ARQUITETURA (REGRAS INVIOLÁVEIS)
# ─────────────────────────────────────────────────────────────────────────────

class TestArquiteturaInviolavel:
    """
    Testes que verificam as regras INVIOLÁVEIS do Editor-Chefe V3.
    Se qualquer desses falhar, a implementação está ERRADA.
    """
    
    def test_nao_tem_quality_gate(self):
        """Editor-Chefe V3 NÃO deve ter método quality_gate."""
        agente = EditorChefeAgentV3.__new__(EditorChefeAgentV3)
        assert not hasattr(agente, '_step_quality_gate'), (
            "VIOLAÇÃO: Editor-Chefe V3 não pode ter quality_gate"
        )
    
    def test_nao_tem_quality_decision(self):
        """Não deve existir QualityDecision ou equivalente."""
        import brasileira.agents.editor_chefe as module
        assert not hasattr(module, 'QualityDecision'), (
            "VIOLAÇÃO: QualityDecision removida na V3"
        )
    
    def test_nao_tem_review_article(self):
        """Não deve ter método para revisar artigos pré-publicação."""
        agente = EditorChefeAgentV3.__new__(EditorChefeAgentV3)
        assert not hasattr(agente, 'review_article'), (
            "VIOLAÇÃO: review_article não existe no Editor-Chefe V3"
        )
    
    def test_grafo_nao_tem_node_quality_gate(self, agente):
        """Grafo LangGraph não deve conter node 'quality_gate'."""
        graph = agente._build_graph()
        # Verifica nos nodes do grafo compilado
        graph_nodes = list(graph.nodes.keys()) if hasattr(graph, 'nodes') else []
        assert "quality_gate" not in graph_nodes, (
            "VIOLAÇÃO: quality_gate não pode ser node do grafo V3"
        )
    
    def test_grafo_tem_todos_steps_corretos(self, agente):
        """Grafo deve ter os 7 steps do ciclo observador."""
        graph = agente._build_graph()
        expected_nodes = {
            "collect_data",
            "analyze_coverage",
            "analyze_engagement",
            "compare_competitors",
            "identify_gaps",
            "adjust_priorities",
            "generate_report",
        }
        # Verifica que os steps existem nos métodos do agente
        for step in expected_nodes:
            method = f"_step_{step}"
            assert hasattr(agente, method), (
                f"FALTANDO: método {method} deve existir no agente"
            )
    
    def test_llm_task_type_e_padrao(self, agente, state_inicial):
        """LLM deve usar task_type='analise_metricas' (tier PADRÃO)."""
        # Mock do router para capturar o task_type
        agente.llm = AsyncMock()
        response = MagicMock()
        response.content = '{"gaps_principais": [], "topicos_urgentes": [], "ajustes_prioridade": {}, "categorias_destaque": [], "observacoes_editoriais": ""}'
        response.usage = None
        agente.llm.route_request = AsyncMock(return_value=response)
        
        # Injeta dados para o step funcionar
        state_com_dados = {
            **state_inicial,
            "cobertura_analise": {},
            "engagement_metrics": {},
            "competitor_analysis": {},
            "publishing_velocity": {},
        }
        
        # Executa o step
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            agente._step_identify_gaps(state_com_dados)
        )
        
        # Verifica que foi chamado com task_type correto
        call_kwargs = agente.llm.route_request.call_args
        assert call_kwargs.kwargs.get("task_type") == "analise_metricas", (
            "VIOLAÇÃO: Editor-Chefe deve usar task_type='analise_metricas' (PADRÃO), não PREMIUM"
        )
    
    def test_16_macrocategorias_cobertas(self, agente, state_inicial):
        """analyze_coverage deve cobrir EXATAMENTE 16 macrocategorias."""
        # Estado com artigos para algumas categorias
        state = {
            **state_inicial,
            "artigos_por_categoria": {
                "Política": 5,
                "Esportes": 10,
            }
        }
        
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            agente._step_analyze_coverage(state)
        )
        
        cobertura = result["cobertura_analise"]
        assert len(cobertura) == 16, (
            f"VIOLAÇÃO: Devem ser 16 macrocategorias, encontradas {len(cobertura)}"
        )
        
        for cat in MACROCATEGORIAS_V3:
            assert cat in cobertura, f"Categoria '{cat}' não encontrada na análise"
    
    def test_pesos_dentro_dos_limites(self, agente, state_inicial):
        """Todos os pesos publicados devem estar entre 0.5 e 2.0."""
        state = {
            **state_inicial,
            "alertas_criticos": [
                {"categoria": "Educação", "publicados": 0, "meta": 1, "deficit": 1}
            ],
            "gap_analysis": {
                "ajustes_prioridade": {
                    "Política": 3.0,  # Propositalmente fora do limite
                    "Economia": 0.1,  # Propositalmente fora do limite
                }
            },
        }
        
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            agente._step_adjust_priorities(state)
        )
        
        pesos = result["pesos_publicados"]
        for categoria, peso in pesos.items():
            assert 0.5 <= peso <= 2.0, (
                f"VIOLAÇÃO: Peso de {categoria} = {peso} está fora dos limites [0.5, 2.0]"
            )


# ─────────────────────────────────────────────────────────────────────────────
# TESTES FUNCIONAIS
# ─────────────────────────────────────────────────────────────────────────────

class TestCicloCompleto:
    """Testes do fluxo completo de análise."""
    
    @pytest.mark.asyncio
    async def test_collect_data_graceful_degradation(self, agente, state_inicial):
        """Se GA4 falha, deve continuar com dados do WordPress."""
        # GA4 vai falhar
        agente.ga4 = AsyncMock()
        agente.ga4.get_article_metrics.side_effect = Exception("GA4 unavailable")
        agente.ga4.get_category_metrics.side_effect = Exception("GA4 unavailable")
        
        # WordPress funciona
        agente.wp = agente.wp  # fixture já configurado
        
        result = await agente._step_collect_data(state_inicial)
        
        # Deve ter continuado sem GA4
        assert "timeout:ga4" in result["erros_coleta"] or \
               "error:ga4:Exception" in result["erros_coleta"]
        
        # Dados do WordPress devem estar presentes
        assert isinstance(result["artigos_por_categoria"], dict)
    
    @pytest.mark.asyncio
    async def test_analyze_coverage_detecta_critico(self, agente, state_inicial):
        """Categorias sem artigos devem ser marcadas como críticas."""
        state = {
            **state_inicial,
            "artigos_por_categoria": {
                "Política": 5,
                # Educação ausente = 0 artigos
                "Esportes": 10,
            }
        }
        
        result = await agente._step_analyze_coverage(state)
        
        # Educação deve ser crítica
        cobertura = result["cobertura_analise"]
        assert "Educação" in cobertura
        assert cobertura["Educação"]["status"] == "critico"
        assert cobertura["Educação"]["publicados"] == 0
        
        # Deve estar nos alertas críticos
        criticos = [a["categoria"] for a in result["alertas_criticos"]]
        assert "Educação" in criticos
    
    @pytest.mark.asyncio
    async def test_boost_automatico_para_categoria_critica(self, agente, state_inicial):
        """Categorias com cobertura zero devem receber boost de 1.8."""
        state = {
            **state_inicial,
            "alertas_criticos": [
                {"categoria": "Meio Ambiente", "publicados": 0, "meta": 1, "deficit": 1}
            ],
            "gap_analysis": {"ajustes_prioridade": {}},
        }
        
        result = await agente._step_adjust_priorities(state)
        pesos = result["pesos_publicados"]
        
        assert "Meio Ambiente" in pesos
        # Boost de 1.8 para cobertura zero
        # (sem ajuste LLM, fica 1.8 mesmo)
        assert pesos["Meio Ambiente"] == 1.8
    
    @pytest.mark.asyncio
    async def test_fallback_sem_llm(self, agente, state_inicial):
        """Deve funcionar mesmo sem LLM disponível."""
        agente.llm = None  # Sem LLM
        
        state = {
            **state_inicial,
            "cobertura_analise": {
                "Educação": {"publicados": 0, "meta": 1, "ratio": 0.0, "status": "critico"}
            },
            "alertas_criticos": [
                {"categoria": "Educação", "publicados": 0, "meta": 1, "deficit": 1}
            ],
            "alertas_moderados": [],
            "engagement_metrics": {},
            "competitor_analysis": {"gaps_urgentes": []},
            "publishing_velocity": {},
        }
        
        result = await agente._step_identify_gaps(state)
        
        # Deve ter usado o fallback
        assert result["gap_analysis"] is not None
        assert "gaps_principais" in result["gap_analysis"]
        # Educação deve aparecer como gap principal
        gaps = [g["categoria"] for g in result["gap_analysis"]["gaps_principais"]]
        assert "Educação" in gaps
    
    @pytest.mark.asyncio
    async def test_gaps_publicados_no_kafka(self, agente, state_inicial):
        """Gaps urgentes devem ser publicados no Kafka pautas-gap."""
        kafka_mock = AsyncMock()
        kafka_mock.send_and_wait = AsyncMock()
        agente.kafka = kafka_mock
        
        state = {
            **state_inicial,
            "gap_analysis": {
                "topicos_urgentes": [
                    {"topico": "Enem 2026", "categoria": "Educação", "urgencia": "alta", "motivo": "test"},
                ],
            },
            "competitor_analysis": {
                "gaps_urgentes": [
                    {"topico": "Copa do Mundo", "categoria": "Esportes"},
                ],
            },
            "alertas_criticos": [],
            "pesos_publicados": {},
        }
        
        result = await agente._step_adjust_priorities(state)
        
        # Kafka deve ter sido chamado
        assert kafka_mock.send_and_wait.called
        assert result["gaps_publicados_kafka"] > 0
    
    def test_safe_parse_llm_json_estrategia_1(self, agente):
        """Deve parsear JSON embutido em texto."""
        content = 'Aqui está a análise: {"key": "value", "num": 42} mais texto'
        result = agente._safe_parse_llm_json(content, {}, "test")
        assert result == {"key": "value", "num": 42}
    
    def test_safe_parse_llm_json_estrategia_3(self, agente):
        """Deve parsear JSON dentro de bloco markdown."""
        content = '```json\n{"key": "value"}\n```'
        result = agente._safe_parse_llm_json(content, {}, "test")
        assert result == {"key": "value"}
    
    def test_safe_parse_llm_json_fallback(self, agente):
        """Deve retornar default quando JSON não é encontrado."""
        default = {"default": True}
        result = agente._safe_parse_llm_json("texto sem json nenhum", default, "test")
        assert result == default


# ─────────────────────────────────────────────────────────────────────────────
# TESTES DE INTEGRAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegracao:
    """Testes de integração entre os steps."""
    
    @pytest.mark.asyncio
    async def test_fluxo_step1_para_step2(self, agente, state_inicial, mock_wp, mock_redis):
        """collect_data → analyze_coverage deve funcionar em sequência."""
        # Step 1
        state = await agente._step_collect_data(state_inicial)
        
        # State deve ter dados do WP
        assert isinstance(state["artigos_por_categoria"], dict)
        
        # Step 2
        state = await agente._step_analyze_coverage(state)
        
        # Deve ter analisado 16 categorias
        assert len(state["cobertura_analise"]) == 16
    
    @pytest.mark.asyncio
    async def test_estado_nunca_tem_quality_decision(self, agente, state_inicial):
        """Estado final não deve conter quality_decision."""
        state = EditorChefeV3State(**state_inicial).model_dump()
        
        assert "quality_decision" not in state
        assert "articles_approved" not in state
        assert "articles_rejected" not in state
        assert "quality_feedback" not in state
```

---

## PARTE XV — CHECKLIST DE IMPLEMENTAÇÃO

### 15.1 Verificação das Regras Invioláveis

Antes de fazer merge, execute este checklist manualmente:

- [ ] **REGRA #1:** `grep -n "quality_gate\|QualityDecision\|KILL\|HOLD" editor_chefe.py` → deve retornar 0 resultados
- [ ] **REGRA #2:** `grep -n "review_article\|artigos_aprovados\|artigos_rejeitados" editor_chefe.py` → deve retornar 0 resultados
- [ ] **REGRA #3:** Step `identify_gaps` usa `task_type="analise_metricas"` (não `"redacao_artigo"` nem `"pauta_especial"`)
- [ ] **REGRA #4:** Pesos publicados via `redis.hset("editorial:pesos", ...)` com TTL de 7200s
- [ ] **REGRA #5:** Loop principal com `asyncio.sleep(3600)` — ciclo de 1 hora
- [ ] **REGRA #6:** `run_forever()` nunca quebra por exceção em um ciclo
- [ ] **REGRA #7:** Custo LLM logado como informação — nunca interrompe ciclo
- [ ] **REGRA #8:** 16 macrocategorias (não 5 editorias) em `MACROCATEGORIAS_V3`

### 15.2 Checklist de Implementação Técnica

**Fase 1 — Estrutura Base:**
- [ ] Criar `brasileira/agents/editor_chefe.py` com classe `EditorChefeAgentV3`
- [ ] Criar `brasileira/analytics/ga4_client.py` com `GA4Client`
- [ ] Criar `brasileira/analytics/wp_analytics_client.py` com `WordPressAnalyticsClient`
- [ ] Criar `brasileira/editorial/coverage_analyzer.py`
- [ ] Criar `brasileira/editorial/priority_manager.py`

**Fase 2 — PostgreSQL:**
- [ ] Criar tabela `relatorios_editoriais` (SQL na Seção 11.2)
- [ ] Criar tabela `historico_pesos_editoriais` (SQL na Seção 11.2)
- [ ] Criar view `vw_editorial_dashboard` (SQL na Seção 11.2)
- [ ] Testar migrations com `asyncpg`

**Fase 3 — Grafo LangGraph:**
- [ ] Implementar `_step_collect_data` com coleta paralela (GA4 + WP + Redis)
- [ ] Implementar `_step_analyze_coverage` com 16 macrocategorias
- [ ] Implementar `_step_analyze_engagement` com scores compostos
- [ ] Implementar `_step_compare_competitors` lendo Redis do Monitor
- [ ] Implementar `_step_identify_gaps` com LLM PADRÃO
- [ ] Implementar `_step_adjust_priorities` publicando no Redis + Kafka
- [ ] Implementar `_step_generate_report` salvando no PostgreSQL

**Fase 4 — Integrações Externas:**
- [ ] Configurar GA4 Service Account (credenciais em `GA4_CREDENTIALS_PATH`)
- [ ] Testar GA4 API com `property_id` real
- [ ] Testar WordPress REST API (autenticação Application Password)
- [ ] Testar Kafka producer no tópico `pautas-gap`
- [ ] Validar leitura de Redis keys do Monitor Concorrência

**Fase 5 — Memória:**
- [ ] Working memory: pesos e relatório no Redis com TTL correto
- [ ] Episodic memory: resultados de ciclo no PostgreSQL `memoria_agentes`
- [ ] Semantic memory: padrões de engajamento com pgvector

**Fase 6 — Testes:**
- [ ] Rodar `pytest tests/test_editor_chefe.py -v`
- [ ] Todos os 8 testes de `TestArquiteturaInviolavel` passando
- [ ] Todos os testes de `TestCicloCompleto` passando
- [ ] Cobertura mínima de 80% do código

**Fase 7 — Configuração:**
- [ ] Criar `brasileira/config/editorial_config.yaml` com metas e pesos
- [ ] Configurar variáveis de ambiente:
  - `GA4_PROPERTY_ID=` (ID da propriedade GA4)
  - `GA4_CREDENTIALS_PATH=` (path do JSON de credenciais)
  - `EDITOR_CHEFE_CICLO_SEGUNDOS=3600` (1 hora)
- [ ] Criar `config/prompts/editor_chefe.txt` com `SYSTEM_PROMPT`

**Fase 8 — Deploy:**
- [ ] Criar Dockerfile ou entrada no docker-compose.yml
- [ ] Configurar restart policy (`unless-stopped`)
- [ ] Adicionar ao supervisor ou systemd como serviço de longa duração
- [ ] Configurar logging com formato estruturado (JSON)
- [ ] Verificar no Redis após primeiro ciclo: `redis-cli hgetall editorial:pesos`

### 15.3 Variáveis de Ambiente Necessárias

```bash
# Google Analytics 4
GA4_PROPERTY_ID=123456789          # ID numérico da propriedade GA4
GA4_CREDENTIALS_PATH=/app/secrets/ga4-service-account.json

# WordPress (já existentes no sistema)
WP_URL=https://brasileira.news
WP_USER=iapublicador
WP_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# Redis (já existente)
REDIS_URL=redis://localhost:6379/0

# PostgreSQL (já existente)
DATABASE_URL=postgresql://user:pass@localhost/brasileira

# Kafka (já existente)
KAFKA_BROKERS=localhost:9092

# LLM (SmartLLMRouter — já existente no sistema)
# Herda do SmartLLMRouter: ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.

# Configuração do ciclo
EDITOR_CHEFE_CICLO_SEGUNDOS=3600   # 1 hora (default)
```

### 15.4 Verificação Pós-Deploy

Após o primeiro ciclo de 1 hora, verifique:

```bash
# 1. Pesos editoriais publicados no Redis
redis-cli hgetall editorial:pesos
# Esperado: hash com 16 categorias e pesos entre 0.5 e 2.0

# 2. Relatório do último ciclo
redis-cli get editorial:relatorio:ultimo | python3 -m json.tool | head -50

# 3. Relatório no PostgreSQL
psql -c "SELECT cycle_id, gerado_em, artigos_hora, n_categorias_criticas FROM vw_editorial_dashboard LIMIT 5;"

# 4. Gaps publicados no Kafka
kafka-console-consumer --topic pautas-gap --from-beginning --max-messages 10

# 5. Logs do agente
journalctl -u editor-chefe -n 100 --no-pager
# Esperado: "Ciclo editorial-YYYYMMDD-HH:MM concluído: XX artigos/h"
```

---

## RESUMO EXECUTIVO

### O Que o Editor-Chefe V3 FAZ

| Função | Descrição |
|--------|-----------|
| Observa | Analisa artigos já publicados (não aprova antes) |
| Mede | Pageviews, tempo de leitura, CTR por categoria |
| Compara | Cobertura própria vs concorrentes |
| Identifica | Editorias sub-representadas (0 artigos = crítico) |
| Ajusta | Pesos de prioridade 0.5-2.0 no Redis (sugestões) |
| Sinaliza | Gaps urgentes no Kafka `pautas-gap` |
| Reporta | Relatório editorial JSON/HTML a cada ciclo |
| Aprende | Padrões de engajamento na memória semântica |

### O Que o Editor-Chefe V3 NÃO FAZ

| Proibição | Motivo |
|-----------|--------|
| NÃO aprova artigos | Viola regra #1: publicar primeiro |
| NÃO rejeita artigos | Nunca existe QualityDecision.KILL |
| NÃO bloqueia o pipeline | É observador, não gatekeeper |
| NÃO usa LLM PREMIUM | analise_metricas = tier PADRÃO |
| NÃO cria artigos | Não é Reporter |
| NÃO monitora saúde do sistema | Isso é do Monitor Sistema |
| NÃO coleta de fontes | Isso é do Worker Pool |

### Diferença Fundamental V2 → V3

```
V2 (ERRADO):
Pauteiro → [Editor-Chefe: GATE] → Reporter → Publisher
                    ↑
            Bloqueia TUDO aqui
            0 artigos publicados

V3 (CORRETO):
Fontes → Reporter → [PUBLICA] → [Editor-Chefe: OBSERVA 1h depois]
                                        ↓
                                   Ajusta pesos
                                   Sinaliza gaps
                                   Gera relatório
```

### Custo Estimado por Ciclo

| Item | Tokens | Custo Estimado (USD) |
|------|--------|---------------------|
| Gap analysis (LLM PADRÃO) | ~3.000 input + ~1.500 output | ~$0.003 |
| Total por ciclo (1h) | — | ~$0.003 |
| Total por dia (24 ciclos) | — | ~$0.07 |
| Total por mês | — | ~$2.10 |

Custo marginal do Editor-Chefe V3: menos de **R$12/mês**.

---

*Briefing gerado em 26 de março de 2026. Baseado em: auditoria do `editor_chefe-10.py` (879 linhas), `contexto-subagentes.md`, `briefing-implementacao-brasileira-news-v3.pplx.md` (Parte IV, seção 4.7), pesquisa sobre editorial analytics 2025-2026 ([American Press Institute](https://americanpressinstitute.org/our-offerings/metrics-for-news/), [Smartocto](https://smartocto.com/blog/editorial-analytics-2025-know/)), Google Analytics 4 Data API ([Google Developers](https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart)), e integração WordPress REST API ([WP Statistics](https://wp-statistics.com/add-ons/wp-statistics-rest-api/)). Componente #10 do sistema brasileira.news V3.*
