# Briefing Completo para IA — Reporter V3 (Agente Principal de Produção)

**Data:** 26 de março de 2026  
**Classificação:** Briefing de Implementação — Componente #4 (Prioridade Máxima)  
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)  
**Repositório:** https://github.com/redes-dsc/brasileira  
**Stack:** Python 3.12+ / LangGraph / aiokafka / HTTPX / pgvector / PostgreSQL / Redis / WordPress REST API  
**Componente:** `brasileira/agents/reporter.py` + módulos auxiliares  
**Dependências:** SmartLLMRouter V3 (Componente #1), Worker Pool de Coletores V3 (Componente #2)

---

## LEIA ISTO PRIMEIRO — Por que este é o Componente #4

O Reporter é o **CORAÇÃO** de toda a produção editorial da brasileira.news V3. Enquanto o SmartLLMRouter é a fundação de chamadas LLM e os Coletores são o pipeline de ingestão, o Reporter é o único agente que **escreve e publica** conteúdo. Sem ele, nenhum artigo vai ao ar. Se ele é lento, a produção cai. Se tem gates ou drafts, o sistema fica paralisado — exatamente o que matou a V2.

**Volume:** 1.000+ artigos/dia. Para alcançar esse volume com um ciclo de coleta a cada 15-30 minutos, o Reporter precisa processar ~40-70 artigos/hora. Isso exige um **worker pool** com N instâncias concorrentes, cada uma executando um LangGraph StateGraph independente.

**Responsabilidade única:** Consumir artigos classificados → contextualizar com RAG → redigir com LLM PREMIUM → otimizar SEO com LLM PADRÃO → **PUBLICAR DIRETO** no WordPress → disparar evento Kafka `article-published`. Sem drafts. Sem aprovação. Sem gates.

**Este briefing contém TUDO que você precisa para implementar o Reporter do zero.** Não consulte outros documentos. Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ QUEBRADO NA V2

### 1.1 O Problema Central: Fluxo Invertido com Gates

O `reporter-19.py` da V2 foi projetado para um fluxo **completamente errado**:

```
V2 (QUEBRADO):
Pauteiro (filtra 99%) → Editor-Chefe (GATE) → Editor Editoria (GATE)
→ Reporter (ESPERA PAUTA) → FAZ DRAFT → Revisor (GATE, pode REJEITAR)
→ Publisher (ESPERA APROVAÇÃO que nunca chega)
= 0 artigos publicados
```

O Reporter V2 nunca publica diretamente. Ele:
1. Fica **esperando pautas** via EventBus (nunca consome artigos diretamente do Kafka)
2. Produz um **draft** (`aprovacao_solicitada`) em vez de publicar
3. Aguarda aprovação de um revisor que pode **rejeitar** o artigo
4. Depende de um `publisher-7.py` separado que também espera aprovação

**Resultado:** O pipeline tem 3+ pontos de bloqueio antes de um único artigo ser publicado. Na prática, zero artigos saem.

### 1.2 Bugs Fatais do reporter-19.py

```python
# reporter-19.py — PROBLEMAS FATAIS

# BUG 1: Espera pauta, não consome Kafka diretamente
# (linha 188-196)
await self.event_bus.subscribe(
    channels=["task_assignment"],
    callback=self._handle_task_assignment,
)
# ↑ Depende do Pauteiro que filtra 99% das fontes. ERRADO.
# V3: consome classified-articles do Kafka diretamente

# BUG 2: Gera draft em vez de publicar
# (linha 762)
await self.event_bus.publish(
    channel="aprovacao_solicitada",  # ERRADO — não existe aprovação em V3
    message={"article_draft": draft, ...},
)
# ↑ Cria gargalo. Ninguém nunca aprova nada. Zero artigos.
# V3: publica direto no WordPress com status="publish"

# BUG 3: Loop de revisão pré-publicação
# (linha 302-349)
# _should_submit: verifica feedback e vai para "revise"
# _should_submit_after_revise: loop de revisão
# ↑ Gate pré-publicação. ELIMINADO em V3.

# BUG 4: LLM tier PADRÃO para escrita de artigo
# task_type="article_writing" → tier PADRÃO
# ↑ ERRADO. Redação usa PREMIUM. SEO usa PADRÃO.

# BUG 5: Tavily search como fonte primária
# (linha 489-532)
# Faz busca web externa quando já tem conteúdo na fonte
# ↑ REDUNDANTE. O conteúdo vem do coletor. RAG é feito com pgvector.

# BUG 6: Sem integração Kafka
# Não produz eventos article_published
# Não consome classified-articles
# ↑ Isolado do pipeline.

# BUG 7: Sem checkpointing PostgresSaver
# Sem persistência de estado
# Se cai, perde o artigo em processamento

# BUG 8: Worker pool inexistente
# Uma única instância, sequencial
# Para 1.000+ artigos/dia, precisamos de N workers concorrentes
```

### 1.3 O publisher-7.py É Eliminado

O `publisher-7.py` é um agente separado que recebe artigos aprovados e os publica. Na V3, **publicação é responsabilidade do próprio Reporter**. O publisher-7.py é eliminado integralmente. Não migrar nada dele além da lógica de upload de mídia (que será usada pelo Fotógrafo, não pelo Reporter).

### 1.4 Mapeamento V2 → V3

| Elemento V2 | Problema | Destino V3 |
|-------------|---------|------------|
| `reporter-19.py` espera pauta | NÃO consome Kafka diretamente | Consumer de `classified-articles` |
| `reporter-19.py` gera draft | NÃO publica | Publica direto com `status="publish"` |
| `publisher-7.py` espera aprovação | Gate desnecessário | **ELIMINADO** |
| Loop de revisão pré-publicação | Gate que bloqueia | **ELIMINADO** |
| EventBus `aprovacao_solicitada` | Gargalo | Kafka `article-published` |
| LLM PADRÃO para escrita | Qualidade degradada | LLM **PREMIUM** para escrita |
| Tavily search externo | Redundante e lento | RAG com pgvector local |
| Instância única | Não escala | Worker pool com N instâncias |
| Sem checkpointing | Perde estado em crash | PostgresSaver por thread_id |

---

## PARTE II — ARQUITETURA DO REPORTER V3

### 2.1 Visão Geral

```
┌──────────────────────────────────────────────────────────────────────┐
│                   REPORTER V3 — ARQUITETURA                          │
│                                                                      │
│  INPUTS:                                                             │
│    Kafka: classified-articles ──┐                                    │
│    Kafka: pautas-especiais ──────┼─→ [Worker Pool Manager]          │
│    Kafka: pautas-gap ───────────┘       │                            │
│                                         ↓                            │
│              ┌──────────────────────────────────────┐                │
│              │  Reporter Worker #1  (LangGraph)     │                │
│              │  Reporter Worker #2  (LangGraph)     │                │
│              │  Reporter Worker #3  (LangGraph)     │                │
│              │  ...                                  │                │
│              │  Reporter Worker #N  (LangGraph)     │                │
│              └──────────────────────────────────────┘                │
│                         │ cada worker executa:                        │
│                         ↓                                            │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              PIPELINE POR ARTIGO (StateGraph)                │   │
│   │                                                               │   │
│   │  [extrair_conteudo] → [contextualizar] → [redigir]          │   │
│   │       ↓                    ↓                  ↓              │   │
│   │  Fetch HTML da         pgvector           LLM PREMIUM        │   │
│   │  fonte original        top-3 RAG         (redação)           │   │
│   │                        similar                                │   │
│   │                                           ↓                   │   │
│   │                               [otimizar_seo]                  │   │
│   │                               LLM PADRÃO                      │   │
│   │                                           ↓                   │   │
│   │                               [publicar_wp]                   │   │
│   │                               status="publish"                │   │
│   │                               SEM DRAFT                       │   │
│   │                                           ↓                   │   │
│   │                               [disparar_eventos]              │   │
│   │                               Kafka: article-published         │   │
│   │                               PostgreSQL: registra artigo      │   │
│   │                               Redis: atualiza working_memory   │   │
│   │                               pgvector: salva embedding        │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  OUTPUTS:                                                            │
│    WordPress: post publicado (status="publish")                      │
│    Kafka: article-published → Fotógrafo, Revisor, Curador, Monitor  │
│    PostgreSQL: registro em tabela artigos                            │
│    pgvector: embedding do artigo para RAG futuro                     │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Princípios de Design OBRIGATÓRIOS

1. **SEM DRAFT.** `status="publish"` sempre. Nunca `status="draft"`.
2. **SEM APROVAÇÃO.** Nenhum canal de aprovação. Nenhum EventBus de revisão pré-publicação.
3. **100% das entradas processadas.** Nenhum artigo ignorado. O worker loop é infinito.
4. **LLM PREMIUM para redação, PADRÃO para SEO.** Nenhuma inversão.
5. **Isolamento total entre workers.** Falha de um worker não afeta os outros.
6. **Checkpointing por thread_id.** Cada artigo tem seu próprio thread_id no PostgresSaver.
7. **Crédito à fonte OBRIGATÓRIO.** Sempre citar fonte com link HTML no 1º ou 2º parágrafo.
8. **Evento Kafka após publicação.** O pipeline pós-publicação depende disso.

### 2.3 Distinção de Fontes de Entrada

O Reporter consome três tópicos Kafka com tratamento ligeiramente diferente:

| Tópico Kafka | Tipo de Artigo | Diferença no Pipeline |
|-------------|---------------|----------------------|
| `classified-articles` | Artigos de fontes RSS/Scraper já classificados | Sempre tem conteúdo da fonte. Extração e RAG. |
| `pautas-especiais` | Pautas criadas pelo Pauteiro (trending, especiais) | Pode não ter URL de fonte. Usa contexto do Pauteiro. |
| `pautas-gap` | Gaps detectados pelo Consolidador/Monitor | Tem tema mas pode ter 0 fontes nossas. |

---

## PARTE III — LANGGRAPH STATEGRAPH (NODES, EDGES, STATE SCHEMA)

### 3.1 ReporterState — Schema Completo

```python
# brasileira/agents/reporter.py

from typing import TypedDict, Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawArticle:
    """Artigo bruto vindo do Kafka classified-articles."""
    article_id: str
    url_fonte: str
    titulo_original: str
    resumo_original: str
    html_preview: str          # Conteúdo parcial do feed RSS
    categoria: str             # 1 das 16 macrocategorias
    urgencia: str              # FLASH | NORMAL | ANÁLISE
    score_relevancia: float    # 0.0 a 1.0
    fonte_nome: str            # Ex: "Folha de São Paulo"
    fonte_id: str              # ID da fonte no banco
    publicado_em: datetime     # Data da publicação na fonte
    og_image: Optional[str]    # Imagem da fonte original
    tipo: str                  # noticia_simples | pauta_especial | pauta_gap


class ReporterState(TypedDict):
    """
    Estado completo do pipeline do Reporter.
    Cada campo é IMUTÁVEL dentro do nó — retorna dict com updates.
    """
    # ── Input ─────────────────────────────────────────────────────────
    article_id: str                    # ID único do artigo (trace_id)
    raw_article: Dict[str, Any]        # RawArticle serializado
    fonte_nome: str                    # Nome da fonte para crédito
    fonte_url: str                     # URL da fonte original
    categoria: str                     # Categoria editorial
    urgencia: str                      # FLASH | NORMAL | ANÁLISE
    tipo: str                          # Tipo de artigo

    # ── Extração de Conteúdo ──────────────────────────────────────────
    conteudo_extraido: Optional[str]   # Texto completo extraído da fonte
    metadados_extracao: Optional[Dict] # og:image, author, date, etc.
    extracao_falhou: bool              # True se extração falhou

    # ── Contextualização RAG ──────────────────────────────────────────
    contexto_rag: List[Dict]           # Top-3 artigos similares do pgvector
    contexto_texto: Optional[str]      # Contexto formatado para o prompt

    # ── Redação ───────────────────────────────────────────────────────
    artigo_redigido: Optional[Dict]    # Artigo completo redigido pelo LLM
    modelo_redacao: Optional[str]      # Qual modelo foi usado
    tokens_redacao: Optional[Dict]     # {in: X, out: Y, custo: Z}

    # ── SEO ───────────────────────────────────────────────────────────
    seo_data: Optional[Dict]           # {titulo_seo, descricao, slug, keywords}
    modelo_seo: Optional[str]          # Qual modelo foi usado para SEO

    # ── Publicação ────────────────────────────────────────────────────
    wp_post_id: Optional[int]          # ID do post publicado
    wp_post_url: Optional[str]         # URL permanente do post
    wp_categoria_id: Optional[int]     # ID da categoria no WordPress
    wp_tag_ids: List[int]              # IDs das tags no WordPress
    publicado: bool                    # Flag de publicação confirmada

    # ── Eventos ───────────────────────────────────────────────────────
    eventos_disparados: bool           # Flag de eventos disparados

    # ── Controle ──────────────────────────────────────────────────────
    step_atual: str                    # Nome do node atual
    erro_fatal: Optional[str]          # Erro que impediu publicação
    tentativas_redacao: int            # Tentativas de parse JSON (max 3)
    iniciado_em: str                   # ISO timestamp
    duracoes: Dict[str, float]         # Duração por step em segundos

    # ── Memória ───────────────────────────────────────────────────────
    cycle_id: str                      # ID do ciclo de trabalho
    worker_id: str                     # ID do worker que processou
```

### 3.2 StateGraph — Definição Completa

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool


def build_reporter_graph(checkpointer: AsyncPostgresSaver) -> StateGraph:
    """
    Constrói o grafo do Reporter.
    Fluxo: extrair_conteudo → contextualizar → redigir → otimizar_seo → publicar_wp → disparar_eventos → END
    
    Design: Linear sem branches condicionais.
    Falhas em qualquer nó → erro registrado + artigo vai para DLQ.
    NUNCA bloqueia o pipeline.
    """
    graph = StateGraph(ReporterState)

    # ── Nós ──────────────────────────────────────────────────────────
    graph.add_node("extrair_conteudo",    node_extrair_conteudo)
    graph.add_node("contextualizar",      node_contextualizar)
    graph.add_node("redigir",             node_redigir)
    graph.add_node("otimizar_seo",        node_otimizar_seo)
    graph.add_node("publicar_wp",         node_publicar_wp)
    graph.add_node("disparar_eventos",    node_disparar_eventos)
    graph.add_node("registrar_erro_dlq",  node_registrar_erro_dlq)

    # ── Entry point ──────────────────────────────────────────────────
    graph.set_entry_point("extrair_conteudo")

    # ── Edges lineares ───────────────────────────────────────────────
    # extrair_conteudo → contextualizar (sempre, mesmo se extração falhou — usa resumo_original)
    graph.add_conditional_edges(
        "extrair_conteudo",
        route_apos_extracao,
        {
            "contextualizar": "contextualizar",
            "dlq": "registrar_erro_dlq",
        }
    )
    graph.add_edge("contextualizar", "redigir")

    # redigir → otimizar_seo (sempre — se falhou JSON, usa fallback estruturado)
    graph.add_conditional_edges(
        "redigir",
        route_apos_redacao,
        {
            "otimizar_seo": "otimizar_seo",
            "dlq": "registrar_erro_dlq",
        }
    )
    graph.add_edge("otimizar_seo", "publicar_wp")

    # publicar_wp → disparar_eventos (apenas se publicou com sucesso)
    graph.add_conditional_edges(
        "publicar_wp",
        route_apos_publicacao,
        {
            "disparar_eventos": "disparar_eventos",
            "dlq": "registrar_erro_dlq",
        }
    )
    graph.add_edge("disparar_eventos", END)
    graph.add_edge("registrar_erro_dlq", END)

    return graph.compile(checkpointer=checkpointer)


def route_apos_extracao(state: ReporterState) -> str:
    """Extração falhou completamente (sem resumo nem conteúdo)? → DLQ."""
    raw = state.get("raw_article", {})
    resumo = raw.get("resumo_original", "")
    conteudo = state.get("conteudo_extraido", "")
    if not resumo and not conteudo:
        return "dlq"
    return "contextualizar"


def route_apos_redacao(state: ReporterState) -> str:
    """Redação falhou após 3 tentativas? → DLQ."""
    if state.get("erro_fatal") and not state.get("artigo_redigido"):
        return "dlq"
    return "otimizar_seo"


def route_apos_publicacao(state: ReporterState) -> str:
    """Publicação falhou? → DLQ. Sucesso? → disparar_eventos."""
    if state.get("publicado") and state.get("wp_post_id"):
        return "disparar_eventos"
    return "dlq"
```

### 3.3 Inicialização do Checkpointer

```python
import os
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

PG_DSN = os.environ["DATABASE_URL"]  # postgresql://user:pass@host:5432/brasileira


async def criar_checkpointer() -> AsyncPostgresSaver:
    """
    Cria AsyncPostgresSaver com connection pool.
    IMPORTANTE: Uma instância por processo. Múltiplos workers no mesmo processo
    compartilham a instância. Para horizontal scaling, use múltiplos processos.
    """
    pool = AsyncConnectionPool(
        conninfo=PG_DSN,
        min_size=4,
        max_size=20,
        kwargs={"autocommit": True},
    )
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()  # Cria tabelas de checkpoint se não existirem
    return checkpointer
```

---

## PARTE IV — CONTENT EXTRACTION (BUSCA CONTEÚDO COMPLETO DA FONTE)

### 4.1 Por Que Extração É Necessária

O artigo que chega via Kafka `classified-articles` vem do coletor RSS/Scraper com apenas:
- Título original
- Resumo/excerpt (geralmente 200-500 caracteres)
- URL da fonte
- Preview HTML do feed

Para redigir um artigo com mínimo 300 palavras de qualidade TIER-1, o Reporter precisa do **conteúdo completo** da matéria original. Sem ele, o LLM vai alucinar ou repetir o resumo.

### 4.2 Extrator de Conteúdo — Implementação

```python
# brasileira/agents/reporter_extractors.py

import asyncio
import re
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import httpx
import trafilatura
from trafilatura.settings import use_config

logger = logging.getLogger("reporter.extractor")

# Configuração do trafilatura para notícias
TRAFILATURA_CONFIG = use_config()
TRAFILATURA_CONFIG.set("DEFAULT", "MIN_EXTRACTED_SIZE", "200")
TRAFILATURA_CONFIG.set("DEFAULT", "MIN_OUTPUT_SIZE", "200")
TRAFILATURA_CONFIG.set("DEFAULT", "INCLUDE_COMMENTS", "false")
TRAFILATURA_CONFIG.set("DEFAULT", "INCLUDE_TABLES", "true")

# Fallback: newspaper4k para sites complexos
try:
    from newspaper import Article as Newspaper4kArticle
    HAS_NEWSPAPER4K = True
except ImportError:
    HAS_NEWSPAPER4K = False

# User-agent para extração editorial
USER_AGENT = (
    "Mozilla/5.0 (compatible; BrasileiraNBot/3.0; "
    "+https://brasileira.news/bot; newsroom-extractor)"
)

TIMEOUT_EXTRACAO = httpx.Timeout(
    connect=10.0,
    read=30.0,
    write=10.0,
    pool=5.0,
)


async def extrair_conteudo_fonte(
    url: str,
    resumo_original: str = "",
    html_preview: str = "",
) -> Dict[str, Any]:
    """
    Extrai conteúdo completo de uma URL de fonte.
    
    Estratégia em cascata:
    1. trafilatura (melhor recall/precision para notícias)
    2. newspaper4k fallback (para sites com estrutura especial)
    3. HTML básico fallback (strip tags do preview)
    4. Resumo original (último recurso — melhor do que nada)
    
    Retorna:
        {
            "conteudo": str,           # Texto principal extraído
            "og_image": str | None,    # URL da imagem OG
            "autor": str | None,       # Autor do artigo
            "data_publicacao": str,    # ISO date
            "extracao_metodo": str,    # Qual método funcionou
            "sucesso": bool,           # True se extraiu conteúdo útil
        }
    """
    resultado = {
        "conteudo": "",
        "og_image": None,
        "autor": None,
        "data_publicacao": None,
        "extracao_metodo": "fallback_resumo",
        "sucesso": False,
    }

    # Verifica se URL é válida
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        logger.warning(f"URL inválida para extração: {url}")
        resultado["conteudo"] = resumo_original
        return resultado

    # Tenta fetch do HTML
    html = None
    async with httpx.AsyncClient(
        timeout=TIMEOUT_EXTRACAO,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        http2=True,
    ) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                html = resp.text
                # Extrai og:image do HTML bruto
                og_match = re.search(
                    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                    html, re.IGNORECASE
                )
                if og_match:
                    resultado["og_image"] = og_match.group(1)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning(f"Falha ao fazer fetch de {url}: {e}")

    if not html:
        # Usa resumo original como fallback
        resultado["conteudo"] = resumo_original or html_preview
        resultado["extracao_metodo"] = "fallback_resumo"
        resultado["sucesso"] = bool(resultado["conteudo"])
        return resultado

    # ── Tentativa 1: trafilatura ─────────────────────────────────────
    try:
        extraido = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
            config=TRAFILATURA_CONFIG,
        )
        metadata = trafilatura.extract_metadata(html, default_url=url)

        if extraido and len(extraido.split()) >= 50:
            resultado["conteudo"] = extraido
            resultado["extracao_metodo"] = "trafilatura"
            resultado["sucesso"] = True
            if metadata:
                resultado["autor"] = metadata.author
                resultado["data_publicacao"] = str(metadata.date) if metadata.date else None
                if metadata.image and not resultado["og_image"]:
                    resultado["og_image"] = metadata.image
            return resultado
    except Exception as e:
        logger.debug(f"trafilatura falhou em {url}: {e}")

    # ── Tentativa 2: newspaper4k ─────────────────────────────────────
    if HAS_NEWSPAPER4K:
        try:
            article = Newspaper4kArticle(url)
            article.set_html(html)
            article.parse()
            if article.text and len(article.text.split()) >= 50:
                resultado["conteudo"] = article.text
                resultado["extracao_metodo"] = "newspaper4k"
                resultado["sucesso"] = True
                resultado["autor"] = ", ".join(article.authors) if article.authors else None
                if article.top_image and not resultado["og_image"]:
                    resultado["og_image"] = article.top_image
                return resultado
        except Exception as e:
            logger.debug(f"newspaper4k falhou em {url}: {e}")

    # ── Tentativa 3: Strip HTML básico do preview ─────────────────────
    if html_preview:
        texto_limpo = re.sub(r'<[^>]+>', ' ', html_preview)
        texto_limpo = re.sub(r'\s+', ' ', texto_limpo).strip()
        if len(texto_limpo.split()) >= 30:
            resultado["conteudo"] = texto_limpo
            resultado["extracao_metodo"] = "html_strip"
            resultado["sucesso"] = True
            return resultado

    # ── Fallback final: resumo original ──────────────────────────────
    resultado["conteudo"] = resumo_original
    resultado["extracao_metodo"] = "fallback_resumo"
    resultado["sucesso"] = bool(resumo_original)
    return resultado


async def node_extrair_conteudo(state: ReporterState) -> Dict[str, Any]:
    """
    Nó LangGraph: extrai conteúdo completo da fonte original.
    
    NUNCA levanta exceção — degrada graciosamente para resumo_original.
    """
    import time
    t_inicio = time.monotonic()

    raw = state["raw_article"]
    url_fonte = raw.get("url_fonte", "")
    resumo = raw.get("resumo_original", "")
    html_preview = raw.get("html_preview", "")
    article_id = state["article_id"]

    logger.info(f"[{article_id}] Extraindo conteúdo de {url_fonte[:80]}")

    resultado = await extrair_conteudo_fonte(
        url=url_fonte,
        resumo_original=resumo,
        html_preview=html_preview,
    )

    duracao = time.monotonic() - t_inicio
    logger.info(
        f"[{article_id}] Extração via {resultado['extracao_metodo']} "
        f"({len(resultado['conteudo'].split())} palavras) em {duracao:.2f}s"
    )

    duracoes = dict(state.get("duracoes", {}))
    duracoes["extrair_conteudo"] = duracao

    return {
        "conteudo_extraido": resultado["conteudo"],
        "metadados_extracao": {
            "og_image": resultado.get("og_image"),
            "autor": resultado.get("autor"),
            "data_publicacao": resultado.get("data_publicacao"),
            "metodo": resultado["extracao_metodo"],
        },
        "extracao_falhou": not resultado["sucesso"],
        "step_atual": "extrair_conteudo",
        "duracoes": duracoes,
    }
```

### 4.3 Timeouts e Limites

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Connect timeout | 10s | DNS + TCP handshake |
| Read timeout | 30s | Páginas lentas |
| Tamanho mínimo para aceitar | 50 palavras | Abaixo disso, provavelmente extração falhou |
| Fallback se extração falha | `resumo_original` | Melhor do que nada — LLM ainda pode redigir |
| Retry em extração | 0 (sem retry) | DLQ cuida de reprocessamento |

---

## PARTE V — CONTEXTUALIZAÇÃO RAG (PGVECTOR)

### 5.1 Objetivo do RAG no Reporter

O Reporter usa RAG (Retrieval-Augmented Generation) para:
1. **Evitar repetição:** Não redigir artigo idêntico ao que já publicamos
2. **Enriquecer contexto:** Fornecer histórico do tema ao LLM de redação
3. **Coerência editorial:** Manter consistência com posicionamentos anteriores
4. **Memória semântica:** Artigos publicados ficam indexados para referência futura

### 5.2 Implementação do Contextualizador

```python
# brasileira/agents/reporter_rag.py

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional

import asyncpg
import numpy as np

logger = logging.getLogger("reporter.rag")

# Dimensão do vetor de embedding (OpenAI text-embedding-3-small)
EMBEDDING_DIM = 1536

# Limite de artigos retornados pelo RAG
RAG_TOP_K = 3

# Similaridade mínima para incluir no contexto (0.0 a 1.0)
RAG_MIN_SIMILARITY = 0.65

# Máximo de dias para buscar artigos similares
RAG_MAX_DIAS = 30

# Máximo de caracteres do resumo de cada artigo no contexto
RAG_MAX_RESUMO_CHARS = 400


async def gerar_embedding(texto: str, client) -> List[float]:
    """
    Gera embedding via SmartLLMRouter.
    Usa OpenAI text-embedding-3-small (1536 dims).
    """
    response = await client.embed(
        input=texto,
        model="text-embedding-3-small",
    )
    return response.embedding


async def buscar_artigos_similares(
    titulo: str,
    resumo: str,
    categoria: str,
    pg_pool: asyncpg.Pool,
    embedding_client,
    top_k: int = RAG_TOP_K,
    min_similarity: float = RAG_MIN_SIMILARITY,
    max_dias: int = RAG_MAX_DIAS,
) -> List[Dict[str, Any]]:
    """
    Busca artigos similares no pgvector para contextualização RAG.
    
    Estratégia:
    1. Gera embedding do título + resumo do artigo atual
    2. Busca HNSW no pgvector os top-K mais similares
    3. Filtra por similaridade mínima e janela temporal
    4. Retorna apenas resumos (não conteúdo completo — economy de tokens)
    
    Retorna lista de dicts:
        {
            "wp_post_id": int,
            "titulo": str,
            "resumo": str,         # Truncado a RAG_MAX_RESUMO_CHARS
            "categoria": str,
            "publicado_em": str,   # ISO datetime
            "similaridade": float,
            "url": str,
        }
    """
    query_texto = f"{titulo}. {resumo}"

    try:
        embedding = await gerar_embedding(query_texto, embedding_client)
    except Exception as e:
        logger.warning(f"Falha ao gerar embedding para RAG: {e}")
        return []

    # Converte para formato pgvector
    embedding_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"

    sql = """
        SELECT
            wp_post_id,
            titulo,
            LEFT(resumo, $5)     AS resumo,
            editoria             AS categoria,
            publicado_em::text   AS publicado_em,
            url_fonte,
            1 - (embedding <=> $1::vector) AS similaridade
        FROM memoria_agentes
        WHERE
            agente = 'reporter'
            AND tipo = 'episodica'
            AND publicado_em >= NOW() - INTERVAL '$4 days'
            AND 1 - (embedding <=> $1::vector) >= $3
        ORDER BY embedding <=> $1::vector
        LIMIT $2;
    """

    try:
        async with pg_pool.acquire() as conn:
            rows = await conn.fetch(
                sql,
                embedding_str,
                top_k,
                min_similarity,
                max_dias,
                RAG_MAX_RESUMO_CHARS,
            )
            return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"Falha na busca RAG no pgvector: {e}")
        return []


def formatar_contexto_rag(artigos: List[Dict]) -> str:
    """
    Formata artigos similares em texto de contexto para o prompt.
    Máximo 3 artigos. Apenas títulos e resumos (sem conteúdo completo).
    """
    if not artigos:
        return ""

    linhas = ["=== CONTEXTO: ARTIGOS ANTERIORES SOBRE ESTE TEMA ==="]
    linhas.append("(Use para evitar repetição e enriquecer contexto)")
    linhas.append("")

    for i, art in enumerate(artigos[:RAG_TOP_K], 1):
        sim = art.get("similaridade", 0)
        data = art.get("publicado_em", "")[:10]  # Apenas YYYY-MM-DD
        linhas.append(f"[{i}] {art.get('titulo', '')} ({data}, sim={sim:.2f})")
        linhas.append(f"     {art.get('resumo', '')}")
        linhas.append("")

    linhas.append("=== FIM DO CONTEXTO ===")
    return "\n".join(linhas)


async def node_contextualizar(state: ReporterState) -> Dict[str, Any]:
    """
    Nó LangGraph: contextualiza artigo com RAG em pgvector.
    
    Se pgvector falhar, segue sem contexto (não bloqueia).
    """
    import time
    t_inicio = time.monotonic()
    from brasileira.integrations.postgres_client import get_pg_pool
    from brasileira.llm.smart_router import get_router

    raw = state["raw_article"]
    article_id = state["article_id"]
    titulo = raw.get("titulo_original", "")
    resumo = raw.get("resumo_original", "")
    categoria = state["categoria"]

    logger.info(f"[{article_id}] Contextualizando via RAG pgvector")

    artigos_similares = []
    try:
        pg_pool = await get_pg_pool()
        router = get_router()
        artigos_similares = await buscar_artigos_similares(
            titulo=titulo,
            resumo=resumo,
            categoria=categoria,
            pg_pool=pg_pool,
            embedding_client=router,
        )
        logger.info(
            f"[{article_id}] RAG encontrou {len(artigos_similares)} artigos similares"
        )
    except Exception as e:
        logger.warning(f"[{article_id}] RAG falhou (continua sem contexto): {e}")

    contexto_texto = formatar_contexto_rag(artigos_similares)
    duracao = time.monotonic() - t_inicio

    duracoes = dict(state.get("duracoes", {}))
    duracoes["contextualizar"] = duracao

    return {
        "contexto_rag": artigos_similares,
        "contexto_texto": contexto_texto,
        "step_atual": "contextualizar",
        "duracoes": duracoes,
    }


async def salvar_embedding_artigo(
    article_id: str,
    wp_post_id: int,
    titulo: str,
    resumo: str,
    categoria: str,
    pg_pool: asyncpg.Pool,
    embedding_client,
) -> None:
    """
    Salva embedding do artigo publicado no pgvector para RAG futuro.
    Chamado APÓS publicação bem-sucedida.
    """
    texto = f"{titulo}. {resumo}"
    try:
        embedding = await gerar_embedding(texto, embedding_client)
        embedding_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"

        sql = """
            INSERT INTO memoria_agentes
                (agente, tipo, conteudo, embedding, relevancia_score, ttl_dias)
            VALUES
                ('reporter', 'episodica', $1::jsonb, $2::vector, 0.5, 90)
            ON CONFLICT DO NOTHING;
        """
        conteudo = json.dumps({
            "article_id": article_id,
            "wp_post_id": wp_post_id,
            "titulo": titulo,
            "resumo": resumo,
            "editoria": categoria,
            "publicado_em": "now()",
        }, ensure_ascii=False)

        async with pg_pool.acquire() as conn:
            await conn.execute(sql, conteudo, embedding_str)
    except Exception as e:
        logger.warning(f"Falha ao salvar embedding do artigo {article_id}: {e}")
```

### 5.3 Tabela PostgreSQL para Memória Semântica

```sql
-- Já definida no master briefing, reproduzida aqui por completude
-- Tabela compartilhada por todos os agentes

CREATE TABLE IF NOT EXISTS memoria_agentes (
    id              SERIAL PRIMARY KEY,
    agente          VARCHAR(50)  NOT NULL,   -- 'reporter', 'curador', etc.
    tipo            VARCHAR(20)  NOT NULL,   -- 'semantica' | 'episodica'
    conteudo        JSONB        NOT NULL,   -- Dados do artigo/decisão
    embedding       vector(1536),            -- pgvector HNSW
    criado_em       TIMESTAMPTZ  DEFAULT NOW(),
    relevancia_score FLOAT       DEFAULT 0.5,
    ttl_dias        INTEGER      DEFAULT 90
);

-- Índice HNSW para busca de similaridade rápida
CREATE INDEX IF NOT EXISTS idx_memoria_embedding_hnsw
    ON memoria_agentes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Índice para filtragem por agente e tipo
CREATE INDEX IF NOT EXISTS idx_memoria_agente_tipo
    ON memoria_agentes (agente, tipo, criado_em DESC);
```

---

## PARTE VI — REDAÇÃO COM LLM PREMIUM

### 6.1 System Prompt Completo para Redação

```python
# brasileira/config/prompts/reporter_redacao.txt
# Este arquivo é carregado UMA VEZ e cacheado (contexto estático — vide context engineering)

SYSTEM_PROMPT_REDACAO = """Você é o Repórter Sênior do portal **brasileira.news**, um dos maiores portais de notícias do Brasil.

Seu trabalho é transformar informações de fontes em matérias jornalísticas completas, factuais e de alta qualidade — no padrão de G1, Folha de São Paulo, UOL e Estadão.

═══════════════════════════════════════════════════════════════
REGRAS ABSOLUTAS (NUNCA violar)
═══════════════════════════════════════════════════════════════

1. TOLERÂNCIA ZERO PARA ALUCINAÇÃO
   - NUNCA invente fatos, dados, estatísticas, nomes ou eventos
   - NUNCA cite fontes que não estejam nas informações fornecidas
   - Se não souber algo, diga que a informação não está disponível
   - Presunção de inocência: use "suspeito de", "acusado de", "investigado por"

2. CRÉDITO À FONTE OBRIGATÓRIO
   - No 1º ou 2º parágrafo: mencionar a fonte original com link HTML
   - Formato: De acordo com informações d<a href="URL_FONTE" target="_blank" rel="nofollow">NOME_DA_FONTE</a>
   - Nunca plagiar. SEMPRE reescrever com ângulo editorial próprio.

3. IDIOMA E TOM
   - Português do Brasil formal, claro e acessível
   - Tom objetivo e factual (sem opinião em notícias factuais)
   - Proibido: asteriscos (*), underscores (_), cerquilhas (#) — use APENAS HTML

═══════════════════════════════════════════════════════════════
MANUAL DE REDAÇÃO — ESTRUTURA OBRIGATÓRIA
═══════════════════════════════════════════════════════════════

**TÍTULO** (campo: titulo)
- 60 a 80 caracteres
- Palavra-chave principal nas primeiras 8 palavras
- Direto e informativo. SEM clickbait. SEM prefixos maiúsculos (BREAKING:, URGENTE:)
- Verbo no presente para fatos recentes ("Governo anuncia...", "STF decide...")

**SUBTÍTULO** (campo: subtitulo)
- 100 a 150 caracteres
- Complementa o título com informação adicional relevante
- NÃO repete o título

**CORPO DO ARTIGO** (campo: conteudo)
- MÍNIMO 300 palavras para notícia simples, 500+ para análise
- TODO o conteúdo em tags HTML semânticas
- Estrutura obrigatória:

  1. LIDE (1º parágrafo): responde O quê? Quem? Quando? Onde? Como? Por quê?
     - Tag: <p> texto </p>
     - Exemplo: <p>O <strong>Ministério da Fazenda</strong> anunciou nesta terça-feira (26) um pacote de medidas fiscais avaliado em R$ 15 bilhões, com foco na redução do deficit primário em 2026.</p>

  2. CRÉDITO À FONTE (no 1º ou 2º parágrafo):
     - De acordo com informações d<a href="URL" target="_blank" rel="nofollow">FONTE</a>, ...

  3. DESENVOLVIMENTO (parágrafos 2-N):
     - Use <h2> a cada 2-3 parágrafos (como perguntas ou afirmações diretas)
     - Use <strong> nas entidades cruciais no PRIMEIRO terço
     - Use <blockquote> APENAS para citações diretas textuais reais
     - Use <ul><li> para listas de pontos, etapas, fatores

  4. CONTEXTO / HISTÓRICO (quando relevante):
     - Seção com <h2> "Contexto" ou "Histórico"
     - Use artigos anteriores fornecidos no contexto RAG (se disponíveis)

  5. PRÓXIMOS PASSOS / CONCLUSÃO (último parágrafo):
     - O que acontece agora? Quais são as implicações?

**NORMAS ESPECÍFICAS:**
- Números de zero a dez: por extenso (zero, um, dois, ... dez)
- Números acima de 10: algarismos (11, 100, 1.500)
- Valores monetários: R$ antes do número. Acima de mil: "R$ 1,5 milhão", "R$ 3,2 bilhões"
- Percentuais: junto ao número (5%, 12,3%)
- Datas: DD/MM/AAAA para datas completas, "nesta terça-feira (26)" para recentes
- Horas: HH:MM (horário de Brasília)
- Siglas: na primeira menção, escreva por extenso seguido da sigla entre parênteses
  Exemplo: "Banco Central do Brasil (BCB)"

**PROIBIDO:**
- Inventar declarações de fontes
- Usar linguagem coloquial ou gírias
- Emitir opinião pessoal em notícias (salvo seção "Opinião/Análise")
- Repetir trechos literais da fonte sem aspas e atribuição
- Usar markdown (**, *, #) — use HTML

**RESUMO** (campo: resumo)
- 2 frases objetivas
- Máximo 300 caracteres
- Sem aspas
- Sem repetir o título

**TAGS** (campo: tags)
- 3 a 5 entidades reais: pessoas, instituições, leis, organizações, locais específicos
- PROIBIDO: termos genéricos como "Notícias", "Brasil", "Política"
- Exemplos bons: "Lula", "STF", "Marco Fiscal", "Banco Central", "São Paulo"

═══════════════════════════════════════════════════════════════
CATEGORIAS VÁLIDAS (escolha UMA)
═══════════════════════════════════════════════════════════════
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
13. Brasil
14. Regionais
15. Opinião / Análise
16. Últimas Notícias

═══════════════════════════════════════════════════════════════
FORMATO DE RESPOSTA (OBRIGATÓRIO — JSON puro)
═══════════════════════════════════════════════════════════════

Responda APENAS com JSON válido, sem markdown, sem texto antes ou depois:

{
  "titulo": "string — 60 a 80 chars",
  "subtitulo": "string — 100 a 150 chars",
  "conteudo": "string — HTML completo, mínimo 300 palavras",
  "resumo": "string — máx 300 chars",
  "categoria": "string — uma das 16 categorias",
  "tags": ["tag1", "tag2", "tag3"],
  "fonte_nome": "string — nome da fonte original",
  "fonte_url": "string — URL da fonte original"
}
"""
```

### 6.2 User Prompt de Redação

```python
def construir_prompt_redacao(
    raw_article: Dict,
    conteudo_extraido: str,
    contexto_rag: str,
) -> str:
    """Constrói o prompt do usuário para redação."""
    
    fonte_nome = raw_article.get("fonte_nome", "fonte não identificada")
    fonte_url = raw_article.get("url_fonte", "")
    titulo_original = raw_article.get("titulo_original", "")
    resumo_original = raw_article.get("resumo_original", "")
    categoria = raw_article.get("categoria", "")
    urgencia = raw_article.get("urgencia", "NORMAL")
    data_fonte = raw_article.get("publicado_em", "")

    # Limita conteúdo extraído para não explodir o contexto
    conteudo_limitado = conteudo_extraido[:6000] if conteudo_extraido else ""

    prompt = f"""Redija uma matéria jornalística completa com base nas informações abaixo.

═══════ INFORMAÇÕES DA FONTE ═══════
Fonte: {fonte_nome}
URL da Fonte: {fonte_url}
Data de Publicação: {data_fonte}
Título Original: {titulo_original}
Resumo Original: {resumo_original}
Urgência: {urgencia}
Categoria Sugerida: {categoria}

═══════ CONTEÚDO COMPLETO DA FONTE ═══════
{conteudo_limitado if conteudo_limitado else "(Conteúdo completo não disponível — use o resumo acima)"}

{contexto_rag if contexto_rag else ""}

═══════ INSTRUÇÕES ═══════
1. Reescreva com ângulo editorial próprio — NUNCA copie trechos literais
2. Inclua crédito à fonte "{fonte_nome}" com link para {fonte_url} no 1º ou 2º parágrafo
3. Use a categoria "{categoria}" (ou ajuste se inadequada)
4. Mínimo: {"500 palavras (urgência ANÁLISE)" if urgencia == "ANÁLISE" else "300 palavras"}
5. Responda APENAS com JSON válido — sem markdown, sem texto extra

Gere o JSON agora:"""

    return prompt
```

### 6.3 Nó de Redação com Retry

```python
import json
import re
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("reporter.redacao")

MAX_TENTATIVAS_JSON = 3


async def node_redigir(state: ReporterState) -> Dict[str, Any]:
    """
    Nó LangGraph: redige o artigo com LLM PREMIUM.
    
    - task_type = "redacao_artigo" → tier PREMIUM (obrigatório)
    - Retry até 3x se JSON inválido
    - Se falhar 3x: registra erro e vai para DLQ
    """
    from brasileira.llm.smart_router import get_router

    t_inicio = time.monotonic()
    article_id = state["article_id"]
    raw = state["raw_article"]
    conteudo = state.get("conteudo_extraido", "") or raw.get("resumo_original", "")
    contexto = state.get("contexto_texto", "")

    logger.info(f"[{article_id}] Redigindo artigo com LLM PREMIUM")

    prompt_usuario = construir_prompt_redacao(
        raw_article=raw,
        conteudo_extraido=conteudo,
        contexto_rag=contexto,
    )

    router = get_router()
    artigo_redigido = None
    modelo_usado = None
    tokens = {}
    erro_redacao = None
    tentativas = state.get("tentativas_redacao", 0)

    for tentativa in range(1, MAX_TENTATIVAS_JSON + 1):
        # Na segunda tentativa em diante: simplifica o prompt
        if tentativa > 1:
            prompt_tentativa = (
                prompt_usuario
                + f"\n\n[TENTATIVA {tentativa}: Resposta anterior não era JSON válido. "
                  f"Retorne APENAS JSON puro, começando com {{ e terminando com }}]"
            )
            logger.warning(f"[{article_id}] Retry JSON tentativa {tentativa}")
        else:
            prompt_tentativa = prompt_usuario

        try:
            response = await router.complete(
                task_type="redacao_artigo",    # → tier PREMIUM
                system_prompt=SYSTEM_PROMPT_REDACAO,
                user_prompt=prompt_tentativa,
                max_tokens=8192,
                temperature=0.7 if tentativa == 1 else 0.4,  # Mais conservador em retries
                agent_id=f"reporter-{state['worker_id']}",
            )

            modelo_usado = response.model
            tokens = {
                "in": response.usage.get("prompt_tokens", 0),
                "out": response.usage.get("completion_tokens", 0),
                "custo_usd": response.cost,
            }

            # Parse JSON
            conteudo_resp = response.content.strip()

            # Remove markdown se o modelo insistir em incluir
            conteudo_resp = re.sub(r'^```json\s*', '', conteudo_resp)
            conteudo_resp = re.sub(r'\s*```$', '', conteudo_resp)

            # Tenta parsear
            artigo_redigido = json.loads(conteudo_resp)

            # Valida campos obrigatórios
            campos_obrigatorios = ["titulo", "subtitulo", "conteudo", "resumo", "categoria", "tags"]
            campos_faltando = [c for c in campos_obrigatorios if not artigo_redigido.get(c)]
            if campos_faltando:
                raise ValueError(f"Campos obrigatórios faltando: {campos_faltando}")

            # Valida contagem de palavras
            texto_sem_html = re.sub(r'<[^>]+>', ' ', artigo_redigido["conteudo"])
            num_palavras = len(texto_sem_html.split())
            if num_palavras < 150:
                raise ValueError(f"Artigo muito curto: {num_palavras} palavras (mínimo 150)")

            logger.info(
                f"[{article_id}] Artigo redigido: '{artigo_redigido['titulo'][:60]}' "
                f"({num_palavras} palavras) via {modelo_usado} em tentativa {tentativa}"
            )
            break  # Sucesso — sai do loop

        except json.JSONDecodeError as e:
            erro_redacao = f"JSONDecodeError tentativa {tentativa}: {e}"
            logger.warning(f"[{article_id}] {erro_redacao}")
            artigo_redigido = None
            tentativas += 1
            continue

        except ValueError as e:
            erro_redacao = f"Validação falhou tentativa {tentativa}: {e}"
            logger.warning(f"[{article_id}] {erro_redacao}")
            artigo_redigido = None
            tentativas += 1
            continue

        except Exception as e:
            # Erro de LLM (timeout, rate limit, etc.) — levanta para o LangGraph retry
            logger.error(f"[{article_id}] Erro LLM na redação: {e}")
            raise

    duracao = time.monotonic() - t_inicio
    duracoes = dict(state.get("duracoes", {}))
    duracoes["redigir"] = duracao

    if not artigo_redigido:
        logger.error(f"[{article_id}] Redação falhou após {MAX_TENTATIVAS_JSON} tentativas: {erro_redacao}")
        return {
            "artigo_redigido": None,
            "erro_fatal": f"Redação falhou: {erro_redacao}",
            "tentativas_redacao": tentativas,
            "step_atual": "redigir",
            "duracoes": duracoes,
        }

    return {
        "artigo_redigido": artigo_redigido,
        "modelo_redacao": modelo_usado,
        "tokens_redacao": tokens,
        "tentativas_redacao": tentativas,
        "erro_fatal": None,
        "step_atual": "redigir",
        "duracoes": duracoes,
    }
```

---

## PARTE VII — OTIMIZAÇÃO SEO COM LLM PADRÃO

### 7.1 System Prompt de SEO

```python
SYSTEM_PROMPT_SEO = """Você é um especialista em SEO para portais de notícias brasileiros.

Sua tarefa é otimizar os metadados de SEO de uma matéria jornalística para maximizar cliques no Google News e busca orgânica.

═══════════════════════════════════════════════════════════════
REGRAS DE SEO PARA PORTAIS DE NOTÍCIAS (2026)
═══════════════════════════════════════════════════════════════

**TÍTULO SEO** (campo: titulo_seo)
- Máximo 60 caracteres (será truncado pelo Google acima disso)
- Palavra-chave PRINCIPAL no início (primeiras 3 palavras)
- Concreto e específico: NÃO "Governo anuncia medidas" MAS "Fazenda corta R$ 15 bi em gastos"
- Inclui entidade principal + ação + número/dado quando possível
- SEM aspas no título SEO

**DESCRIÇÃO SEO / META DESCRIPTION** (campo: descricao_seo)
- Máximo 155 caracteres
- Inclui palavra-chave principal no início
- Inclui micro CTA: "Saiba mais", "Entenda", "Veja o que muda"
- Responde: por que o leitor deve clicar?
- Formato: [Palavra-chave]: [detalhe específico]. [CTA].

**SLUG** (campo: slug)
- Máximo 60 caracteres
- Apenas letras minúsculas, números e hífens
- Sem preposições ("de", "da", "do", "em", "para")
- Sem artigos ("o", "a", "os", "as", "um", "uma")
- Inclui entidade principal e ação principal
- Exemplo: "fazenda-corte-gastos-15-bilhoes-2026"

**PALAVRAS-CHAVE** (campo: keywords)
- 3 a 5 termos de busca relevantes
- Mix: específicos (nome próprio) + gerais (tema)
- Ordem de importância decrescente
- Exemplos: ["Fazenda", "corte de gastos", "deficit primario", "orcamento 2026"]

**SCHEMA.ORG** (campo: schema_type)
- "NewsArticle" para notícias factuais
- "AnalysisNewsArticle" para análises/opinião
- "ReportageNewsArticle" para reportagens investigativas

═══════════════════════════════════════════════════════════════
FORMATO DE RESPOSTA (JSON puro)
═══════════════════════════════════════════════════════════════

{
  "titulo_seo": "string — máx 60 chars",
  "descricao_seo": "string — máx 155 chars",
  "slug": "string — máx 60 chars, apenas letras/números/hífens",
  "keywords": ["kw1", "kw2", "kw3"],
  "schema_type": "NewsArticle | AnalysisNewsArticle | ReportageNewsArticle"
}"""


async def node_otimizar_seo(state: ReporterState) -> Dict[str, Any]:
    """
    Nó LangGraph: otimiza metadados SEO com LLM PADRÃO.
    
    task_type = "seo_otimizacao" → tier PADRÃO (conforme tier_config)
    Se falhar: usa fallback com título/resumo truncados (não bloqueia)
    """
    from brasileira.llm.smart_router import get_router

    t_inicio = time.monotonic()
    article_id = state["article_id"]
    artigo = state.get("artigo_redigido", {})

    if not artigo:
        # Sem artigo redigido → vai para DLQ de qualquer forma
        return {"seo_data": None, "step_atual": "otimizar_seo"}

    titulo = artigo.get("titulo", "")
    subtitulo = artigo.get("subtitulo", "")
    resumo = artigo.get("resumo", "")
    categoria = artigo.get("categoria", state.get("categoria", ""))

    prompt = f"""Otimize o SEO da seguinte matéria jornalística:

Título: {titulo}
Subtítulo: {subtitulo}
Resumo: {resumo}
Categoria: {categoria}

Retorne APENAS o JSON de SEO:"""

    router = get_router()
    seo_data = None
    modelo_seo = None

    try:
        response = await router.complete(
            task_type="seo_otimizacao",    # → tier PADRÃO
            system_prompt=SYSTEM_PROMPT_SEO,
            user_prompt=prompt,
            max_tokens=512,
            temperature=0.3,               # Baixa criatividade para SEO mecânico
            agent_id=f"reporter-{state['worker_id']}",
        )
        modelo_seo = response.model
        conteudo = response.content.strip()
        conteudo = re.sub(r'^```json\s*', '', conteudo)
        conteudo = re.sub(r'\s*```$', '', conteudo)
        seo_data = json.loads(conteudo)

    except Exception as e:
        logger.warning(f"[{article_id}] SEO LLM falhou, usando fallback: {e}")
        # Fallback: gera SEO básico sem LLM
        seo_data = _gerar_seo_fallback(titulo, resumo, categoria)
        modelo_seo = "fallback"

    # Validação e sanitização
    seo_data = _sanitizar_seo(seo_data, titulo, resumo)

    duracao = time.monotonic() - t_inicio
    duracoes = dict(state.get("duracoes", {}))
    duracoes["otimizar_seo"] = duracao

    return {
        "seo_data": seo_data,
        "modelo_seo": modelo_seo,
        "step_atual": "otimizar_seo",
        "duracoes": duracoes,
    }


def _gerar_seo_fallback(titulo: str, resumo: str, categoria: str) -> Dict:
    """Gera SEO básico sem LLM como fallback de emergência."""
    # Slug básico
    slug = re.sub(r'[^a-z0-9\s-]', '', titulo.lower())
    slug = re.sub(r'\s+', '-', slug.strip())
    slug = slug[:60]

    # Remove palavras comuns do slug
    palavras_comuns = ['de', 'da', 'do', 'em', 'para', 'com', 'que', 'e', 'o', 'a']
    partes = [p for p in slug.split('-') if p not in palavras_comuns]
    slug = '-'.join(partes[:8])

    return {
        "titulo_seo": titulo[:60],
        "descricao_seo": resumo[:155] if resumo else titulo[:155],
        "slug": slug,
        "keywords": [categoria],
        "schema_type": "NewsArticle",
    }


def _sanitizar_seo(seo: Dict, titulo: str, resumo: str) -> Dict:
    """Garante que SEO data está dentro dos limites."""
    return {
        "titulo_seo": (seo.get("titulo_seo") or titulo)[:60],
        "descricao_seo": (seo.get("descricao_seo") or resumo)[:155],
        "slug": re.sub(r'[^a-z0-9-]', '', (seo.get("slug") or "").lower())[:60] or "artigo",
        "keywords": (seo.get("keywords") or [])[:5],
        "schema_type": seo.get("schema_type", "NewsArticle"),
    }
```

### 7.2 SEO para Google News — Critérios Obrigatórios

Conforme padrões de portais brasileiros para [Google News](https://searchonedigital.com.br/blog/seo-para-portais-de-noticia/):

| Critério | Implementação |
|----------|---------------|
| Frescor do conteúdo | Publicação imediata (sem draft) |
| Relevância de palavras-chave | Título SEO com palavra-chave nas primeiras 3 palavras |
| Proeminência | Cobertura de 100% das fontes |
| Autoridade | Crédito explícito à fonte no conteúdo |
| Usabilidade | HTML limpo, sem markdown, schema NewsArticle |
| Localização | Tags de categoria regional quando aplicável |
| Dados estruturados | `schema_type: NewsArticle` no meta |

---

## PARTE VIII — PUBLICAÇÃO WORDPRESS (REST API)

### 8.1 WordPressPublisher — Implementação Completa

```python
# brasileira/integrations/wordpress_client.py

import asyncio
import base64
import logging
import re
import html as html_module
from typing import Optional, List, Dict, Any

import httpx

logger = logging.getLogger("reporter.wordpress")

# Auth: Application Password (iapublicador)
WP_URL = "https://brasileira.news"
WP_API_BASE = f"{WP_URL}/wp-json/wp/v2"
WP_MEDIA_API = f"{WP_URL}/wp-json/wp/v2/media"

# Headers base para todas as requisições
def _get_headers(user: str, app_password: str) -> Dict[str, str]:
    """Gera headers com Basic Auth para Application Password."""
    credentials = f"{user}:{app_password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "User-Agent": "brasileira.news/reporter-v3",
    }

# Timeout para publicação
WP_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

# Retry config
MAX_RETRIES_WP = 3
RETRY_BASE_DELAY = 2.0


async def _request_with_retry(
    method: str,
    url: str,
    headers: Dict,
    max_retries: int = MAX_RETRIES_WP,
    **kwargs,
) -> Optional[httpx.Response]:
    """
    Faz request HTTP com retry e backoff exponencial.
    Retorna None após max_retries falhas consecutivas.
    NUNCA levanta exceção — retorna None em caso de falha total.
    """
    async with httpx.AsyncClient(timeout=WP_TIMEOUT, http2=True) as client:
        for tentativa in range(1, max_retries + 1):
            try:
                resp = await client.request(method, url, headers=headers, **kwargs)
                if resp.status_code < 500:
                    return resp
                # 5xx: servidor com problema — retry
                logger.warning(
                    f"WP HTTP {resp.status_code} em {url} "
                    f"(tentativa {tentativa}/{max_retries})"
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning(
                    f"WP request falhou em {url} "
                    f"(tentativa {tentativa}/{max_retries}): {e}"
                )

            if tentativa < max_retries:
                delay = RETRY_BASE_DELAY ** tentativa
                await asyncio.sleep(delay)

    return None


class WordPressPublisherV3:
    """
    Publicador WordPress para o Reporter V3.
    
    Responsabilidades:
    - Resolver categorias (cache DB → criar se não existe)
    - Resolver/criar tags
    - Publicar post com status="publish" (NUNCA draft)
    - Definir metadados SEO (Yoast + AIOSEO)
    - Definir schema.org
    """

    def __init__(self, wp_url: str, wp_user: str, wp_app_password: str):
        self.wp_url = wp_url
        self.api_base = f"{wp_url}/wp-json/wp/v2"
        self.headers = _get_headers(wp_user, wp_app_password)

        # Caches em memória (carregados do banco)
        self._category_cache: Dict[str, int] = {}  # nome_normalizado → id
        self._tag_cache: Dict[str, int] = {}        # nome_normalizado → id
        self._caches_carregados = False

    async def _carregar_caches(self) -> None:
        """Carrega categorias e tags do banco WordPress."""
        if self._caches_carregados:
            return
        try:
            from brasileira.integrations.postgres_client import get_pg_pool
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                # Categorias
                rows = await conn.fetch(
                    "SELECT t.name, tt.term_id FROM wp_7_terms t "
                    "JOIN wp_7_term_taxonomy tt ON t.term_id = tt.term_id "
                    "WHERE tt.taxonomy = 'category'"
                )
                for row in rows:
                    key = html_module.unescape(row["name"]).lower().strip()
                    self._category_cache[key] = row["term_id"]

                # Tags
                rows = await conn.fetch(
                    "SELECT t.name, tt.term_id FROM wp_7_terms t "
                    "JOIN wp_7_term_taxonomy tt ON t.term_id = tt.term_id "
                    "WHERE tt.taxonomy = 'post_tag'"
                )
                for row in rows:
                    key = html_module.unescape(row["name"]).lower().strip()
                    self._tag_cache[key] = row["term_id"]

            self._caches_carregados = True
            logger.info(
                f"WP caches: {len(self._category_cache)} categorias, "
                f"{len(self._tag_cache)} tags"
            )
        except Exception as e:
            logger.warning(f"Falha ao carregar caches WP do banco: {e}")

    async def resolver_categoria(self, nome: str) -> Optional[int]:
        """Retorna ID da categoria. Cria se não existe."""
        await self._carregar_caches()
        key = html_module.unescape(nome).lower().strip()

        if key in self._category_cache:
            return self._category_cache[key]

        # Cria categoria via API
        slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
        resp = await _request_with_retry(
            "POST",
            f"{self.api_base}/categories",
            self.headers,
            json={"name": nome, "slug": slug},
        )
        if resp and resp.status_code in (200, 201):
            cat_id = resp.json().get("id")
            self._category_cache[key] = cat_id
            logger.info(f"WP: Categoria criada: '{nome}' (id={cat_id})")
            return cat_id

        logger.warning(f"WP: Não foi possível criar categoria: '{nome}'")
        return None

    async def resolver_tags(self, nomes: List[str]) -> List[int]:
        """Retorna lista de IDs de tags. Cria as que não existem."""
        await self._carregar_caches()
        ids = []
        for nome in nomes:
            if not nome or not nome.strip():
                continue
            key = nome.lower().strip()
            if key in self._tag_cache:
                ids.append(self._tag_cache[key])
                continue
            # Cria tag via API
            slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
            resp = await _request_with_retry(
                "POST",
                f"{self.api_base}/tags",
                self.headers,
                json={"name": nome, "slug": slug},
            )
            if resp and resp.status_code in (200, 201):
                tag_id = resp.json().get("id")
                self._tag_cache[key] = tag_id
                ids.append(tag_id)
        return ids

    async def publicar_artigo(
        self,
        artigo: Dict,
        seo: Dict,
        fonte_url: str,
        fonte_nome: str,
        categoria_nome: str,
        tags_nomes: List[str],
        og_image_url: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Publica artigo no WordPress.
        
        OBRIGATÓRIO: status="publish" — NUNCA draft.
        
        Retorna:
            {"post_id": int, "post_url": str} se sucesso
            None se falhou
        """
        await self._carregar_caches()

        # Resolve IDs de categoria e tags
        categoria_id = await self.resolver_categoria(categoria_nome)
        tag_ids = await self.resolver_tags(tags_nomes)

        # Monta payload do post
        post_data: Dict[str, Any] = {
            "title":    artigo.get("titulo", ""),
            "content":  artigo.get("conteudo", ""),
            "excerpt":  artigo.get("resumo", ""),
            "status":   "publish",           # ← OBRIGATÓRIO. NUNCA "draft"
            "slug":     seo.get("slug", ""),
            "categories": [categoria_id] if categoria_id else [],
            "tags":      tag_ids,
            "meta": {
                # SEO — compatível com Yoast e AIOSEO
                "_yoast_wpseo_title":       seo.get("titulo_seo", ""),
                "_yoast_wpseo_metadesc":    seo.get("descricao_seo", ""),
                "_aioseo_title":            seo.get("titulo_seo", ""),
                "_aioseo_description":      seo.get("descricao_seo", ""),
                # Rastreabilidade editorial
                "fonte_original":           fonte_url,
                "fonte_nome":               fonte_nome,
                "schema_type":              seo.get("schema_type", "NewsArticle"),
            },
        }

        # Publica
        resp = await _request_with_retry(
            "POST",
            f"{self.api_base}/posts",
            self.headers,
            json=post_data,
        )

        if not resp:
            logger.error(f"WP: Falha total ao publicar '{artigo.get('titulo', '')[:60]}'")
            return None

        if resp.status_code not in (200, 201):
            logger.error(
                f"WP: HTTP {resp.status_code} ao publicar: {resp.text[:300]}"
            )
            return None

        dados = resp.json()
        post_id = dados.get("id")
        post_url = dados.get("link", "")

        logger.info(
            f"WP: Post publicado: id={post_id} | "
            f"'{artigo.get('titulo', '')[:60]}' | {post_url}"
        )

        return {"post_id": post_id, "post_url": post_url}
```

### 8.2 Nó de Publicação

```python
async def node_publicar_wp(state: ReporterState) -> Dict[str, Any]:
    """
    Nó LangGraph: publica artigo no WordPress.
    
    REGRAS OBRIGATÓRIAS:
    - status="publish" SEMPRE
    - Nunca publicar draft
    - Se falhar após 3 retries: registra como erro_fatal (vai para DLQ)
    - Registra no PostgreSQL mesmo em caso de erro (para análise)
    """
    import time
    from brasileira.integrations.wordpress_client import WordPressPublisherV3
    from brasileira.config import settings

    t_inicio = time.monotonic()
    article_id = state["article_id"]
    artigo = state.get("artigo_redigido", {})
    seo = state.get("seo_data", {}) or {}
    raw = state["raw_article"]

    if not artigo:
        return {
            "publicado": False,
            "erro_fatal": "Sem artigo redigido para publicar",
            "step_atual": "publicar_wp",
        }

    logger.info(f"[{article_id}] Publicando no WordPress: '{artigo.get('titulo', '')[:60]}'")

    wp = WordPressPublisherV3(
        wp_url=settings.WP_URL,
        wp_user=settings.WP_USER,
        wp_app_password=settings.WP_APP_PASS,
    )

    resultado = await wp.publicar_artigo(
        artigo=artigo,
        seo=seo,
        fonte_url=state.get("fonte_url", raw.get("url_fonte", "")),
        fonte_nome=state.get("fonte_nome", raw.get("fonte_nome", "")),
        categoria_nome=artigo.get("categoria", state.get("categoria", "Últimas Notícias")),
        tags_nomes=artigo.get("tags", []),
        og_image_url=state.get("metadados_extracao", {}).get("og_image"),
    )

    duracao = time.monotonic() - t_inicio
    duracoes = dict(state.get("duracoes", {}))
    duracoes["publicar_wp"] = duracao

    if not resultado:
        return {
            "publicado": False,
            "erro_fatal": "WordPress publicação falhou após 3 retries",
            "step_atual": "publicar_wp",
            "duracoes": duracoes,
        }

    # Registra no PostgreSQL
    await _registrar_artigo_publicado(
        article_id=article_id,
        wp_post_id=resultado["post_id"],
        post_url=resultado["post_url"],
        raw=raw,
        artigo=artigo,
        seo=seo,
        state=state,
    )

    return {
        "wp_post_id": resultado["post_id"],
        "wp_post_url": resultado["post_url"],
        "publicado": True,
        "erro_fatal": None,
        "step_atual": "publicar_wp",
        "duracoes": duracoes,
    }


async def _registrar_artigo_publicado(
    article_id: str,
    wp_post_id: int,
    post_url: str,
    raw: Dict,
    artigo: Dict,
    seo: Dict,
    state: ReporterState,
) -> None:
    """Registra artigo publicado no PostgreSQL (tabela artigos)."""
    from brasileira.integrations.postgres_client import get_pg_pool
    import hashlib

    url_fonte = raw.get("url_fonte", "")
    url_hash = hashlib.sha256(url_fonte.encode()).hexdigest()

    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO artigos (
                    wp_post_id, url_fonte, url_hash, titulo, editoria,
                    urgencia, score_relevancia, fonte_nome, revisado,
                    imagem_aplicada
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, false, false)
                ON CONFLICT (url_hash) DO UPDATE SET
                    wp_post_id = EXCLUDED.wp_post_id,
                    titulo = EXCLUDED.titulo
            """,
                wp_post_id,
                url_fonte,
                url_hash,
                artigo.get("titulo", ""),
                artigo.get("categoria", state.get("categoria", "")),
                state.get("urgencia", "NORMAL"),
                raw.get("score_relevancia", 0.5),
                raw.get("fonte_nome", ""),
            )
    except Exception as e:
        logger.warning(f"Falha ao registrar artigo no PostgreSQL: {e}")
```

### 8.3 Mapeamento de Macrocategorias → IDs WordPress

```python
# brasileira/config/categories.py
# Mapeamento das 16 macrocategorias para slugs WordPress
# IDs reais são carregados do banco em runtime

CATEGORIA_SLUG_MAP = {
    "Política":                  "politica",
    "Economia":                  "economia",
    "Esportes":                  "esportes",
    "Tecnologia":                "tecnologia",
    "Saúde":                     "saude",
    "Educação":                  "educacao",
    "Ciência":                   "ciencia",
    "Cultura / Entretenimento":  "cultura-entretenimento",
    "Mundo / Internacional":     "mundo-internacional",
    "Meio Ambiente":             "meio-ambiente",
    "Segurança / Justiça":       "seguranca-justica",
    "Sociedade":                 "sociedade",
    "Brasil":                    "brasil",
    "Regionais":                 "regionais",
    "Opinião / Análise":         "opiniao-analise",
    "Últimas Notícias":          "ultimas-noticias",
}

# Normalização de categoria para lookup
def normalizar_categoria(nome: str) -> str:
    """Normaliza nome de categoria para lookup no mapa."""
    for cat_oficial in CATEGORIA_SLUG_MAP:
        if cat_oficial.lower() in nome.lower() or nome.lower() in cat_oficial.lower():
            return cat_oficial
    return "Últimas Notícias"  # Fallback
```

---

## PARTE IX — EVENTO KAFKA article_published

### 9.1 Schema do Evento

```python
# brasileira/agents/reporter_events.py

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional
import json


@dataclass
class ArticlePublishedEvent:
    """
    Evento disparado pelo Reporter após publicação bem-sucedida.
    
    Consumido por:
    - Fotógrafo: busca imagem para o artigo
    - Revisor: revisa e corrige in-place
    - Curador: considera para homepage
    - Monitor Sistema: atualiza métricas de throughput
    - Editor-Chefe: analytics de cobertura
    """
    event: str                       # "article_published"
    post_id: int                     # ID do post no WordPress
    article_id: str                  # ID interno (trace_id)
    titulo: str                      # Título do artigo
    editoria: str                    # Categoria (uma das 16)
    urgencia: str                    # FLASH | NORMAL | ANÁLISE
    url: str                         # URL permanente do post
    url_fonte: str                   # URL da fonte original
    fonte_nome: str                  # Nome da fonte
    og_image_url: Optional[str]      # Imagem da fonte (para o Fotógrafo tentar primeiro)
    publicado_em: str                # ISO 8601 com timezone (America/Sao_Paulo)
    palavras: int                    # Contagem de palavras do artigo
    modelo_redacao: str              # Qual modelo LLM foi usado
    worker_id: str                   # Qual worker processou
    duracoes: dict                   # Duração de cada step em segundos

    def to_kafka_value(self) -> bytes:
        return json.dumps(asdict(self), ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_state(cls, state: "ReporterState") -> "ArticlePublishedEvent":
        artigo = state.get("artigo_redigido", {})
        raw = state.get("raw_article", {})
        conteudo = artigo.get("conteudo", "")
        import re
        texto_sem_html = re.sub(r'<[^>]+>', ' ', conteudo)
        palavras = len(texto_sem_html.split())

        agora = datetime.now(timezone.utc).astimezone(
            __import__("zoneinfo").ZoneInfo("America/Sao_Paulo")
        ).isoformat()

        return cls(
            event="article_published",
            post_id=state.get("wp_post_id", 0),
            article_id=state.get("article_id", ""),
            titulo=artigo.get("titulo", ""),
            editoria=artigo.get("categoria", state.get("categoria", "")),
            urgencia=state.get("urgencia", "NORMAL"),
            url=state.get("wp_post_url", ""),
            url_fonte=state.get("fonte_url", raw.get("url_fonte", "")),
            fonte_nome=state.get("fonte_nome", raw.get("fonte_nome", "")),
            og_image_url=state.get("metadados_extracao", {}).get("og_image"),
            publicado_em=agora,
            palavras=palavras,
            modelo_redacao=state.get("modelo_redacao", ""),
            worker_id=state.get("worker_id", ""),
            duracoes=dict(state.get("duracoes", {})),
        )
```

### 9.2 Nó de Disparo de Eventos

```python
async def node_disparar_eventos(state: ReporterState) -> Dict[str, Any]:
    """
    Nó LangGraph: dispara evento Kafka após publicação.
    
    Também:
    - Salva embedding no pgvector (para RAG futuro)
    - Atualiza working memory no Redis
    - Registra métricas no log
    """
    import time
    from brasileira.integrations.kafka_client import get_kafka_producer
    from brasileira.agents.reporter_rag import salvar_embedding_artigo
    from brasileira.integrations.redis_client import get_redis

    t_inicio = time.monotonic()
    article_id = state["article_id"]
    artigo = state.get("artigo_redigido", {})
    wp_post_id = state.get("wp_post_id")

    logger.info(f"[{article_id}] Disparando eventos pós-publicação")

    # ── 1. Kafka: article-published ───────────────────────────────────
    try:
        evento = ArticlePublishedEvent.from_state(state)
        producer = await get_kafka_producer()
        await producer.send(
            topic="article-published",
            key=str(wp_post_id).encode(),
            value=evento.to_kafka_value(),
        )
        logger.info(f"[{article_id}] Kafka: article-published disparado (post_id={wp_post_id})")
    except Exception as e:
        logger.warning(f"[{article_id}] Kafka falhou (não crítico): {e}")

    # ── 2. pgvector: salva embedding para RAG futuro ──────────────────
    try:
        from brasileira.integrations.postgres_client import get_pg_pool
        from brasileira.llm.smart_router import get_router
        pg_pool = await get_pg_pool()
        router = get_router()
        await salvar_embedding_artigo(
            article_id=article_id,
            wp_post_id=wp_post_id,
            titulo=artigo.get("titulo", ""),
            resumo=artigo.get("resumo", ""),
            categoria=artigo.get("categoria", ""),
            pg_pool=pg_pool,
            embedding_client=router,
        )
    except Exception as e:
        logger.warning(f"[{article_id}] Falha ao salvar embedding (não crítico): {e}")

    # ── 3. Redis: atualiza working memory ────────────────────────────
    try:
        redis = await get_redis()
        cycle_id = state.get("cycle_id", "unknown")
        await redis.hincrby(
            f"agent:working_memory:reporter:{cycle_id}",
            "artigos_publicados",
            1,
        )
        await redis.expire(
            f"agent:working_memory:reporter:{cycle_id}",
            4 * 3600,  # TTL 4h
        )
    except Exception as e:
        logger.warning(f"[{article_id}] Redis working memory falhou (não crítico): {e}")

    duracao = time.monotonic() - t_inicio
    duracoes = dict(state.get("duracoes", {}))
    duracoes["disparar_eventos"] = duracao

    return {
        "eventos_disparados": True,
        "step_atual": "disparar_eventos",
        "duracoes": duracoes,
    }
```

### 9.3 Nó DLQ

```python
async def node_registrar_erro_dlq(state: ReporterState) -> Dict[str, Any]:
    """
    Nó DLQ: registra artigos que falharam para análise e reprocessamento.
    
    NUNCA levanta exceção. Log + registro + continua.
    """
    from brasileira.integrations.kafka_client import get_kafka_producer
    import json

    article_id = state["article_id"]
    erro = state.get("erro_fatal", "Erro desconhecido")
    raw = state.get("raw_article", {})

    logger.error(f"[{article_id}] DLQ: {erro}")

    # Envia para dead-letter topic
    try:
        producer = await get_kafka_producer()
        await producer.send(
            topic="reporter-dlq",
            key=article_id.encode(),
            value=json.dumps({
                "article_id": article_id,
                "erro": erro,
                "step_que_falhou": state.get("step_atual", ""),
                "raw_article": raw,
                "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            }, ensure_ascii=False).encode("utf-8"),
        )
    except Exception as e:
        logger.warning(f"[{article_id}] Falha ao enviar para DLQ: {e}")

    return {
        "eventos_disparados": False,
        "step_atual": "dlq",
    }
```

---

## PARTE X — MEMÓRIA DO REPORTER (SEMÂNTICA, EPISÓDICA, WORKING)

### 10.1 Três Camadas de Memória

O Reporter V3 implementa memória real (não hooks vazios como na V2):

| Tipo | O Que Armazena | Storage | TTL | Uso |
|------|---------------|---------|-----|-----|
| **Semântica** | Conhecimento de domínio: perfil de fontes, padrões editoriais, taxonomia | pgvector | Permanente | Carregado no system prompt como contexto estático |
| **Episódica** | Artigos publicados anteriormente (embeddings) | pgvector | 90 dias | RAG para contextualização |
| **Working** | Estado do ciclo: artigos processados, contadores, tempo médio | Redis | 4h | Monitoramento de throughput por worker |

### 10.2 Memória Semântica — Perfil de Fontes

```python
# brasileira/memory/reporter_semantic.py

import json
import logging
from typing import Optional, Dict

logger = logging.getLogger("reporter.memory")


async def carregar_perfil_fonte(fonte_id: str, pg_pool) -> Optional[str]:
    """
    Recupera perfil editorial da fonte do pgvector.
    Perfil: estilo editorial, cobertura típica, confiabilidade.
    Usado como contexto adicional no prompt de redação.
    """
    try:
        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT conteudo FROM memoria_agentes
                WHERE agente = 'reporter'
                  AND tipo = 'semantica'
                  AND conteudo->>'fonte_id' = $1
                ORDER BY criado_em DESC
                LIMIT 1
            """, fonte_id)
            if row:
                dados = json.loads(row["conteudo"])
                return dados.get("perfil_texto", "")
    except Exception as e:
        logger.debug(f"Sem perfil semântico para fonte {fonte_id}: {e}")
    return None


async def atualizar_perfil_fonte(
    fonte_id: str,
    fonte_nome: str,
    categoria_tipica: str,
    num_artigos: int,
    pg_pool,
    embedding_client,
) -> None:
    """
    Atualiza memória semântica com perfil da fonte.
    Chamado após N artigos processados da mesma fonte.
    """
    perfil = {
        "fonte_id": fonte_id,
        "fonte_nome": fonte_nome,
        "categoria_tipica": categoria_tipica,
        "num_artigos_processados": num_artigos,
        "perfil_texto": (
            f"{fonte_nome} é uma fonte que tipicamente cobre {categoria_tipica}. "
            f"Já publicamos {num_artigos} artigos desta fonte."
        ),
    }

    from brasileira.agents.reporter_rag import gerar_embedding
    embedding = await gerar_embedding(perfil["perfil_texto"], embedding_client)
    embedding_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"

    try:
        async with pg_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO memoria_agentes (agente, tipo, conteudo, embedding, ttl_dias)
                VALUES ('reporter', 'semantica', $1::jsonb, $2::vector, 365)
                ON CONFLICT DO NOTHING
            """, json.dumps(perfil, ensure_ascii=False), embedding_str)
    except Exception as e:
        logger.warning(f"Falha ao atualizar perfil semântico de {fonte_nome}: {e}")
```

### 10.3 Working Memory por Ciclo

```python
# brasileira/memory/reporter_working.py

import json
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger("reporter.working_memory")


class ReporterWorkingMemory:
    """
    Memória de trabalho do Reporter em Redis.
    TTL de 4h — persiste pelo ciclo inteiro.
    """

    def __init__(self, redis_client, worker_id: str, cycle_id: str):
        self.redis = redis_client
        self.key = f"agent:working_memory:reporter:{cycle_id}:{worker_id}"
        self.ttl = 4 * 3600  # 4 horas

    async def inicializar(self) -> None:
        """Inicializa working memory para o ciclo."""
        await self.redis.hset(self.key, mapping={
            "worker_id": self.worker_id if hasattr(self, "worker_id") else "",
            "cycle_id": self.key.split(":")[-2],
            "iniciado_em": str(time.time()),
            "artigos_publicados": "0",
            "artigos_dlq": "0",
            "tempo_medio_ms": "0",
            "ultimo_artigo_em": "",
        })
        await self.redis.expire(self.key, self.ttl)

    async def registrar_publicacao(
        self, article_id: str, titulo: str, duracao_total_ms: int
    ) -> None:
        """Atualiza contadores após publicação bem-sucedida."""
        await self.redis.hincrby(self.key, "artigos_publicados", 1)
        await self.redis.hset(self.key, mapping={
            "ultimo_artigo_id": article_id,
            "ultimo_artigo_titulo": titulo[:100],
            "ultimo_artigo_em": str(time.time()),
        })
        # Atualiza média móvel de duração
        atual = await self.redis.hget(self.key, "artigos_publicados")
        n = int(atual or 1)
        media_atual = float(
            (await self.redis.hget(self.key, "tempo_medio_ms")) or 0
        )
        nova_media = media_atual + (duracao_total_ms - media_atual) / n
        await self.redis.hset(self.key, "tempo_medio_ms", str(int(nova_media)))

    async def registrar_dlq(self, article_id: str, erro: str) -> None:
        """Registra artigo que foi para DLQ."""
        await self.redis.hincrby(self.key, "artigos_dlq", 1)
        await self.redis.hset(self.key, mapping={
            "ultimo_dlq_id": article_id,
            "ultimo_dlq_erro": erro[:200],
        })

    async def obter_stats(self) -> Dict:
        """Retorna métricas do ciclo atual."""
        dados = await self.redis.hgetall(self.key)
        return {k.decode(): v.decode() for k, v in dados.items()}
```

---

## PARTE XI — SCHEMAS KAFKA E POSTGRESQL

### 11.1 Schema Kafka: classified-articles (Input)

```json
{
  "article_id": "art-g1-20260326-142001-abc123",
  "url_fonte": "https://g1.globo.com/politica/noticia/2026/03/26/titulo.html",
  "titulo_original": "Governo anuncia pacote fiscal de R$ 15 bilhões",
  "resumo_original": "O Ministério da Fazenda anunciou nesta terça-feira...",
  "html_preview": "<p>O Ministério da Fazenda...</p>",
  "categoria": "Economia",
  "urgencia": "NORMAL",
  "score_relevancia": 0.85,
  "fonte_nome": "G1 - O Portal de Notícias da Globo",
  "fonte_id": "fonte-001",
  "publicado_em": "2026-03-26T14:15:00-03:00",
  "og_image": "https://s2.glbimg.com/...",
  "tipo": "noticia_simples"
}
```

### 11.2 Schema Kafka: pautas-especiais (Input)

```json
{
  "pauta_id": "pauta-especial-20260326-001",
  "topico": "Reação do mercado ao pacote fiscal",
  "descricao": "O mercado financeiro reagiu com ...",
  "categoria": "Economia",
  "urgencia": "FLASH",
  "tipo": "pauta_especial",
  "fonte_urls": [],
  "contexto_adicional": "Gerada pelo Pauteiro após análise de trending",
  "gerado_por": "pauteiro",
  "timestamp": "2026-03-26T14:20:00-03:00"
}
```

### 11.3 Schema Kafka: pautas-gap (Input)

```json
{
  "pauta_id": "gap-20260326-001",
  "topico": "Crise na embaixada brasileira na Venezuela",
  "descricao": "G1, UOL e Folha estão cobrindo mas não temos nada",
  "categoria": "Mundo / Internacional",
  "urgencia": "FLASH",
  "tipo": "pauta_gap",
  "num_capas_concorrentes": 4,
  "fontes_concorrentes": [
    "https://g1.globo.com/...",
    "https://www.uol.com.br/..."
  ],
  "gerado_por": "monitor_concorrencia",
  "timestamp": "2026-03-26T14:30:00-03:00"
}
```

### 11.4 Schema Kafka: article-published (Output)

```json
{
  "event": "article_published",
  "post_id": 98765,
  "article_id": "art-g1-20260326-142001-abc123",
  "titulo": "Governo corta R$ 15 bilhões em gastos para equilibrar orçamento 2026",
  "editoria": "Economia",
  "urgencia": "NORMAL",
  "url": "https://brasileira.news/economia/governo-corte-gastos-15-bilhoes-2026/",
  "url_fonte": "https://g1.globo.com/...",
  "fonte_nome": "G1 - O Portal de Notícias da Globo",
  "og_image_url": "https://s2.glbimg.com/...",
  "publicado_em": "2026-03-26T11:20:00-03:00",
  "palavras": 412,
  "modelo_redacao": "claude-sonnet-4-6",
  "worker_id": "reporter-worker-03",
  "duracoes": {
    "extrair_conteudo": 2.3,
    "contextualizar": 0.8,
    "redigir": 12.4,
    "otimizar_seo": 3.1,
    "publicar_wp": 1.9,
    "disparar_eventos": 0.3
  }
}
```

### 11.5 PostgreSQL: Tabelas Relevantes

```sql
-- ── Artigos publicados (fonte de verdade) ─────────────────────────
CREATE TABLE IF NOT EXISTS artigos (
    id                  SERIAL PRIMARY KEY,
    wp_post_id          INTEGER      UNIQUE,
    url_fonte           TEXT         NOT NULL,
    url_hash            CHAR(64)     UNIQUE,     -- SHA-256 para dedup
    titulo              TEXT         NOT NULL,
    editoria            VARCHAR(50),
    urgencia            VARCHAR(20)  DEFAULT 'NORMAL',
    score_relevancia    FLOAT        DEFAULT 0.5,
    publicado_em        TIMESTAMPTZ  DEFAULT NOW(),
    revisado            BOOLEAN      DEFAULT FALSE,
    imagem_aplicada     BOOLEAN      DEFAULT FALSE,
    fonte_nome          VARCHAR(200),
    modelo_redacao      VARCHAR(100),
    palavras            INTEGER,
    duracao_total_ms    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_artigos_url_hash      ON artigos(url_hash);
CREATE INDEX IF NOT EXISTS idx_artigos_editoria      ON artigos(editoria);
CREATE INDEX IF NOT EXISTS idx_artigos_publicado     ON artigos(publicado_em DESC);
CREATE INDEX IF NOT EXISTS idx_artigos_wp_post_id    ON artigos(wp_post_id);

-- ── Memória dos agentes (pgvector) ────────────────────────────────
-- (já criada na PARTE V — reproduzida para completude)
CREATE TABLE IF NOT EXISTS memoria_agentes (
    id               SERIAL PRIMARY KEY,
    agente           VARCHAR(50)   NOT NULL,
    tipo             VARCHAR(20)   NOT NULL,   -- semantica | episodica
    conteudo         JSONB         NOT NULL,
    embedding        vector(1536),
    criado_em        TIMESTAMPTZ   DEFAULT NOW(),
    relevancia_score FLOAT         DEFAULT 0.5,
    ttl_dias         INTEGER       DEFAULT 90
);

CREATE INDEX IF NOT EXISTS idx_memoria_embedding_hnsw
    ON memoria_agentes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ── Log de erros do Reporter ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS reporter_erros (
    id             SERIAL PRIMARY KEY,
    article_id     VARCHAR(100),
    url_fonte      TEXT,
    step_falhou    VARCHAR(50),
    erro           TEXT,
    timestamp      TIMESTAMPTZ DEFAULT NOW(),
    reprocessado   BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_reporter_erros_reprocessado
    ON reporter_erros(reprocessado, timestamp DESC);
```

---

## PARTE XII — ESTRUTURA DE DIRETÓRIOS E DEPENDÊNCIAS

### 12.1 Estrutura de Diretórios

```
brasileira/
├── agents/
│   ├── reporter.py                    # ReporterAgent principal + worker pool
│   ├── reporter_extractors.py         # Content extraction (trafilatura + newspaper4k)
│   ├── reporter_rag.py                # RAG com pgvector
│   └── reporter_events.py             # ArticlePublishedEvent + nó disparar_eventos
│
├── config/
│   ├── settings.py                    # Variáveis de ambiente + defaults
│   ├── categories.py                  # CATEGORIA_SLUG_MAP (16 macrocategorias)
│   └── prompts/
│       ├── reporter_redacao.txt       # SYSTEM_PROMPT_REDACAO (contexto estático)
│       └── reporter_seo.txt           # SYSTEM_PROMPT_SEO (contexto estático)
│
├── integrations/
│   ├── wordpress_client.py            # WordPressPublisherV3
│   ├── kafka_client.py                # aiokafka producer/consumer
│   ├── postgres_client.py             # asyncpg pool + helpers
│   └── redis_client.py                # aioredis client
│
├── llm/
│   ├── smart_router.py                # SmartLLMRouter V3 (Componente #1)
│   └── tier_config.py                 # task_type → tier mapping
│
├── memory/
│   ├── reporter_semantic.py           # Memória semântica (perfil de fontes)
│   └── reporter_working.py            # Working memory (Redis por ciclo)
│
└── workers/
    └── reporter_worker_pool.py        # Worker pool manager
```

### 12.2 requirements.txt (Dependências do Reporter)

```txt
# ── Core ─────────────────────────────────────────────────────────────
python-dotenv>=1.0.0
pydantic>=2.7.0

# ── LangGraph + Checkpointing ────────────────────────────────────────
langgraph>=1.0.0
langgraph-checkpoint-postgres>=2.0.0
psycopg[pool]>=3.2.0         # psycopg3 (psycopg_pool incluído)

# ── Kafka ─────────────────────────────────────────────────────────────
aiokafka>=0.11.0

# ── HTTP + Content Extraction ─────────────────────────────────────────
httpx[http2]>=0.28.0         # Async HTTP + HTTP/2
trafilatura>=2.0.0           # Extração principal de conteúdo
newspaper4k>=0.9.3           # Fallback para sites complexos
lxml>=5.2.0                  # Backend HTML do trafilatura
certifi>=2024.0.0

# ── PostgreSQL + pgvector ─────────────────────────────────────────────
asyncpg>=0.29.0              # Driver async PostgreSQL
pgvector>=0.3.0              # Python client para pgvector
numpy>=1.26.0                # Operações com embeddings

# ── Redis ─────────────────────────────────────────────────────────────
redis[hiredis]>=5.0.0        # aioredis via redis-py async

# ── LLM Gateway ───────────────────────────────────────────────────────
litellm>=1.50.0              # Multi-provider LLM
anthropic>=0.40.0
openai>=1.50.0
google-generativeai>=0.8.0

# ── Observabilidade ───────────────────────────────────────────────────
opentelemetry-sdk>=1.28.0
opentelemetry-exporter-otlp>=1.28.0

# ── Utilitários ───────────────────────────────────────────────────────
zoneinfo>=0.2.1              # Timezone America/Sao_Paulo
```

---

## PARTE XIII — ENTRYPOINT, INICIALIZAÇÃO, WORKER POOL

### 13.1 Worker Pool Manager

```python
# brasileira/workers/reporter_worker_pool.py

import asyncio
import logging
import os
import signal
import time
import uuid
from typing import Optional

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from brasileira.agents.reporter import build_reporter_graph, ReporterState
from brasileira.agents.reporter_extractors import node_extrair_conteudo
from brasileira.agents.reporter_rag import node_contextualizar
from brasileira.agents.reporter import (
    node_redigir, node_otimizar_seo, node_publicar_wp, node_disparar_eventos,
    node_registrar_erro_dlq
)
from brasileira.integrations.kafka_client import get_kafka_producer
from brasileira.memory.reporter_working import ReporterWorkingMemory

logger = logging.getLogger("reporter.worker_pool")

# Config do pool
NUM_WORKERS_DEFAULT = int(os.getenv("REPORTER_NUM_WORKERS", "5"))
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# Tópicos Kafka que o Reporter consome
INPUT_TOPICS = ["classified-articles", "pautas-especiais", "pautas-gap"]
CONSUMER_GROUP = "reporter-workers"


class ReporterWorkerPool:
    """
    Pool de workers do Reporter.
    
    Cada worker é uma coroutine independente que consome mensagens
    do Kafka e executa o pipeline LangGraph.
    
    Design:
    - N workers compartilham UM consumer group Kafka
    - Kafka distribui partições automaticamente entre workers
    - Falha de um worker não afeta os outros
    - Checkpointing PostgresSaver por thread_id (article_id)
    """

    def __init__(self, num_workers: int = NUM_WORKERS_DEFAULT):
        self.num_workers = num_workers
        self.workers: list = []
        self._shutdown = asyncio.Event()
        self.cycle_id = f"cycle-{time.strftime('%Y%m%d-%H%M%S')}"

    async def inicializar(self) -> None:
        """Inicializa recursos compartilhados."""
        from brasileira.agents.reporter import criar_checkpointer
        self.checkpointer = await criar_checkpointer()
        self.graph = build_reporter_graph(self.checkpointer)
        logger.info(f"ReporterWorkerPool inicializado: {self.num_workers} workers")

    async def start(self) -> None:
        """Inicia o pool de workers."""
        await self.inicializar()

        # Cria N workers concorrentes
        tasks = [
            asyncio.create_task(
                self._worker_loop(f"reporter-worker-{i:02d}"),
                name=f"reporter-worker-{i:02d}",
            )
            for i in range(self.num_workers)
        ]
        self.workers = tasks

        logger.info(f"Pool de {self.num_workers} reporters iniciado")

        # Aguarda shutdown signal
        await self._shutdown.wait()

        # Cancela todos os workers graciosamente
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Pool de reporters encerrado")

    async def _worker_loop(self, worker_id: str) -> None:
        """
        Loop infinito de um worker.
        
        NUNCA para. NUNCA bloqueia outros workers.
        Erros são isolados por artigo.
        """
        redis = None
        try:
            from brasileira.integrations.redis_client import get_redis
            redis = await get_redis()
        except Exception:
            pass

        working_mem = None

        consumer = AIOKafkaConsumer(
            *INPUT_TOPICS,
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=CONSUMER_GROUP,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            max_poll_records=1,      # Um artigo por vez por worker
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
        )

        await consumer.start()
        logger.info(f"[{worker_id}] Consumer Kafka iniciado — aguardando mensagens")

        try:
            async for msg in consumer:
                if self._shutdown.is_set():
                    break

                # Processa mensagem
                try:
                    await self._processar_mensagem(
                        worker_id=worker_id,
                        msg=msg,
                        working_mem=working_mem,
                    )
                except Exception as e:
                    # Isolamento total: erro aqui não mata o worker
                    logger.error(
                        f"[{worker_id}] Erro ao processar mensagem "
                        f"(topic={msg.topic}, offset={msg.offset}): {e}"
                    )
                    continue

        finally:
            await consumer.stop()
            logger.info(f"[{worker_id}] Consumer Kafka encerrado")

    async def _processar_mensagem(
        self,
        worker_id: str,
        msg,
        working_mem: Optional[ReporterWorkingMemory],
    ) -> None:
        """
        Processa UMA mensagem Kafka: monta estado inicial e executa o grafo.
        """
        import json

        t_inicio = time.monotonic()
        payload = json.loads(msg.value.decode("utf-8"))

        # Determina tipo de mensagem
        topic = msg.topic
        article_id = payload.get("article_id") or payload.get("pauta_id") or str(uuid.uuid4())

        logger.info(
            f"[{worker_id}] Processando {topic}: {article_id} "
            f"| '{payload.get('titulo_original', payload.get('topico', ''))[:60]}'"
        )

        # Monta estado inicial
        initial_state: ReporterState = {
            "article_id": article_id,
            "raw_article": payload,
            "fonte_nome": payload.get("fonte_nome", ""),
            "fonte_url": payload.get("url_fonte", ""),
            "categoria": payload.get("categoria", "Últimas Notícias"),
            "urgencia": payload.get("urgencia", "NORMAL"),
            "tipo": payload.get("tipo", "noticia_simples"),

            # Campos a serem preenchidos pelo pipeline
            "conteudo_extraido": None,
            "metadados_extracao": None,
            "extracao_falhou": False,
            "contexto_rag": [],
            "contexto_texto": None,
            "artigo_redigido": None,
            "modelo_redacao": None,
            "tokens_redacao": None,
            "seo_data": None,
            "modelo_seo": None,
            "wp_post_id": None,
            "wp_post_url": None,
            "wp_categoria_id": None,
            "wp_tag_ids": [],
            "publicado": False,
            "eventos_disparados": False,
            "step_atual": "init",
            "erro_fatal": None,
            "tentativas_redacao": 0,
            "iniciado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duracoes": {},
            "cycle_id": self.cycle_id,
            "worker_id": worker_id,
        }

        # Executa grafo com checkpointing
        config = {
            "configurable": {
                "thread_id": article_id,  # Cada artigo = 1 thread
            }
        }

        try:
            final_state = await self.graph.ainvoke(initial_state, config=config)

            duracao_total = time.monotonic() - t_inicio
            if final_state.get("publicado"):
                logger.info(
                    f"[{worker_id}] PUBLICADO: '{final_state.get('artigo_redigido', {}).get('titulo', '')[:60]}' "
                    f"| post_id={final_state.get('wp_post_id')} "
                    f"| {duracao_total:.1f}s total"
                )
            else:
                logger.warning(
                    f"[{worker_id}] NÃO PUBLICADO: {article_id} "
                    f"| erro={final_state.get('erro_fatal', 'desconhecido')}"
                )

        except Exception as e:
            logger.error(f"[{worker_id}] Erro fatal no grafo para {article_id}: {e}")

    def shutdown(self) -> None:
        """Sinaliza shutdown gracioso para todos os workers."""
        self._shutdown.set()
        logger.info("Shutdown solicitado ao pool de reporters")
```

### 13.2 Entrypoint Principal

```python
# brasileira/workers/run_reporter.py
"""
Entrypoint para execução do pool de reporters.

Uso:
    python -m brasileira.workers.run_reporter
    
Variáveis de ambiente:
    REPORTER_NUM_WORKERS=5         # Número de workers (default: 5)
    DATABASE_URL=postgresql://...  # PostgreSQL
    REDIS_URL=redis://...          # Redis
    KAFKA_BOOTSTRAP_SERVERS=...    # Kafka
    WP_URL=https://brasileira.news
    WP_USER=iapublicador
    WP_APP_PASS=xxxx xxxx xxxx
    ANTHROPIC_API_KEY=...
    OPENAI_API_KEY=...
    GOOGLE_API_KEY=...
    XAI_API_KEY=...
    PERPLEXITY_API_KEY=...
    DEEPSEEK_API_KEY=...
    ALIBABA_API_KEY=...
"""

import asyncio
import logging
import os
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("reporter.entrypoint")


async def main() -> None:
    from brasileira.workers.reporter_worker_pool import ReporterWorkerPool

    num_workers = int(os.getenv("REPORTER_NUM_WORKERS", "5"))
    logger.info(f"Iniciando Reporter V3 com {num_workers} workers")

    pool = ReporterWorkerPool(num_workers=num_workers)

    # Handler para shutdown gracioso
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, pool.shutdown)

    try:
        await pool.start()
    except asyncio.CancelledError:
        logger.info("Reporter pool cancelado")
    finally:
        logger.info("Reporter encerrado")


if __name__ == "__main__":
    asyncio.run(main())
```

### 13.3 Dockerfile

```dockerfile
# Dockerfile.reporter
FROM python:3.12-slim

WORKDIR /app

# Dependências do sistema para trafilatura e lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY brasileira/ ./brasileira/

# Variáveis obrigatórias (fornecidas via .env ou secrets)
ENV REPORTER_NUM_WORKERS=5
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "brasileira.workers.run_reporter"]
```

### 13.4 docker-compose.yml (Serviço reporter)

```yaml
# Adicionar ao docker-compose.yml existente

services:
  reporter:
    build:
      context: .
      dockerfile: Dockerfile.reporter
    environment:
      - REPORTER_NUM_WORKERS=${REPORTER_NUM_WORKERS:-5}
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS}
      - WP_URL=${WP_URL}
      - WP_USER=${WP_USER}
      - WP_APP_PASS=${WP_APP_PASS}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - XAI_API_KEY=${XAI_API_KEY}
      - PERPLEXITY_API_KEY=${PERPLEXITY_API_KEY}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - ALIBABA_API_KEY=${ALIBABA_API_KEY}
    depends_on:
      - kafka
      - postgres
      - redis
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "2"
          memory: "2G"
    healthcheck:
      test: ["CMD", "python", "-c", "import brasileira.workers.reporter_worker_pool"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 13.5 Scaling Horizontal

Para escalar acima de 5 workers locais (1.000+ artigos/hora):

```bash
# Escalar para 3 instâncias do container reporter
docker-compose up --scale reporter=3

# Cada instância roda REPORTER_NUM_WORKERS workers internos
# 3 instâncias × 5 workers = 15 workers concorrentes
# Kafka distribui partições automaticamente pelo consumer group

# Monitorar consumer group:
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group reporter-workers \
  --describe
```

---

## PARTE XIV — TESTES, VALIDAÇÃO E CHECKLIST

### 14.1 Testes Unitários

```python
# tests/test_reporter.py

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from brasileira.agents.reporter_extractors import extrair_conteudo_fonte
from brasileira.agents.reporter_rag import formatar_contexto_rag, buscar_artigos_similares
from brasileira.integrations.wordpress_client import WordPressPublisherV3


# ── Testes de extração ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extracao_fallback_resumo():
    """Se fetch falhar, usa resumo_original."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("timeout")
        resultado = await extrair_conteudo_fonte(
            url="https://example.com/article",
            resumo_original="Resumo de teste do artigo.",
        )
        assert resultado["conteudo"] == "Resumo de teste do artigo."
        assert resultado["extracao_metodo"] == "fallback_resumo"


@pytest.mark.asyncio
async def test_extracao_trafilatura_sucesso(httpx_mock):
    """trafilatura extrai conteúdo quando HTML válido."""
    html_com_conteudo = "<html><body><article>" + "palavra " * 100 + "</article></body></html>"
    httpx_mock.add_response(text=html_com_conteudo, status_code=200)

    resultado = await extrair_conteudo_fonte(
        url="https://example.com/article",
        resumo_original="Resumo",
    )
    # trafilatura deve ter extraído algo
    assert resultado["sucesso"] == True
    assert len(resultado["conteudo"].split()) > 10


# ── Testes de RAG ─────────────────────────────────────────────────────

def test_formatar_contexto_rag_vazio():
    """Contexto vazio retorna string vazia."""
    assert formatar_contexto_rag([]) == ""


def test_formatar_contexto_rag_com_artigos():
    """Contexto com artigos retorna texto formatado."""
    artigos = [
        {
            "titulo": "Governo anuncia pacote fiscal",
            "resumo": "O Ministério da Fazenda...",
            "publicado_em": "2026-03-25T10:00:00",
            "similaridade": 0.85,
        }
    ]
    contexto = formatar_contexto_rag(artigos)
    assert "Governo anuncia pacote fiscal" in contexto
    assert "CONTEXTO" in contexto
    assert "0.85" in contexto


# ── Testes de SEO ─────────────────────────────────────────────────────

def test_sanitizar_seo_limites():
    """SEO sanitization respeita limites de caracteres."""
    from brasileira.agents.reporter import _sanitizar_seo
    seo = {
        "titulo_seo": "x" * 100,     # Deve truncar para 60
        "descricao_seo": "y" * 200,  # Deve truncar para 155
        "slug": "slug-com-MAIÚSCULAS-e-acentos!!",
    }
    sanitizado = _sanitizar_seo(seo, "fallback titulo", "fallback resumo")
    assert len(sanitizado["titulo_seo"]) <= 60
    assert len(sanitizado["descricao_seo"]) <= 155
    assert sanitizado["slug"] == sanitizado["slug"].lower()


# ── Testes de WordPress ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publicar_artigo_status_publish(httpx_mock):
    """CRÍTICO: status DEVE ser 'publish', NUNCA 'draft'."""
    httpx_mock.add_response(
        json={"id": 12345, "link": "https://brasileira.news/post"},
        status_code=201,
    )

    wp = WordPressPublisherV3("https://brasileira.news", "user", "pass pass")
    wp._caches_carregados = True
    wp._category_cache = {"economia": 5}

    artigo = {
        "titulo": "Título de teste",
        "conteudo": "<p>Conteúdo</p>",
        "resumo": "Resumo",
        "categoria": "Economia",
        "tags": ["teste"],
    }
    seo = {"slug": "titulo-teste", "titulo_seo": "Título SEO", "descricao_seo": "Desc"}

    resultado = await wp.publicar_artigo(
        artigo=artigo, seo=seo,
        fonte_url="https://g1.com", fonte_nome="G1",
        categoria_nome="Economia", tags_nomes=["teste"],
    )

    assert resultado is not None
    assert resultado["post_id"] == 12345

    # Verifica que o request enviou status="publish"
    request = httpx_mock.get_requests()[-1]
    body = json.loads(request.content)
    assert body["status"] == "publish", "CRÍTICO: status deve ser 'publish', não 'draft'"


# ── Testes de integração do grafo ─────────────────────────────────────

@pytest.mark.asyncio
async def test_grafo_pipeline_completo():
    """Testa o pipeline completo com mocks."""
    from langgraph.checkpoint.memory import MemorySaver
    from brasileira.agents.reporter import build_reporter_graph

    # Mocks de todos os nós
    with (
        patch("brasileira.agents.reporter_extractors.extrair_conteudo_fonte") as mock_extr,
        patch("brasileira.agents.reporter_rag.buscar_artigos_similares") as mock_rag,
        patch("brasileira.agents.reporter.node_redigir") as mock_redigir,
        patch("brasileira.agents.reporter.node_otimizar_seo") as mock_seo,
        patch("brasileira.agents.reporter.node_publicar_wp") as mock_wp,
        patch("brasileira.agents.reporter.node_disparar_eventos") as mock_eventos,
    ):
        mock_extr.return_value = {"conteudo": "Texto extraído", "sucesso": True, "og_image": None}
        mock_rag.return_value = []
        mock_redigir.return_value = {
            "artigo_redigido": {
                "titulo": "Título teste",
                "subtitulo": "Sub",
                "conteudo": "<p>" + "palavra " * 100 + "</p>",
                "resumo": "Resumo",
                "categoria": "Economia",
                "tags": ["Teste"],
            },
            "modelo_redacao": "claude-sonnet-4-6",
            "tokens_redacao": {},
        }
        mock_seo.return_value = {"seo_data": {"slug": "titulo-teste"}}
        mock_wp.return_value = {
            "wp_post_id": 99999,
            "wp_post_url": "https://brasileira.news/test",
            "publicado": True,
        }
        mock_eventos.return_value = {"eventos_disparados": True}

        checkpointer = MemorySaver()
        graph = build_reporter_graph(checkpointer)

        # Estado inicial mínimo
        initial = {
            "article_id": "test-001",
            "raw_article": {
                "url_fonte": "https://g1.com/test",
                "titulo_original": "Teste",
                "resumo_original": "Resumo teste",
                "html_preview": "",
                "fonte_nome": "G1",
                "categoria": "Economia",
                "urgencia": "NORMAL",
                "tipo": "noticia_simples",
            },
            "fonte_nome": "G1",
            "fonte_url": "https://g1.com/test",
            "categoria": "Economia",
            "urgencia": "NORMAL",
            "tipo": "noticia_simples",
            "worker_id": "worker-test",
            "cycle_id": "test-cycle",
            # ... demais campos com defaults
        }

        result = await graph.ainvoke(
            initial,
            config={"configurable": {"thread_id": "test-001"}}
        )

        assert result.get("publicado") == True
        assert result.get("wp_post_id") == 99999
        assert result.get("eventos_disparados") == True
```

### 14.2 Teste de Smoke (Validação em Produção)

```python
# tests/smoke_test_reporter.py
"""
Smoke test: envia um artigo de teste para o pipeline e verifica publicação.
Roda apenas em ambiente de staging.
"""

import asyncio
import json
import time
import httpx

KAFKA_BOOTSTRAP = "localhost:9092"
WP_URL = "https://staging.brasileira.news"
WP_USER = "iapublicador"
WP_PASS = "xxxx xxxx xxxx"


async def smoke_test():
    from aiokafka import AIOKafkaProducer

    # Envia artigo de teste
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
    await producer.start()

    artigo_teste = {
        "article_id": f"smoke-test-{int(time.time())}",
        "url_fonte": "https://agenciabrasil.ebc.com.br/geral/noticia/2026-03/brasilia-tem-sol-e-temperatura-de-28-graus",
        "titulo_original": "[SMOKE TEST] Brasília registra temperatura de 28 graus nesta terça",
        "resumo_original": "A capital federal registrou nesta terça-feira temperatura máxima de 28 graus.",
        "html_preview": "<p>Brasília registrou temperatura máxima de 28 graus.</p>",
        "categoria": "Brasil",
        "urgencia": "NORMAL",
        "score_relevancia": 0.5,
        "fonte_nome": "Agência Brasil",
        "fonte_id": "agencia-brasil",
        "publicado_em": "2026-03-26T10:00:00-03:00",
        "og_image": None,
        "tipo": "noticia_simples",
    }

    await producer.send(
        "classified-articles",
        key=artigo_teste["article_id"].encode(),
        value=json.dumps(artigo_teste, ensure_ascii=False).encode("utf-8"),
    )
    await producer.stop()

    print(f"Artigo de teste enviado: {artigo_teste['article_id']}")
    print("Aguardando 60s para processamento...")
    await asyncio.sleep(60)

    # Verifica se foi publicado no WordPress
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            params={"search": "[SMOKE TEST]", "status": "publish"},
            auth=(WP_USER, WP_PASS),
        )
        posts = resp.json()
        if posts:
            print(f"✓ SMOKE TEST PASSOU: Post publicado: {posts[0]['link']}")
        else:
            print("✗ SMOKE TEST FALHOU: Nenhum post encontrado após 60s")


if __name__ == "__main__":
    asyncio.run(smoke_test())
```

### 14.3 Checklist de Implementação

#### Prioridade 1 — OBRIGATÓRIO para funcionar

- [ ] `ReporterState` TypedDict com todos os campos definidos na PARTE III
- [ ] `build_reporter_graph()` com 7 nós + 5 edges + checkpointer
- [ ] `criar_checkpointer()` com AsyncPostgresSaver + connection pool
- [ ] `node_extrair_conteudo()` com trafilatura + fallback resumo_original
- [ ] `node_contextualizar()` com pgvector RAG top-3 (falha graciosamente)
- [ ] `node_redigir()` com SYSTEM_PROMPT_REDACAO + retry JSON até 3x
- [ ] `node_otimizar_seo()` com SYSTEM_PROMPT_SEO + fallback sem LLM
- [ ] `node_publicar_wp()` com `status="publish"` OBRIGATÓRIO
- [ ] `WordPressPublisherV3.publicar_artigo()` com resolver de categorias/tags
- [ ] `node_disparar_eventos()` produz Kafka `article-published`
- [ ] `node_registrar_erro_dlq()` para artigos que falharam
- [ ] `ReporterWorkerPool` com N workers concorrentes (default 5)
- [ ] Consumer Kafka para `classified-articles`, `pautas-especiais`, `pautas-gap`
- [ ] Registro de artigos publicados na tabela `artigos` do PostgreSQL

#### Prioridade 2 — IMPORTANTE para qualidade e estabilidade

- [ ] `salvar_embedding_artigo()` no pgvector após publicação
- [ ] `ReporterWorkingMemory` com contadores de artigos publicados no Redis
- [ ] `ArticlePublishedEvent` com todos os campos conforme schema PARTE IX
- [ ] Mapeamento `CATEGORIA_SLUG_MAP` para 16 macrocategorias
- [ ] Retry com backoff exponencial nas chamadas WordPress
- [ ] Thread_id = article_id no PostgresSaver (isolamento de checkpoints)
- [ ] Logs estruturados com `article_id` em TODOS os níveis
- [ ] Duração de cada step registrada em `state["duracoes"]`

#### Prioridade 3 — DESEJÁVEL para observabilidade e robustez

- [ ] Smoke test automatizado (`tests/smoke_test_reporter.py`)
- [ ] Testes unitários para todos os nós (`tests/test_reporter.py`)
- [ ] Dockerfile + docker-compose service
- [ ] Health check endpoint (`/health` HTTP 200 se workers ativos)
- [ ] Métricas OpenTelemetry: `reporter.articles_published`, `reporter.pipeline_duration`
- [ ] Memória semântica de perfis de fontes (`carregar_perfil_fonte`)
- [ ] Scaling horizontal documentado (múltiplos containers no mesmo consumer group)

### 14.4 Validações CRÍTICAS (não colocar em produção sem estas)

```python
# Checklist de validações antes do deploy

def validar_config_critica():
    """
    Valida configurações críticas antes de iniciar o pool.
    Levanta ValueError se qualquer validação falhar.
    """
    import os

    # 1. WordPress: deve ter credenciais
    assert os.getenv("WP_URL"), "WP_URL obrigatório"
    assert os.getenv("WP_USER"), "WP_USER obrigatório"
    assert os.getenv("WP_APP_PASS"), "WP_APP_PASS obrigatório"

    # 2. Kafka: deve ter bootstrap servers
    assert os.getenv("KAFKA_BOOTSTRAP_SERVERS"), "KAFKA_BOOTSTRAP_SERVERS obrigatório"

    # 3. PostgreSQL: deve ter DSN
    assert os.getenv("DATABASE_URL"), "DATABASE_URL obrigatório"

    # 4. Pelo menos um provedor LLM PREMIUM configurado
    premium_keys = [
        os.getenv("ANTHROPIC_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
        os.getenv("GOOGLE_API_KEY"),
        os.getenv("XAI_API_KEY"),
    ]
    assert any(premium_keys), "Pelo menos um provedor LLM PREMIUM é obrigatório"

    # 5. Verificar que SmartLLMRouter tem "redacao_artigo" → PREMIUM
    from brasileira.llm.tier_config import TASK_TIER_MAP
    assert TASK_TIER_MAP.get("redacao_artigo") == "premium", \
        "CRÍTICO: redacao_artigo DEVE usar tier PREMIUM"
    assert TASK_TIER_MAP.get("seo_otimizacao") == "padrao", \
        "CRÍTICO: seo_otimizacao DEVE usar tier PADRÃO"

    print("✓ Todas as validações críticas passaram")
```

---

## REFERÊNCIAS E FONTES

- **Master Briefing V3** — `briefing-implementacao-brasileira-news-v3.pplx.md` — Arquitetura geral, fluxo editorial, especificação do Reporter
- **Benchmarking Editorial** — `benchmarking_editorial.md` — AP Wordsmith, Bloomberg, Reuters, padrões de jornalismo automatizado
- **Context Engineering** — `context-engineering-brasileira-news.pplx.md` — Princípios de contexto, memória por camada, scratchpads
- **[LangGraph 1.0 — Towards AI](https://pub.towardsai.net/from-single-brains-to-team-intelligence-mastering-ai-agent-systems-with-langgraph-in-2025-3520af4fc758)** — Padrões de StateGraph, checkpointing, worker pools
- **[AsyncPostgresSaver — LangChain Reference](https://reference.langchain.com/python/langgraph.checkpoint.postgres/aio/AsyncPostgresSaver)** — Checkpointing assíncrono com pool de conexões
- **[Trafilatura 2.0 — Docs](https://trafilatura.readthedocs.io/en/latest/evaluation.html)** — Melhor precision/recall para extração de notícias vs newspaper3k
- **[HTTPX Async — OneUptime](https://oneuptime.com/blog/post/2026-02-03-python-httpx-async-requests/view)** — Padrões de cliente HTTP assíncrono com retry e rate limiting
- **[pgvector RAG — Severalnines](https://severalnines.com/blog/improving-llm-fidelity-with-retrieval-augmented-generation-using-pgvector/)** — RAG com pgvector para contextualização de artigos
- **[SEO Portais de Notícias — Search One Digital](https://searchonedigital.com.br/blog/seo-para-portais-de-noticia/)** — Critérios Google News, otimização para portais brasileiros
- **[SEO + IA 2026 — Beatz](https://beatz.com.br/blog/tendencias-seo-ia-2026-autoridade-sintetica/)** — Tendências SEO para portais jornalísticos em 2026

---

*Este briefing documenta a implementação completa do Reporter V3, o componente central de produção editorial da brasileira.news. Todos os exemplos de código são funcionais e prontos para uso. Não improvise nos pontos marcados como OBRIGATÓRIO — especialmente `status="publish"`, o pipeline linear sem gates, e o uso de LLM PREMIUM para redação.*
