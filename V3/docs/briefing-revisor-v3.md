# Briefing Completo para IA — Revisor V3 (QA Pós-Publicação)

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #6
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / LangGraph / Kafka / Redis / PostgreSQL+pgvector / WordPress REST API / LiteLLM
**Componente:** `brasileira/agents/revisor/` — Revisor (QA Pós-Publicação)

---

## LEIA ISTO PRIMEIRO — A Mudança de Paradigma

O Revisor V3 é **completamente diferente** do Revisor V2. Não é uma evolução — é uma inversão de papel.

**V2 (ERRADO):** Gate pré-publicação. Avalia drafts. Pode REJEITAR. Bloqueia o pipeline. Opera antes da publicação. Usa LLM PREMIUM. Tem decisões de APPROVE/REVISE/REJECT.

**V3 (CORRETO):** QA pós-publicação. Consome evento `article_published`. Opera sobre posts JÁ PUBLICADOS. Corrige in-place via PATCH no WordPress. NUNCA rejeita. NUNCA despublica. NUNCA bloqueia. Usa LLM PADRÃO.

A distinção é **inviolável e filosófica**: o sistema da brasileira.news V3 segue a doutrina "publicar primeiro, corrigir depois". O artigo já está no ar quando o Revisor começa a trabalhar. Seu papel é melhorar a qualidade sem interromper o fluxo editorial.

```
FLUXO V3 CORRETO:

Reporter → Publica WordPress → Kafka: article_published
                                         │
                              ┌──────────┴──────────┐
                              ↓                     ↓
                         Fotógrafo              REVISOR
                      (busca imagem)        (QA pós-publicação)
                              │                     │
                              ↓                     ↓
                      PATCH WordPress         PATCH WordPress
                      (featured_media)        (título, conteúdo,
                                               excerpt, meta SEO)
```

**Este briefing contém TUDO que você precisa para implementar o Revisor V3 do zero.** Não consulte outros documentos. Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ QUEBRADO NA V2

### 1.1 Problema Central: Gate Pré-Publicação

O `revisor-20.py` da V2 é um **gatekeeper**, não um corrector. Está posicionado ANTES da publicação e pode REJEITAR artigos, impedindo que qualquer coisa seja publicada.

**Arquivo V2:** `revisor-20.py` (1.372 linhas)

**Problemas fatais, linha por linha:**

**PROBLEMA 1: Decisão REJECT (linha 47-51)**
```python
class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"   # ← PROIBIDO NA V3. Não existe mais.
```
O Revisor V2 pode REJEITAR um artigo. Na V3, esta opção não existe. O artigo já está publicado — rejeitá-lo agora seria despublicá-lo, o que viola a regra #11.

**PROBLEMA 2: Opera sobre Draft (linha 86-99)**
```python
class RevisorState(AgentState):
    article_draft: Optional[Dict[str, Any]] = None  # ← draft, não post publicado
    validation_results: Dict[str, Any] = Field(default_factory=dict)
    ...
```
O state recebe um `article_draft` — um artigo que ainda não foi publicado. Na V3, o Revisor recebe um `post_id` do Kafka e busca o post JÁ PUBLICADO via GET no WordPress.

**PROBLEMA 3: Thresholds de bloqueio (linha 217-218)**
```python
APPROVE_THRESHOLD = 5.5   # abaixo disso → pode REJEITAR
REVISE_THRESHOLD = 3.5    # abaixo disso → REJEITA definitivamente
```
Estes thresholds determinam REJECT. Na V3 não há threshold de bloqueio. O Revisor SEMPRE corrige e SEMPRE finaliza sem rejeitar.

**PROBLEMA 4: LLM PREMIUM para revisão de texto (linha 1083-1090)**
```python
response = await self.llm.acomplete(
    prompt=prompt,
    task_type="quality_review",   # ← roteado para PREMIUM na V2
    system_prompt=self.get_system_prompt(),
    ...
)
```
A V2 usa LLM PREMIUM para revisão textual. Na V3, revisão de texto é tier PADRÃO. PREMIUM é reservado para redação, imagem query e homepage scoring.

**PROBLEMA 5: Não faz PATCH no WordPress (inexistente no V2)**
O Revisor V2 não tem nenhum código de atualização do WordPress. Ele avalia o draft e devolve uma decisão — mas nunca aplica correções diretamente no post publicado. Na V3, o PATCH é a ação central.

**PROBLEMA 6: Não consome Kafka (inexistente no V2)**
O Revisor V2 é acionado de forma síncrona no pipeline. Na V3, ele é um consumidor Kafka independente que opera em paralelo com o Fotógrafo.

**PROBLEMA 7: Sem memória episódica real (linha 266-277)**
```python
def get_system_prompt(self) -> str:
    return """Você é um Editor-Revisor experiente da Brasileira News..."""
```
O system prompt é estático. Não usa memória de revisões anteriores para melhorar padrões, não aprende quais tipos de erro são mais frequentes por editoria.

### 1.2 Mapeamento Completo V2 → V3

| Aspecto | V2 (ERRADO) | V3 (CORRETO) |
|---------|-------------|--------------|
| Momento de operação | PRÉ-publicação | PÓS-publicação |
| Input | `article_draft` (dict) | `post_id` via Kafka |
| Acionamento | Síncrono no pipeline | Consumidor Kafka async |
| Paralelismo | Bloqueante | Paralelo com Fotógrafo |
| Decisões | APPROVE / REVISE / REJECT | Sem decisão — sempre corrige |
| Pode rejeitar? | SIM | NÃO — NUNCA |
| Pode despublicar? | SIM (implícito no REJECT) | NÃO — NUNCA |
| Saída | `ReviewResult` (decisão) | PATCH WordPress aplicado |
| LLM tier | PREMIUM | PADRÃO |
| WordPress | Sem interação | GET (carregar) + PATCH (corrigir) |
| Kafka | Não consome | Consome `article-published` |
| Memória | Hooks sem uso real | Semântica + episódica + working |

### 1.3 Consequências dos Bugs V2

A configuração errada do Revisor V2 foi **um dos principais motivos de 0 artigos publicados** no sistema:

1. Reporter gerava um draft
2. Draft ia para Revisor (gate)
3. Revisor avaliava e decidia REVISE (score entre 3.5 e 5.5)
4. Artigo voltava para Reporter para reescrita
5. Loop poderia se repetir até REJECT
6. Resultado: nada publicado

Na V3, este loop não existe. O Reporter publica direto. O Revisor melhora o que já está publicado.

---

## PARTE II — ARQUITETURA V3

### 2.1 Visão Geral do Componente

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    REVISOR V3 — QA PÓS-PUBLICAÇÃO                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Kafka Consumer                                                          │
│  ─────────────                                                           │
│  Tópico: article-published                                               │
│  Group ID: revisor-consumers                                             │
│  (mesmo tópico que Fotógrafo — em PARALELO)                              │
│                                                                          │
│  ↓ evento: {post_id, titulo, editoria, url, ...}                        │
│                                                                          │
│  LangGraph StateGraph                                                    │
│  ────────────────────                                                    │
│  [carregar_post] → [revisar_gramatica] → [revisar_estilo]               │
│       ↓                    ↓                     ↓                       │
│  GET /wp/v2/posts/{id}  LLM PADRÃO           LLM PADRÃO                 │
│                                                                          │
│  → [verificar_fatos] → [revisar_seo] → [aplicar_correcoes]             │
│         ↓                   ↓                   ↓                       │
│    Regras básicas       LLM PADRÃO        PATCH /wp/v2/posts/{id}       │
│                                                                          │
│  → [registrar_revisao]                                                   │
│         ↓                                                                │
│    PostgreSQL + Redis + pgvector                                         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Princípios Arquiteturais

**Princípio 1: Sempre completa, nunca bloqueia**
O pipeline do Revisor deve sempre terminar com `aplicar_correcoes`. Mesmo que todas as verificações encontrem zero problemas, o nó `aplicar_correcoes` é chamado (pode resultar em zero mudanças). Nunca retorna erro que interrompa o fluxo.

**Princípio 2: Correção mínima necessária**
O Revisor não reescreve artigos. Faz correções pontuais: erros gramaticais, termos de estilo, metadados SEO ausentes. Preserva a voz e o conteúdo original do Reporter.

**Princípio 3: LLM PADRÃO, não PREMIUM**
Revisão gramatical e ajuste de estilo não exigem capacidade criativa premium. Modelos PADRÃO como GPT-4.1-mini, Gemini 2.5 Flash e Claude Haiku têm mais que capacidade suficiente para identificar e corrigir erros textuais em português.

**Princípio 4: Paralelismo com Fotógrafo**
Ambos consomem o tópico `article-published` com group IDs diferentes. Não há comunicação entre eles. Podem executar simultaneamente sobre o mesmo post. O WordPress REST API suporta múltiplas atualizações sequenciais em campos distintos.

**Princípio 5: Idempotência**
Se o Revisor falhar no meio e for re-executado sobre o mesmo `post_id`, o resultado deve ser o mesmo. As correções são determinísticas (mesma entrada → mesma saída com o mesmo LLM e mesma temperatura baixa).

### 2.3 Estrutura de Arquivos

```
brasileira/
└── agents/
    └── revisor/
        ├── __init__.py
        ├── agent.py          # RevisorAgent — classe principal
        ├── state.py          # RevisorState — Pydantic model
        ├── nodes.py          # Nós do LangGraph
        ├── prompts.py        # System prompts e templates de revisão
        ├── wp_client.py      # Cliente WordPress (GET + PATCH)
        ├── kafka_consumer.py # Consumidor Kafka + orquestrador
        ├── memory.py         # Memória semântica, episódica, working
        └── schemas.py        # Schemas Kafka + PostgreSQL models
```

### 2.4 Dependências

```toml
# pyproject.toml — dependências do Revisor
[tool.poetry.dependencies]
langgraph = ">=0.3.0"
langchain-core = ">=0.3.0"
aiokafka = ">=0.11.0"
aiohttp = ">=3.9.0"
pydantic = ">=2.0.0"
asyncpg = ">=0.29.0"
redis = {extras = ["hiredis"], version = ">=5.0.0"}
pgvector = ">=0.3.0"
beautifulsoup4 = ">=4.12.0"
lxml = ">=5.0.0"
```

---

## PARTE III — LANGGRAPH STATEGRAPH

### 3.1 State Definition

```python
# brasileira/agents/revisor/state.py

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class CorrecaoTipo(str, Enum):
    """Tipo de correção aplicada."""
    GRAMATICA = "gramatica"
    ORTOGRAFIA = "ortografia"
    ESTILO = "estilo"
    SEO_TITULO = "seo_titulo"
    SEO_EXCERPT = "seo_excerpt"
    SEO_META = "seo_meta"
    FATO_DATA = "fato_data"
    FATO_NUMERO = "fato_numero"
    PONTUACAO = "pontuacao"
    CONSISTENCIA = "consistencia"


class Correcao(BaseModel):
    """Uma correção individual aplicada ao post."""
    tipo: CorrecaoTipo
    campo: str                    # "titulo", "content", "excerpt", "meta.yoast_wpseo_title"
    original: str                 # Texto original
    corrigido: str                # Texto corrigido
    justificativa: str            # Por que foi corrigido
    posicao_inicio: Optional[int] = None   # Posição no texto (se aplicável)
    posicao_fim: Optional[int] = None


class PostCarregado(BaseModel):
    """Post WordPress carregado via GET."""
    post_id: int
    titulo: str
    conteudo_html: str
    excerpt: str
    slug: str
    status: str
    editoria: str
    tags: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    link: str = ""
    data_publicacao: str = ""
    fonte_original: str = ""


class RevisorState(BaseModel):
    """Estado completo do pipeline de revisão."""
    # Identificação
    session_id: str = ""
    agent_id: str = "revisor-01"

    # Input do Kafka
    post_id: int = 0
    event_data: Dict[str, Any] = Field(default_factory=dict)
    editoria: str = ""

    # Post carregado do WordPress
    post: Optional[PostCarregado] = None

    # Resultados de cada nó de revisão
    correcoes_gramatica: List[Correcao] = Field(default_factory=list)
    correcoes_estilo: List[Correcao] = Field(default_factory=list)
    correcoes_fatos: List[Correcao] = Field(default_factory=list)
    correcoes_seo: List[Correcao] = Field(default_factory=list)

    # Todas as correções consolidadas
    todas_correcoes: List[Correcao] = Field(default_factory=list)

    # Payload final para PATCH
    patch_payload: Dict[str, Any] = Field(default_factory=dict)

    # Resultado da aplicação
    patch_aplicado: bool = False
    patch_response: Dict[str, Any] = Field(default_factory=dict)

    # Métricas de custo LLM
    llm_calls: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_custo_usd: float = 0.0

    # Controle de erros
    erros: List[Dict[str, Any]] = Field(default_factory=list)
    sucesso: bool = True

    # Working memory
    contexto_edicoes_anteriores: List[Dict] = Field(default_factory=list)
    padroes_erro_editoria: Dict[str, int] = Field(default_factory=dict)

    # Timestamps
    iniciado_em: Optional[datetime] = None
    concluido_em: Optional[datetime] = None

    model_config = {"arbitrary_types_allowed": True}

    def adicionar_erro(self, etapa: str, erro: Exception, fatal: bool = False):
        self.erros.append({
            "etapa": etapa,
            "tipo": type(erro).__name__,
            "mensagem": str(erro),
            "timestamp": datetime.utcnow().isoformat(),
            "fatal": fatal,
        })
        if fatal:
            self.sucesso = False

    def adicionar_custo(self, tokens_in: int, tokens_out: int, custo: float):
        self.llm_calls += 1
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out
        self.total_custo_usd += custo

    def consolidar_correcoes(self):
        """Une todas as listas de correções em uma única lista ordenada."""
        self.todas_correcoes = (
            self.correcoes_gramatica
            + self.correcoes_estilo
            + self.correcoes_fatos
            + self.correcoes_seo
        )
```

### 3.2 Grafo LangGraph Completo

```python
# brasileira/agents/revisor/agent.py

from langgraph.graph import StateGraph, END
from .state import RevisorState
from .nodes import (
    node_carregar_post,
    node_revisar_gramatica,
    node_revisar_estilo,
    node_verificar_fatos,
    node_revisar_seo,
    node_aplicar_correcoes,
    node_registrar_revisao,
)


def build_revisor_graph() -> StateGraph:
    """
    Constrói o StateGraph do Revisor V3.

    Fluxo LINEAR — sem branches, sem loops, sem rejeições:
    carregar_post → revisar_gramatica → revisar_estilo
                 → verificar_fatos → revisar_seo
                 → aplicar_correcoes → registrar_revisao → END

    INVIOLÁVEL: Nenhum nó pode retornar sem avançar para o próximo.
    INVIOLÁVEL: Nenhum nó pode cancelar ou despublicar o post.
    INVIOLÁVEL: aplicar_correcoes SEMPRE executa (mesmo com zero correções).
    """
    builder = StateGraph(RevisorState)

    # Adicionar nós
    builder.add_node("carregar_post", node_carregar_post)
    builder.add_node("revisar_gramatica", node_revisar_gramatica)
    builder.add_node("revisar_estilo", node_revisar_estilo)
    builder.add_node("verificar_fatos", node_verificar_fatos)
    builder.add_node("revisar_seo", node_revisar_seo)
    builder.add_node("aplicar_correcoes", node_aplicar_correcoes)
    builder.add_node("registrar_revisao", node_registrar_revisao)

    # Definir fluxo — LINEAR, sem condicionais
    builder.set_entry_point("carregar_post")
    builder.add_edge("carregar_post", "revisar_gramatica")
    builder.add_edge("revisar_gramatica", "revisar_estilo")
    builder.add_edge("revisar_estilo", "verificar_fatos")
    builder.add_edge("verificar_fatos", "revisar_seo")
    builder.add_edge("revisar_seo", "aplicar_correcoes")
    builder.add_edge("aplicar_correcoes", "registrar_revisao")
    builder.add_edge("registrar_revisao", END)

    return builder.compile()


# Instância global compilada
REVISOR_GRAPH = build_revisor_graph()
```

### 3.3 Diagrama de Fluxo de Estados

```
Estado Inicial: RevisorState(post_id=12345, event_data={...})
      │
      ▼
[carregar_post]
  GET /wp-json/wp/v2/posts/12345
  → state.post = PostCarregado(titulo, conteudo_html, excerpt, meta, ...)
  → state.editoria = "politica"
      │
      ▼
[revisar_gramatica]
  LLM PADRÃO: analisa state.post.conteudo_html + titulo
  → state.correcoes_gramatica = [Correcao(...), ...]
  → state.adicionar_custo(...)
      │
      ▼
[revisar_estilo]
  LLM PADRÃO: verifica manual de estilo + coerência jornalística
  → state.correcoes_estilo = [Correcao(...), ...]
      │
      ▼
[verificar_fatos]
  Regras determinísticas: datas, números, consistência interna
  (SEM LLM — verificações de padrão com regex + lógica)
  → state.correcoes_fatos = [Correcao(...), ...]
      │
      ▼
[revisar_seo]
  LLM PADRÃO: otimiza título SEO, excerpt, meta description
  → state.correcoes_seo = [Correcao(...), ...]
      │
      ▼
[aplicar_correcoes]
  state.consolidar_correcoes()
  Monta patch_payload com todas as correções
  PATCH /wp-json/wp/v2/posts/12345
  → state.patch_aplicado = True
  → state.patch_response = {id: 12345, modified: "..."}
      │
      ▼
[registrar_revisao]
  PostgreSQL: INSERT INTO revisoes_realizadas
  Redis: cache de correções aplicadas
  pgvector: embedding da revisão para memória semântica
      │
      ▼
     END
```

---

## PARTE IV — CARREGAMENTO DO POST (GET WORDPRESS)

### 4.1 Cliente WordPress Assíncrono

```python
# brasileira/agents/revisor/wp_client.py

import aiohttp
import asyncio
import base64
import json
import logging
from typing import Any, Dict, Optional
from .state import PostCarregado

logger = logging.getLogger(__name__)


class WordPressClient:
    """
    Cliente assíncrono para WordPress REST API.
    Operações: GET (carregar post) + PATCH (aplicar correções).

    INVIOLÁVEL: O método patch_post NUNCA altera status do post.
    INVIOLÁVEL: O método patch_post NUNCA define status="draft" ou status="trash".
    """

    def __init__(
        self,
        wp_url: str,
        wp_user: str,
        wp_password: str,
        timeout_segundos: int = 30,
        max_retries: int = 3,
    ):
        self.base_url = wp_url.rstrip("/")
        self.api_base = f"{self.base_url}/wp-json/wp/v2"
        self.timeout = aiohttp.ClientTimeout(total=timeout_segundos)
        self.max_retries = max_retries

        # Autenticação Application Password
        credentials = f"{wp_user}:{wp_password}"
        token = base64.b64encode(credentials.encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get_post(self, post_id: int) -> PostCarregado:
        """
        Carrega um post do WordPress via GET.
        Inclui campos padrão + meta fields do Yoast SEO.

        Args:
            post_id: ID do post WordPress

        Returns:
            PostCarregado com todos os campos relevantes para revisão
        """
        url = f"{self.api_base}/posts/{post_id}"
        params = {
            "_fields": "id,title,content,excerpt,slug,status,categories,tags,"
                       "meta,link,date,modified",
            "context": "edit",  # Importante: retorna conteúdo sem filtros
        }

        for tentativa in range(self.max_retries):
            try:
                async with aiohttp.ClientSession(
                    headers=self.headers,
                    timeout=self.timeout
                ) as session:
                    async with session.get(url, params=params) as response:
                        if response.status == 404:
                            raise ValueError(f"Post {post_id} não encontrado no WordPress")
                        if response.status != 200:
                            texto = await response.text()
                            raise RuntimeError(
                                f"WordPress GET falhou: HTTP {response.status} — {texto[:200]}"
                            )
                        data = await response.json()

                return self._parse_post(data)

            except aiohttp.ClientError as e:
                if tentativa == self.max_retries - 1:
                    raise RuntimeError(f"Falha ao carregar post {post_id} após {self.max_retries} tentativas: {e}")
                await asyncio.sleep(2 ** tentativa)  # Backoff exponencial

    def _parse_post(self, data: Dict[str, Any]) -> PostCarregado:
        """Converte resposta da API WordPress para PostCarregado."""
        # Título: a API retorna {"rendered": "...", "raw": "..."}
        titulo = data.get("title", {})
        if isinstance(titulo, dict):
            titulo = titulo.get("raw") or titulo.get("rendered", "")

        # Conteúdo HTML
        conteudo = data.get("content", {})
        if isinstance(conteudo, dict):
            conteudo = conteudo.get("raw") or conteudo.get("rendered", "")

        # Excerpt / resumo
        excerpt = data.get("excerpt", {})
        if isinstance(excerpt, dict):
            excerpt = excerpt.get("raw") or excerpt.get("rendered", "")

        # Meta fields (Yoast, ACF, etc.)
        meta = data.get("meta", {}) or {}

        # Extrair fonte original dos meta fields
        fonte_original = (
            meta.get("fonte_original")
            or meta.get("_yoast_wpseo_canonical")
            or ""
        )

        return PostCarregado(
            post_id=data.get("id", 0),
            titulo=titulo,
            conteudo_html=conteudo,
            excerpt=excerpt,
            slug=data.get("slug", ""),
            status=data.get("status", "publish"),
            editoria=self._extrair_editoria(data),
            tags=[str(t) for t in data.get("tags", [])],
            meta=meta,
            link=data.get("link", ""),
            data_publicacao=data.get("date", ""),
            fonte_original=fonte_original,
        )

    def _extrair_editoria(self, data: Dict[str, Any]) -> str:
        """Extrai editoria dos metadados ou categorias."""
        meta = data.get("meta", {}) or {}
        editoria = meta.get("editoria", "")
        if editoria:
            return editoria
        # Fallback: primeira categoria como string
        categorias = data.get("categories", [])
        if categorias:
            return str(categorias[0])
        return "geral"

    async def patch_post(self, post_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aplica correções em um post publicado via PATCH (POST com ID no WordPress REST API).

        INVIOLÁVEL: payload NUNCA deve conter "status" — não alterar status do post.
        INVIOLÁVEL: payload NUNCA deve conter "date" — não alterar data de publicação.

        Args:
            post_id: ID do post WordPress
            payload: Campos a serem atualizados (título, conteúdo, excerpt, meta)

        Returns:
            Resposta da API com o post atualizado
        """
        # Garantia de segurança: remover campos proibidos
        payload_seguro = {k: v for k, v in payload.items()
                         if k not in ("status", "date", "date_gmt", "author")}

        if not payload_seguro:
            logger.info(f"Post {post_id}: nenhuma correção para aplicar")
            return {"id": post_id, "modified": "sem_alteracoes"}

        url = f"{self.api_base}/posts/{post_id}"

        for tentativa in range(self.max_retries):
            try:
                async with aiohttp.ClientSession(
                    headers=self.headers,
                    timeout=self.timeout
                ) as session:
                    # WordPress REST API usa POST com ID para atualizar (não PATCH puro)
                    async with session.post(url, json=payload_seguro) as response:
                        if response.status not in (200, 201):
                            texto = await response.text()
                            raise RuntimeError(
                                f"WordPress PATCH falhou: HTTP {response.status} — {texto[:300]}"
                            )
                        return await response.json()

            except aiohttp.ClientError as e:
                if tentativa == self.max_retries - 1:
                    raise RuntimeError(f"Falha ao aplicar PATCH no post {post_id}: {e}")
                await asyncio.sleep(2 ** tentativa)

        return {}  # Nunca alcançado, mas satisfaz o type checker
```

### 4.2 Nó carregar_post

```python
# Em brasileira/agents/revisor/nodes.py

import logging
from .state import RevisorState
from .wp_client import WordPressClient
from brasileira.config import get_settings

logger = logging.getLogger(__name__)


async def node_carregar_post(state: RevisorState) -> RevisorState:
    """
    Nó 1: Carrega o post JÁ PUBLICADO do WordPress.

    Input:  state.post_id (vindo do evento Kafka)
    Output: state.post (PostCarregado com todo o conteúdo)

    Em caso de falha: registra o erro mas continua sem post
    (os nós seguintes lidarão com state.post == None graciosamente).
    """
    settings = get_settings()
    client = WordPressClient(
        wp_url=settings.WP_URL,
        wp_user=settings.WP_USER,
        wp_password=settings.WP_PASSWORD,
    )

    try:
        logger.info(f"[Revisor] Carregando post {state.post_id} do WordPress...")
        post = await client.get_post(state.post_id)
        logger.info(f"[Revisor] Post carregado: '{post.titulo[:60]}...' ({len(post.conteudo_html)} chars)")
        state.post = post
        state.editoria = post.editoria

    except ValueError as e:
        # Post não encontrado — possível race condition com Fotógrafo
        logger.warning(f"[Revisor] Post {state.post_id} não encontrado: {e}")
        state.adicionar_erro("carregar_post", e, fatal=True)

    except RuntimeError as e:
        logger.error(f"[Revisor] Erro ao carregar post {state.post_id}: {e}")
        state.adicionar_erro("carregar_post", e, fatal=False)
        # Tenta novamente com delay — post pode estar sendo processado
        import asyncio
        await asyncio.sleep(5)
        try:
            post = await client.get_post(state.post_id)
            state.post = post
            state.editoria = post.editoria
        except Exception as e2:
            state.adicionar_erro("carregar_post_retry", e2, fatal=True)

    return state
```

### 4.3 Campos Extraídos do WordPress para Revisão

| Campo WordPress | Campo em PostCarregado | Usado para |
|----------------|----------------------|------------|
| `title.raw` | `titulo` | Revisão gramática, SEO |
| `content.raw` | `conteudo_html` | Revisão gramática, estilo, fatos |
| `excerpt.raw` | `excerpt` | Revisão SEO (meta description) |
| `meta._yoast_wpseo_title` | `meta["_yoast_wpseo_title"]` | SEO título |
| `meta._yoast_wpseo_metadesc` | `meta["_yoast_wpseo_metadesc"]` | SEO description |
| `meta.fonte_original` | `fonte_original` | Verificação de atribuição |
| `meta.editoria` | `editoria` | Contexto de estilo por editoria |

---

## PARTE V — REVISÃO GRAMATICAL E ORTOGRÁFICA

### 5.1 System Prompt — Gramática e Ortografia

```python
# brasileira/agents/revisor/prompts.py

SYSTEM_PROMPT_REVISOR = """Você é o Revisor Gramatical da brasileira.news, um portal de jornalismo brasileiro de tier 1.

SEU PAPEL:
- Identificar e corrigir erros gramaticais, ortográficos e de pontuação no texto
- Corrigir sem alterar o sentido, a voz ou o estilo do jornalista
- Preservar termos técnicos, nomes próprios e siglas
- Manter o tom jornalístico objetivo e factual original

REGRAS DO PORTAL (Manual de Estilo brasileira.news):
- Língua portuguesa brasileira padrão culta (não lusitana)
- Números de 1 a 9 por extenso; 10 em diante em algarismos
- Porcentagem: "5%" (não "5 por cento" no texto corrido)
- Datas: "26 de março de 2026" (não "26/03/2026" no corpo do texto)
- Horas: "12h30" ou "às 12 horas e 30 minutos"
- Siglas conhecidas sem pontos: STF, PT, IBGE, PIB (não S.T.F.)
- Aspas duplas para citações diretas, simples para termos
- Sem ponto final em títulos
- Lide nas primeiras 2-3 frases: responde O quê, Quem, Quando, Onde, Por quê
- Crédito à fonte OBRIGATÓRIO

O QUE VOCÊ PODE CORRIGIR:
✓ Erros de concordância verbal e nominal
✓ Regência verbal e nominal incorreta
✓ Ortografia incorreta (acento, grafia)
✓ Pontuação errada (vírgulas, pontos, ponto e vírgula)
✓ Crase incorreta ou omitida
✓ Uso incorreto de pronomes
✓ Formatação de números, datas e horas fora do padrão
✓ Uso de voz passiva excessiva (sugerir voz ativa)

O QUE VOCÊ NÃO PODE FAZER:
✗ Alterar fatos, dados ou informações
✗ Mudar o ângulo editorial da matéria
✗ Adicionar ou remover parágrafos inteiros
✗ Substituir palavras por sinônimos desnecessariamente
✗ Reescrever frases completamente quando a correção é pontual
✗ Alterar nomes próprios, siglas ou termos técnicos

FORMATO DE SAÍDA:
Retorne APENAS JSON válido com a estrutura especificada.
"""

PROMPT_REVISAO_GRAMATICAL = """Revise o texto jornalístico abaixo identificando erros gramaticais, ortográficos e de pontuação.

TÍTULO:
{titulo}

CONTEÚDO HTML:
{conteudo}

EDITORIA: {editoria}

INSTRUÇÕES:
1. Analise o título e o conteúdo HTML
2. Identifique APENAS correções necessárias (não sugestões de melhoria estilística)
3. Para cada correção, forneça o trecho EXATO original e o trecho corrigido
4. Limite de 20 correções por chamada (priorize as mais graves)
5. Preserve toda a marcação HTML — corrija apenas o texto dentro das tags

Retorne APENAS JSON válido:
{{
    "correcoes": [
        {{
            "tipo": "gramatica|ortografia|pontuacao|concordancia|crase",
            "campo": "titulo|content",
            "original": "texto original exato com contexto suficiente (min 10 chars)",
            "corrigido": "texto corrigido",
            "justificativa": "explicação da correção em português"
        }}
    ],
    "resumo": "síntese breve dos tipos de erros encontrados",
    "total_erros_encontrados": 0
}}

Se não houver erros, retorne {{"correcoes": [], "resumo": "Texto sem erros gramaticais detectados", "total_erros_encontrados": 0}}
"""
```

### 5.2 Nó revisar_gramatica

```python
async def node_revisar_gramatica(state: RevisorState) -> RevisorState:
    """
    Nó 2: Revisão gramatical e ortográfica via LLM PADRÃO.

    Se state.post is None (falha no carregamento), retorna sem fazer nada.
    NUNCA levanta exceção — erros são logados em state.erros.
    """
    if not state.post:
        logger.warning("[Revisor] Sem post carregado — pulando revisão gramatical")
        return state

    from brasileira.llm.smart_router import SmartLLMRouter, LLMTier
    from .prompts import SYSTEM_PROMPT_REVISOR, PROMPT_REVISAO_GRAMATICAL

    router = SmartLLMRouter()

    # Limitar tamanho do conteúdo para o LLM (evitar exceder context window)
    conteudo_truncado = state.post.conteudo_html[:8000]

    prompt = PROMPT_REVISAO_GRAMATICAL.format(
        titulo=state.post.titulo,
        conteudo=conteudo_truncado,
        editoria=state.editoria,
    )

    try:
        response = await router.complete(
            system_prompt=SYSTEM_PROMPT_REVISOR,
            user_prompt=prompt,
            tier=LLMTier.PADRAO,           # PADRÃO — não PREMIUM
            task_type="revisao_texto",
            temperature=0.1,               # Baixa temperatura — determinístico
            max_tokens=2048,
        )

        # Parsear resposta JSON
        import json, re
        content = response.content.strip()
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            raise ValueError("LLM não retornou JSON válido para revisão gramatical")

        data = json.loads(json_match.group())
        correcoes_raw = data.get("correcoes", [])

        # Converter para objetos Correcao
        from .state import Correcao, CorrecaoTipo
        correcoes = []
        for c in correcoes_raw:
            tipo_str = c.get("tipo", "gramatica")
            try:
                tipo = CorrecaoTipo(tipo_str)
            except ValueError:
                tipo = CorrecaoTipo.GRAMATICA

            correcoes.append(Correcao(
                tipo=tipo,
                campo=c.get("campo", "content"),
                original=c.get("original", ""),
                corrigido=c.get("corrigido", ""),
                justificativa=c.get("justificativa", ""),
            ))

        state.correcoes_gramatica = correcoes
        state.adicionar_custo(
            tokens_in=response.usage.prompt_tokens,
            tokens_out=response.usage.completion_tokens,
            custo=response.usage.cost_usd,
        )

        logger.info(f"[Revisor] Gramática: {len(correcoes)} correções encontradas")

    except Exception as e:
        logger.error(f"[Revisor] Erro na revisão gramatical: {e}")
        state.adicionar_erro("revisar_gramatica", e, fatal=False)
        # Continua sem correções gramaticais — não bloqueia o pipeline

    return state
```

### 5.3 Aplicação das Correções Textuais

As correções gramaticais são aplicadas por substituição de string no HTML, com cuidado para não quebrar tags:

```python
def aplicar_substituicoes_html(html: str, correcoes: List[Correcao]) -> str:
    """
    Aplica substituições de texto em HTML preservando as tags.

    Estratégia: substitui apenas o primeiro match do texto original
    para evitar correções indevidas em múltiplas ocorrências.
    """
    texto_atual = html
    for correcao in correcoes:
        if not correcao.original or not correcao.corrigido:
            continue
        if correcao.original == correcao.corrigido:
            continue
        # Substituição cuidadosa — apenas primeira ocorrência
        if correcao.original in texto_atual:
            texto_atual = texto_atual.replace(correcao.original, correcao.corrigido, 1)
        else:
            logger.debug(f"Trecho não encontrado no HTML: '{correcao.original[:50]}...'")
    return texto_atual
```

---

## PARTE VI — REVISÃO DE ESTILO

### 6.1 System Prompt — Estilo Jornalístico

```python
PROMPT_REVISAO_ESTILO = """Revise o artigo abaixo verificando a aderência ao estilo jornalístico da brasileira.news.

TÍTULO: {titulo}
EDITORIA: {editoria}
CONTEÚDO (primeiros 4000 chars):
{conteudo_inicio}

CRITÉRIOS DE ESTILO A VERIFICAR:
1. Lide: Os primeiros 2 parágrafos respondem O quê? Quem? Quando? Onde? Por quê?
2. Tom: Objetivo e factual (sem opinião editorial implícita)
3. Voz ativa: Preferir "O presidente anunciou" a "Foi anunciado pelo presidente"
4. Frases: Máximo 3 linhas por frase. Parágrafos de 2-4 frases.
5. Jargão: Sem termos que o leitor médio não entenderia sem explicação
6. Marcadores de opinião proibidos: "é óbvio que", "infelizmente", "felizmente",
   "na minha opinião", "claramente", "evidentemente"
7. Repetição: Evitar repetir a mesma palavra chave mais de 3x no mesmo parágrafo
8. Atribuição: Toda afirmação factual deve ter fonte atribuída

INSTRUÇÕES:
- Aponte apenas problemas RELEVANTES (não detalhes menores)
- Para cada problema, sugira a correção mínima necessária
- Máximo de 10 sugestões de estilo

Retorne APENAS JSON:
{{
    "ajustes_estilo": [
        {{
            "tipo": "lide|tom|voz_passiva|frase_longa|jargao|opiniao|repeticao|atribuicao",
            "campo": "titulo|content|excerpt",
            "original": "trecho original exato",
            "corrigido": "trecho corrigido",
            "justificativa": "explicação"
        }}
    ],
    "qualidade_geral": "excelente|boa|adequada|precisa_ajustes",
    "nota_lide": "comentário sobre qualidade do lide"
}}
"""
```

### 6.2 Nó revisar_estilo

```python
async def node_revisar_estilo(state: RevisorState) -> RevisorState:
    """
    Nó 3: Revisão de estilo jornalístico via LLM PADRÃO.

    Foco: lide, tom, voz passiva, frases longas, jargão, marcadores de opinião.
    Usa apenas os primeiros 4000 chars de conteúdo para eficiência.
    """
    if not state.post:
        return state

    from brasileira.llm.smart_router import SmartLLMRouter, LLMTier
    from .prompts import SYSTEM_PROMPT_REVISOR, PROMPT_REVISAO_ESTILO

    router = SmartLLMRouter()

    # Para revisão de estilo, foco nas primeiras seções (lide é mais importante)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(state.post.conteudo_html, "lxml")
    texto_limpo = soup.get_text(separator="\n", strip=True)
    conteudo_inicio = texto_limpo[:4000]

    prompt = PROMPT_REVISAO_ESTILO.format(
        titulo=state.post.titulo,
        editoria=state.editoria,
        conteudo_inicio=conteudo_inicio,
    )

    try:
        response = await router.complete(
            system_prompt=SYSTEM_PROMPT_REVISOR,
            user_prompt=prompt,
            tier=LLMTier.PADRAO,
            task_type="revisao_texto",
            temperature=0.2,
            max_tokens=1500,
        )

        import json, re
        content = response.content.strip()
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            raise ValueError("LLM não retornou JSON válido para revisão de estilo")

        data = json.loads(json_match.group())
        ajustes_raw = data.get("ajustes_estilo", [])

        from .state import Correcao, CorrecaoTipo
        correcoes = []
        for c in ajustes_raw:
            correcoes.append(Correcao(
                tipo=CorrecaoTipo.ESTILO,
                campo=c.get("campo", "content"),
                original=c.get("original", ""),
                corrigido=c.get("corrigido", ""),
                justificativa=c.get("justificativa", ""),
            ))

        state.correcoes_estilo = correcoes
        state.adicionar_custo(
            tokens_in=response.usage.prompt_tokens,
            tokens_out=response.usage.completion_tokens,
            custo=response.usage.cost_usd,
        )

        logger.info(
            f"[Revisor] Estilo: {len(correcoes)} ajustes | qualidade={data.get('qualidade_geral', 'N/A')}"
        )

    except Exception as e:
        logger.error(f"[Revisor] Erro na revisão de estilo: {e}")
        state.adicionar_erro("revisar_estilo", e, fatal=False)

    return state
```

---

## PARTE VII — VERIFICAÇÃO DE FATOS BÁSICOS

### 7.1 Verificações Determinísticas (Sem LLM)

A verificação de fatos básicos usa **regras e regex**, não LLM. Isso garante:
- Custo zero nesta etapa
- Resultados determinísticos
- Velocidade máxima
- Zero alucinação

```python
# brasileira/agents/revisor/nodes.py

import re
from datetime import datetime
from typing import List
from .state import RevisorState, Correcao, CorrecaoTipo


# Padrões de data válidos para português brasileiro
PADRAO_DATA_VALIDA = re.compile(
    r'\b(\d{1,2})\s+de\s+(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|'
    r'setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b',
    re.IGNORECASE
)

# Padrão para datas em formato DD/MM/AAAA no corpo do texto (inadequado)
PADRAO_DATA_NUMERICA = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b')

# Padrão para horas
PADRAO_HORA = re.compile(r'\b(\d{1,2})h(\d{0,2})\b')

# Padrões de percentual
PADRAO_PERCENTUAL_TEXTO = re.compile(r'\b(\d+(?:[.,]\d+)?)\s+por\s+cento\b', re.IGNORECASE)

# Padrão para números por extenso incorretos (1 a 9 devem ser por extenso)
PADRAO_NUMERO_DIGITO = re.compile(r'\b([1-9])\s+(pessoa|homem|mulher|vez|dia|mês|ano|caso|ponto|real)\b', re.IGNORECASE)


def verificar_datas(texto: str) -> List[Correcao]:
    """
    Verifica formatação de datas.
    - DD/MM/AAAA no texto corrido → converter para "D de mês de AAAA"
    - Validar que datas são logicamente possíveis (dia 1-31, mês 1-12)
    """
    correcoes = []
    meses = {
        1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
        5: "maio", 6: "junho", 7: "julho", 8: "agosto",
        9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
    }

    for match in PADRAO_DATA_NUMERICA.finditer(texto):
        dia, mes, ano = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if 1 <= dia <= 31 and 1 <= mes <= 12 and 2000 <= ano <= 2030:
            original = match.group(0)
            corrigido = f"{dia} de {meses[mes]} de {ano}"
            correcoes.append(Correcao(
                tipo=CorrecaoTipo.FATO_DATA,
                campo="content",
                original=original,
                corrigido=corrigido,
                justificativa="Datas no corpo do texto devem ser por extenso: 'D de mês de AAAA'",
            ))

    return correcoes


def verificar_percentuais(texto: str) -> List[Correcao]:
    """
    Converte "X por cento" → "X%" no texto corrido.
    Exceção: em citações diretas, manter como está.
    """
    correcoes = []
    for match in PADRAO_PERCENTUAL_TEXTO.finditer(texto):
        numero = match.group(1).replace(",", ".")
        original = match.group(0)
        corrigido = f"{numero}%"
        correcoes.append(Correcao(
            tipo=CorrecaoTipo.FATO_NUMERO,
            campo="content",
            original=original,
            corrigido=corrigido,
            justificativa="Manual de estilo: usar '%' em vez de 'por cento'",
        ))
    return correcoes


def verificar_consistencia_interna(html: str) -> List[Correcao]:
    """
    Verifica consistência interna de dados no artigo.
    Detecta contradições óbvias de números.

    Exemplos de verificação:
    - Artigo menciona "10 mortos" e depois "11 vítimas fatais" (possível inconsistência)
    - Valores monetários em formatos diferentes (R$ 1.000 vs R$1000)
    """
    correcoes = []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    texto = soup.get_text()

    # Verificar formato de valores monetários
    padrao_real_sem_espaco = re.compile(r'R\$(\d)', re.IGNORECASE)
    for match in padrao_real_sem_espaco.finditer(texto):
        original_context = texto[max(0, match.start()-5):match.end()+10]
        correcoes.append(Correcao(
            tipo=CorrecaoTipo.CONSISTENCIA,
            campo="content",
            original=f"R${match.group(1)}",
            corrigido=f"R$ {match.group(1)}",
            justificativa="Formato monetário: 'R$ ' com espaço após o símbolo",
        ))

    return correcoes


async def node_verificar_fatos(state: RevisorState) -> RevisorState:
    """
    Nó 4: Verificação de fatos básicos — sem LLM.

    Verifica:
    - Formatação de datas (DD/MM/AAAA → por extenso)
    - Formatação de percentuais ("por cento" → %)
    - Consistência de valores monetários (R$ com espaço)
    - Formatação de horas (12:30 → 12h30)

    SEM LLM — apenas regex e regras determinísticas.
    """
    if not state.post:
        return state

    try:
        texto_html = state.post.conteudo_html

        correcoes = []
        correcoes.extend(verificar_datas(texto_html))
        correcoes.extend(verificar_percentuais(texto_html))
        correcoes.extend(verificar_consistencia_interna(texto_html))

        state.correcoes_fatos = correcoes
        logger.info(f"[Revisor] Fatos: {len(correcoes)} inconsistências de formatação")

    except Exception as e:
        logger.error(f"[Revisor] Erro na verificação de fatos: {e}")
        state.adicionar_erro("verificar_fatos", e, fatal=False)

    return state
```

---

## PARTE VIII — REVISÃO SEO

### 8.1 O que é Revisado em SEO

O Revisor otimiza os campos de SEO **sem reescrever o artigo**. Foco em:

| Campo | Regra 2025/2026 | Ação do Revisor |
|-------|----------------|-----------------|
| Título WordPress | Máx. 80 chars, sem ponto final | Encurtar se necessário |
| SEO Title (Yoast) | 50-60 chars, keyword no início | Gerar se ausente |
| Meta Description | 120-155 chars, ação clara | Gerar do excerpt se ausente |
| Excerpt | 150-200 chars, resumo factual | Melhorar se vago |
| Slug | Lowercase, hifens, sem acentos | Verificar (não altera se já publicado) |

### 8.2 System Prompt — SEO

```python
PROMPT_REVISAO_SEO = """Otimize os metadados SEO do artigo abaixo para um portal de notícias brasileiro.

DADOS DO ARTIGO:
Título atual: {titulo}
Excerpt atual: {excerpt}
SEO Title atual: {seo_title}
SEO Meta Description atual: {seo_metadesc}
Editoria: {editoria}
Primeiros 500 chars do conteúdo: {conteudo_inicio}

REGRAS SEO 2025/2026 PARA PORTAIS DE NOTÍCIAS:
1. SEO Title: 50-60 caracteres, keyword principal nos primeiros 40 chars, sem ponto final
2. Meta Description: 120-155 caracteres, responde O quê aconteceu e Por quê importa
3. Evitar: clickbait, sensacionalismo, promessas não cumpridas
4. Incluir: quem, o quê, quando (implícito na data do artigo)
5. Google reescreve >40% dos titles que não correspondem ao conteúdo — garantir consistência
6. Para breaking news: incluir urgência semântica (não "URGENTE" em maiúsculas)

INSTRUÇÕES:
- Gere versões otimizadas APENAS para campos que precisam de melhoria
- Se um campo já está adequado, NÃO inclua na resposta
- Mantenha português brasileiro

Retorne APENAS JSON:
{{
    "seo_title": "novo título SEO otimizado (ou null se já ok)",
    "seo_metadesc": "nova meta description (ou null se já ok)",
    "excerpt": "novo excerpt melhorado (ou null se já ok)",
    "titulo_wordpress": "novo título WordPress se muito longo (ou null se ok)",
    "justificativas": {{
        "seo_title": "por que foi alterado",
        "seo_metadesc": "por que foi alterado",
        "excerpt": "por que foi alterado",
        "titulo_wordpress": "por que foi alterado"
    }}
}}
"""
```

### 8.3 Nó revisar_seo

```python
async def node_revisar_seo(state: RevisorState) -> RevisorState:
    """
    Nó 5: Revisão e otimização SEO via LLM PADRÃO.

    Campos revisados: SEO Title, Meta Description, Excerpt, Título WordPress.
    NÃO altera: slug (já publicado e indexado), categorias, tags.
    """
    if not state.post:
        return state

    from brasileira.llm.smart_router import SmartLLMRouter, LLMTier
    from .prompts import SYSTEM_PROMPT_REVISOR, PROMPT_REVISAO_SEO
    from .state import Correcao, CorrecaoTipo

    router = SmartLLMRouter()
    post = state.post

    # Extrair SEO fields dos meta
    seo_title = post.meta.get("_yoast_wpseo_title", "") or ""
    seo_metadesc = post.meta.get("_yoast_wpseo_metadesc", "") or ""

    # Conteúdo limpo para contexto
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(post.conteudo_html, "lxml")
    texto_limpo = soup.get_text(separator=" ", strip=True)
    conteudo_inicio = texto_limpo[:500]

    prompt = PROMPT_REVISAO_SEO.format(
        titulo=post.titulo,
        excerpt=post.excerpt[:200] if post.excerpt else "",
        seo_title=seo_title[:100] if seo_title else "(não definido)",
        seo_metadesc=seo_metadesc[:200] if seo_metadesc else "(não definido)",
        editoria=state.editoria,
        conteudo_inicio=conteudo_inicio,
    )

    try:
        response = await router.complete(
            system_prompt=SYSTEM_PROMPT_REVISOR,
            user_prompt=prompt,
            tier=LLMTier.PADRAO,
            task_type="seo_otimizacao",
            temperature=0.3,
            max_tokens=800,
        )

        import json, re
        content = response.content.strip()
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            raise ValueError("LLM não retornou JSON válido para revisão SEO")

        data = json.loads(json_match.group())
        justificativas = data.get("justificativas", {})
        correcoes = []

        # SEO Title
        if data.get("seo_title"):
            correcoes.append(Correcao(
                tipo=CorrecaoTipo.SEO_TITULO,
                campo="meta._yoast_wpseo_title",
                original=seo_title,
                corrigido=data["seo_title"],
                justificativa=justificativas.get("seo_title", "Otimização SEO"),
            ))

        # Meta Description
        if data.get("seo_metadesc"):
            correcoes.append(Correcao(
                tipo=CorrecaoTipo.SEO_META,
                campo="meta._yoast_wpseo_metadesc",
                original=seo_metadesc,
                corrigido=data["seo_metadesc"],
                justificativa=justificativas.get("seo_metadesc", "Otimização meta description"),
            ))

        # Excerpt
        if data.get("excerpt"):
            correcoes.append(Correcao(
                tipo=CorrecaoTipo.SEO_EXCERPT,
                campo="excerpt",
                original=post.excerpt,
                corrigido=data["excerpt"],
                justificativa=justificativas.get("excerpt", "Melhoria do excerpt"),
            ))

        # Título WordPress
        if data.get("titulo_wordpress"):
            correcoes.append(Correcao(
                tipo=CorrecaoTipo.SEO_TITULO,
                campo="titulo",
                original=post.titulo,
                corrigido=data["titulo_wordpress"],
                justificativa=justificativas.get("titulo_wordpress", "Ajuste de comprimento do título"),
            ))

        state.correcoes_seo = correcoes
        state.adicionar_custo(
            tokens_in=response.usage.prompt_tokens,
            tokens_out=response.usage.completion_tokens,
            custo=response.usage.cost_usd,
        )

        logger.info(f"[Revisor] SEO: {len(correcoes)} campos otimizados")

    except Exception as e:
        logger.error(f"[Revisor] Erro na revisão SEO: {e}")
        state.adicionar_erro("revisar_seo", e, fatal=False)

    return state
```

---

## PARTE IX — APLICAÇÃO DE CORREÇÕES (PATCH WORDPRESS)

### 9.1 Lógica de Montagem do Payload

```python
async def node_aplicar_correcoes(state: RevisorState) -> RevisorState:
    """
    Nó 6: Monta o payload de correções e aplica via PATCH no WordPress.

    INVIOLÁVEL: SEMPRE executa, mesmo com zero correções.
    INVIOLÁVEL: Nunca inclui "status" no payload — não despublica.
    INVIOLÁVEL: Nunca inclui "date" no payload — não altera data.

    Processo:
    1. Consolidar todas as correções dos nós anteriores
    2. Aplicar substituições textuais ao HTML original
    3. Montar payload para PATCH
    4. Enviar PATCH para WordPress
    5. Registrar resultado no state
    """
    # Consolidar todas as correções
    state.consolidar_correcoes()

    if not state.post:
        logger.warning(f"[Revisor] Post {state.post_id}: sem post carregado, nada a aplicar")
        return state

    settings = get_settings()
    client = WordPressClient(
        wp_url=settings.WP_URL,
        wp_user=settings.WP_USER,
        wp_password=settings.WP_PASSWORD,
    )

    # Separar correções por campo
    correcoes_titulo = [c for c in state.todas_correcoes if c.campo == "titulo"]
    correcoes_content = [c for c in state.todas_correcoes if c.campo == "content"]
    correcoes_excerpt = [c for c in state.todas_correcoes if c.campo == "excerpt"]
    correcoes_meta = {c.campo: c for c in state.todas_correcoes if c.campo.startswith("meta.")}

    # Montar payload
    payload = {}

    # Título
    titulo_final = state.post.titulo
    for c in correcoes_titulo:
        titulo_final = titulo_final.replace(c.original, c.corrigido, 1)
    if titulo_final != state.post.titulo:
        payload["title"] = titulo_final

    # Conteúdo HTML
    conteudo_final = state.post.conteudo_html
    for c in correcoes_content:
        if c.original and c.original in conteudo_final:
            conteudo_final = conteudo_final.replace(c.original, c.corrigido, 1)
    if conteudo_final != state.post.conteudo_html:
        payload["content"] = conteudo_final

    # Excerpt
    excerpt_final = state.post.excerpt
    for c in correcoes_excerpt:
        excerpt_final = c.corrigido  # Excerpt é substituído inteiro
    if excerpt_final != state.post.excerpt:
        payload["excerpt"] = excerpt_final

    # Meta fields (Yoast SEO)
    meta_updates = {}
    for campo_meta, correcao in correcoes_meta.items():
        # "meta._yoast_wpseo_title" → "_yoast_wpseo_title"
        meta_key = campo_meta.replace("meta.", "")
        meta_updates[meta_key] = correcao.corrigido

    if meta_updates:
        payload["meta"] = meta_updates

    state.patch_payload = payload

    # Aplicar PATCH
    total_campos = len(payload)
    total_correcoes = len(state.todas_correcoes)

    logger.info(
        f"[Revisor] Post {state.post_id}: aplicando {total_correcoes} correções "
        f"em {total_campos} campos"
    )

    try:
        response = await client.patch_post(state.post_id, payload)
        state.patch_aplicado = True
        state.patch_response = response

        logger.info(
            f"[Revisor] Post {state.post_id}: PATCH aplicado com sucesso. "
            f"Modificado em: {response.get('modified', 'N/A')}"
        )

    except RuntimeError as e:
        logger.error(f"[Revisor] Falha no PATCH do post {state.post_id}: {e}")
        state.adicionar_erro("aplicar_correcoes", e, fatal=False)
        # Não fatal — o post já está publicado mesmo sem as correções

    return state
```

### 9.2 Tratamento de Edge Cases no PATCH

```python
# Edge cases que o nó aplicar_correcoes deve tratar:

# CASO 1: Correção de substring não encontrada no HTML final
# (pode ter sido alterada por nó anterior)
if c.original not in conteudo_atual:
    logger.debug(f"[Revisor] Substring não encontrada após edições anteriores: '{c.original[:40]}'")
    continue  # Pular sem erro

# CASO 2: Correção circular (original == corrigido)
if c.original == c.corrigido:
    continue

# CASO 3: Correção cria HTML inválido
# Validar com BeautifulSoup após aplicação
soup_check = BeautifulSoup(conteudo_final, "lxml")
if not soup_check.find():
    logger.error("[Revisor] PATCH de conteúdo resultaria em HTML inválido — revertendo")
    conteudo_final = state.post.conteudo_html  # Reverter

# CASO 4: Payload vazio (nenhuma correção necessária)
if not payload:
    logger.info(f"[Revisor] Post {state.post_id}: nenhuma correção necessária")
    state.patch_aplicado = True  # Marcado como aplicado (com zero mudanças)
    state.patch_response = {"id": state.post_id, "status": "sem_alteracoes"}
```

### 9.3 Diagrama do Payload Final

```
state.todas_correcoes
    │
    ├── correcoes_titulo (campo="titulo")
    │       → payload["title"] = titulo_corrigido
    │
    ├── correcoes_content (campo="content")
    │       → payload["content"] = html_com_substituicoes
    │
    ├── correcoes_excerpt (campo="excerpt")
    │       → payload["excerpt"] = excerpt_melhorado
    │
    └── correcoes_meta (campo="meta.*")
            → payload["meta"] = {
                "_yoast_wpseo_title": "...",
                "_yoast_wpseo_metadesc": "..."
              }

PATCH /wp-json/wp/v2/posts/{post_id}
Body: payload
NÃO INCLUI: status, date, author, slug
```

---

## PARTE X — MEMÓRIA DO REVISOR

### 10.1 Três Tipos de Memória

O Revisor mantém os três tipos de memória da V3:

**Memória Semântica:** Padrões de erros recorrentes por editoria, armazenados como embeddings em pgvector. Permite ao Revisor "lembrar" que artigos de Política frequentemente têm problemas com concordância de cargos, ou que artigos de Economia erram na formatação de números.

**Memória Episódica:** Histórico de revisões realizadas. Cada revisão é um episódio: qual post, quais erros encontrados, quais correções aplicadas, qual editoria.

**Working Memory:** Estado do ciclo atual. Mantido em Redis com TTL de 4 horas. Inclui os padrões de erro mais frequentes da sessão atual.

### 10.2 Implementação da Memória

```python
# brasileira/agents/revisor/memory.py

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg
import redis.asyncio as aioredis
from pgvector.asyncpg import register_vector

logger = logging.getLogger(__name__)


class RevisorMemory:
    """
    Gerencia os três tipos de memória do Revisor:
    - Semântica: embeddings em pgvector (padrões de erro)
    - Episódica: histórico de revisões no PostgreSQL
    - Working: estado atual em Redis
    """

    def __init__(self, pg_pool: asyncpg.Pool, redis_client: aioredis.Redis):
        self.pg = pg_pool
        self.redis = redis_client

    # ──────────────────────────────────────────────
    # MEMÓRIA WORKING (Redis)
    # ──────────────────────────────────────────────

    async def salvar_working_memory(self, session_id: str, dados: Dict[str, Any]):
        """Persiste working memory no Redis com TTL de 4 horas."""
        chave = f"agent:working_memory:revisor:{session_id}"
        await self.redis.hset(chave, mapping={
            k: json.dumps(v) if not isinstance(v, str) else v
            for k, v in dados.items()
        })
        await self.redis.expire(chave, 4 * 3600)  # 4 horas

    async def carregar_working_memory(self, session_id: str) -> Dict[str, Any]:
        """Recupera working memory do Redis."""
        chave = f"agent:working_memory:revisor:{session_id}"
        dados_raw = await self.redis.hgetall(chave)
        if not dados_raw:
            return {}
        return {
            k.decode(): json.loads(v.decode()) if v.decode().startswith(('[', '{')) else v.decode()
            for k, v in dados_raw.items()
        }

    # ──────────────────────────────────────────────
    # MEMÓRIA EPISÓDICA (PostgreSQL)
    # ──────────────────────────────────────────────

    async def registrar_revisao(
        self,
        post_id: int,
        editoria: str,
        total_correcoes: int,
        tipos_correcoes: Dict[str, int],
        custo_usd: float,
        duracao_ms: int,
        sucesso: bool,
    ):
        """Registra uma revisão concluída na memória episódica."""
        await self.pg.execute("""
            INSERT INTO revisoes_realizadas (
                post_id, editoria, total_correcoes, tipos_correcoes,
                custo_usd, duracao_ms, sucesso, revisado_em
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            ON CONFLICT (post_id) DO UPDATE SET
                total_correcoes = EXCLUDED.total_correcoes,
                tipos_correcoes = EXCLUDED.tipos_correcoes,
                revisado_em = NOW()
        """,
            post_id, editoria, total_correcoes,
            json.dumps(tipos_correcoes), custo_usd, duracao_ms, sucesso
        )

    async def buscar_revisoes_recentes(
        self,
        editoria: str,
        limite: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Busca revisões recentes de uma editoria para contexto.
        Usado para identificar padrões de erro recorrentes.
        """
        rows = await self.pg.fetch("""
            SELECT post_id, total_correcoes, tipos_correcoes, revisado_em
            FROM revisoes_realizadas
            WHERE editoria = $1
            ORDER BY revisado_em DESC
            LIMIT $2
        """, editoria, limite)

        return [dict(row) for row in rows]

    # ──────────────────────────────────────────────
    # MEMÓRIA SEMÂNTICA (pgvector)
    # ──────────────────────────────────────────────

    async def salvar_padrao_erro(
        self,
        descricao: str,
        editoria: str,
        tipo_erro: str,
        embedding: List[float],
        exemplo_original: str,
        exemplo_corrigido: str,
    ):
        """
        Salva um padrão de erro na memória semântica.
        Permite busca semântica posterior para contexto de revisão.
        """
        await self.pg.execute("""
            INSERT INTO memoria_agentes (
                agente, tipo, conteudo, embedding, metadata, criado_em
            ) VALUES ($1, 'semantica', $2, $3, $4, NOW())
        """,
            "revisor",
            json.dumps({
                "descricao": descricao,
                "editoria": editoria,
                "tipo_erro": tipo_erro,
                "exemplo_original": exemplo_original,
                "exemplo_corrigido": exemplo_corrigido,
            }),
            embedding,
            json.dumps({"editoria": editoria, "tipo_erro": tipo_erro})
        )

    async def buscar_padroes_similares(
        self,
        embedding_consulta: List[float],
        editoria: Optional[str] = None,
        limite: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Busca padrões de erro similares via similaridade cosseno em pgvector.
        Usado para enriquecer o contexto do LLM de revisão.
        """
        filtro_editoria = "AND (conteudo->>'editoria' = $3)" if editoria else ""
        params = [embedding_consulta, limite]
        if editoria:
            params.append(editoria)

        query = f"""
            SELECT conteudo, 1 - (embedding <=> $1::vector) AS similaridade
            FROM memoria_agentes
            WHERE agente = 'revisor' AND tipo = 'semantica'
            {filtro_editoria}
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """
        rows = await self.pg.fetch(query, *params)
        return [
            {"conteudo": json.loads(row["conteudo"]), "similaridade": row["similaridade"]}
            for row in rows
        ]
```

### 10.3 Nó registrar_revisao

```python
async def node_registrar_revisao(state: RevisorState) -> RevisorState:
    """
    Nó 7: Registra a revisão concluída em todas as camadas de memória.

    PostgreSQL: revisoes_realizadas
    Redis: working memory com padrões da sessão
    pgvector: padrões de erro frequentes (se aplicável)
    """
    from brasileira.db import get_pg_pool
    from brasileira.cache import get_redis
    from .memory import RevisorMemory
    from datetime import datetime

    try:
        pg_pool = await get_pg_pool()
        redis = await get_redis()
        memory = RevisorMemory(pg_pool, redis)

        # Calcular métricas da revisão
        state.concluido_em = datetime.utcnow()
        duracao_ms = int(
            (state.concluido_em - state.iniciado_em).total_seconds() * 1000
        ) if state.iniciado_em else 0

        # Contabilizar tipos de correções
        from collections import Counter
        tipos_correcoes = Counter(c.tipo.value for c in state.todas_correcoes)

        # Registrar na memória episódica
        await memory.registrar_revisao(
            post_id=state.post_id,
            editoria=state.editoria,
            total_correcoes=len(state.todas_correcoes),
            tipos_correcoes=dict(tipos_correcoes),
            custo_usd=state.total_custo_usd,
            duracao_ms=duracao_ms,
            sucesso=state.sucesso,
        )

        # Atualizar working memory com padrões da sessão
        working = await memory.carregar_working_memory(state.session_id)
        padroes = working.get("padroes_erro", {})
        for tipo, count in tipos_correcoes.items():
            padroes[tipo] = padroes.get(tipo, 0) + count
        working["padroes_erro"] = padroes
        working["ultima_revisao"] = state.post_id
        working["total_revisoes"] = working.get("total_revisoes", 0) + 1
        await memory.salvar_working_memory(state.session_id, working)

        logger.info(
            f"[Revisor] Post {state.post_id}: revisão registrada. "
            f"{len(state.todas_correcoes)} correções em {duracao_ms}ms. "
            f"Custo: ${state.total_custo_usd:.6f}"
        )

    except Exception as e:
        logger.error(f"[Revisor] Erro ao registrar revisão: {e}")
        state.adicionar_erro("registrar_revisao", e, fatal=False)
        # Não fatal — a revisão já foi aplicada no post

    return state
```

---

## PARTE XI — SCHEMAS KAFKA E POSTGRESQL

### 11.1 Schema do Evento Kafka — Input

```python
# brasileira/agents/revisor/schemas.py

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class EventoArticlePublished(BaseModel):
    """
    Schema do evento article-published consumido do Kafka.
    Produzido pelo Reporter após publicação bem-sucedida no WordPress.
    """
    event: str = "article_published"
    post_id: int                             # ID do post no WordPress
    titulo: str                              # Título do artigo publicado
    editoria: str                            # Editoria (politica, economia, etc.)
    urgencia: str = "normal"                 # normal | alta | breaking
    url: str                                 # URL do artigo no portal
    fonte_original: str                      # URL da fonte RSS/scraper
    timestamp: str                           # ISO 8601 com timezone -03:00

    # Opcional — nem sempre disponível
    slug: Optional[str] = None
    categoria_wp_id: Optional[int] = None
    tags: list = Field(default_factory=list)

    # Para tracking
    reporter_session_id: Optional[str] = None
    pipeline_id: Optional[str] = None


class ResultadoRevisao(BaseModel):
    """
    Schema do resultado de revisão para logging e auditoria.
    NÃO é publicado no Kafka — apenas armazenado no PostgreSQL.
    """
    post_id: int
    session_id: str
    editoria: str
    total_correcoes: int
    tipos_correcoes: dict                    # {"gramatica": 3, "seo_titulo": 1, ...}
    campos_alterados: list                   # ["title", "content", "meta"]
    custo_usd: float
    duracao_ms: int
    sucesso: bool
    patch_aplicado: bool
    revisado_em: datetime
```

### 11.2 SQL — Tabelas PostgreSQL

```sql
-- Tabela de revisões realizadas (memória episódica do Revisor)
CREATE TABLE IF NOT EXISTS revisoes_realizadas (
    id              BIGSERIAL PRIMARY KEY,
    post_id         INTEGER NOT NULL,
    editoria        VARCHAR(50) NOT NULL DEFAULT 'geral',
    total_correcoes INTEGER NOT NULL DEFAULT 0,
    tipos_correcoes JSONB NOT NULL DEFAULT '{}',
    campos_alterados JSONB NOT NULL DEFAULT '[]',
    custo_usd       DECIMAL(10, 8) NOT NULL DEFAULT 0,
    duracao_ms      INTEGER NOT NULL DEFAULT 0,
    sucesso         BOOLEAN NOT NULL DEFAULT TRUE,
    patch_aplicado  BOOLEAN NOT NULL DEFAULT FALSE,
    revisado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Índices para consultas frequentes
    CONSTRAINT revisoes_realizadas_post_id_unique UNIQUE (post_id)
);

CREATE INDEX IF NOT EXISTS idx_revisoes_editoria
    ON revisoes_realizadas (editoria, revisado_em DESC);

CREATE INDEX IF NOT EXISTS idx_revisoes_data
    ON revisoes_realizadas (revisado_em DESC);

CREATE INDEX IF NOT EXISTS idx_revisoes_tipos
    ON revisoes_realizadas USING GIN (tipos_correcoes);


-- Tabela de memória semântica (reutiliza memoria_agentes existente)
-- Verificar que a tabela existe:
CREATE TABLE IF NOT EXISTS memoria_agentes (
    id          BIGSERIAL PRIMARY KEY,
    agente      VARCHAR(50) NOT NULL,
    tipo        VARCHAR(20) NOT NULL CHECK (tipo IN ('semantica', 'episodica', 'working')),
    conteudo    JSONB NOT NULL,
    embedding   vector(1536),              -- OpenAI text-embedding-3-small
    metadata    JSONB NOT NULL DEFAULT '{}',
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memoria_agente_tipo
    ON memoria_agentes (agente, tipo);

-- Índice ivfflat para busca semântica eficiente
CREATE INDEX IF NOT EXISTS idx_memoria_embedding
    ON memoria_agentes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);


-- View para métricas do Revisor (Dashboard)
CREATE OR REPLACE VIEW v_revisor_metricas AS
SELECT
    DATE(revisado_em) AS data,
    editoria,
    COUNT(*) AS total_revisoes,
    AVG(total_correcoes) AS media_correcoes,
    SUM(total_correcoes) AS total_correcoes_dia,
    AVG(custo_usd) AS custo_medio_usd,
    SUM(custo_usd) AS custo_total_usd,
    AVG(duracao_ms) AS duracao_media_ms,
    SUM(CASE WHEN sucesso THEN 1 ELSE 0 END)::FLOAT / COUNT(*) AS taxa_sucesso
FROM revisoes_realizadas
GROUP BY DATE(revisado_em), editoria
ORDER BY data DESC, total_revisoes DESC;
```

### 11.3 Schema Redis

```
Chaves Redis usadas pelo Revisor:

agent:working_memory:revisor:{session_id}
  Tipo: HASH
  TTL: 4 horas (14400 segundos)
  Campos:
    padroes_erro: JSON {tipo: count}
    ultima_revisao: post_id
    total_revisoes: int
    iniciado_em: ISO timestamp

revisor:lock:{post_id}
  Tipo: STRING
  TTL: 5 minutos (300 segundos)
  Valor: session_id
  Propósito: Evitar dupla revisão do mesmo post
  (race condition: dois workers Revisor no mesmo post)

revisor:stats:hoje
  Tipo: HASH
  TTL: 24 horas
  Campos:
    total_revisoes: int
    total_correcoes: int
    custo_total_usd: float
    erros: int
```

---

## PARTE XII — ESTRUTURA DE DIRETÓRIOS

### 12.1 Árvore Completa de Arquivos

```
brasileira/
├── agents/
│   └── revisor/
│       ├── __init__.py              # Exports: RevisorAgent, RevisorState
│       ├── agent.py                 # Classe RevisorAgent + build_revisor_graph()
│       ├── state.py                 # RevisorState, Correcao, CorrecaoTipo, PostCarregado
│       ├── nodes.py                 # 7 nós do LangGraph
│       ├── prompts.py               # System prompts e templates
│       ├── wp_client.py             # WordPressClient (GET + PATCH)
│       ├── kafka_consumer.py        # KafkaConsumer + loop de processamento
│       ├── memory.py                # RevisorMemory (semântica + episódica + working)
│       └── schemas.py               # EventoArticlePublished, ResultadoRevisao
│
├── llm/
│   └── smart_router.py              # SmartLLMRouter (Componente #1 — não implementar aqui)
│
├── db/
│   └── __init__.py                  # get_pg_pool()
│
├── cache/
│   └── __init__.py                  # get_redis()
│
└── config.py                        # Settings (WP_URL, WP_USER, WP_PASSWORD, etc.)

scripts/
└── migrate_revisor.sql              # SQL das tabelas revisoes_realizadas

tests/
└── agents/
    └── revisor/
        ├── test_wp_client.py
        ├── test_nodes.py
        ├── test_agent.py
        └── test_kafka_consumer.py
```

### 12.2 __init__.py

```python
# brasileira/agents/revisor/__init__.py

from .agent import RevisorAgent, build_revisor_graph, REVISOR_GRAPH
from .state import RevisorState, Correcao, CorrecaoTipo, PostCarregado
from .kafka_consumer import RevisorKafkaConsumer
from .schemas import EventoArticlePublished, ResultadoRevisao

__all__ = [
    "RevisorAgent",
    "build_revisor_graph",
    "REVISOR_GRAPH",
    "RevisorState",
    "Correcao",
    "CorrecaoTipo",
    "PostCarregado",
    "RevisorKafkaConsumer",
    "EventoArticlePublished",
    "ResultadoRevisao",
]
```

---

## PARTE XIII — ENTRYPOINT

### 13.1 Kafka Consumer e Orquestrador

```python
# brasileira/agents/revisor/kafka_consumer.py

import asyncio
import json
import logging
import signal
import uuid
from datetime import datetime
from typing import Optional

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from .agent import REVISOR_GRAPH
from .state import RevisorState
from .schemas import EventoArticlePublished
from brasileira.config import get_settings

logger = logging.getLogger(__name__)


class RevisorKafkaConsumer:
    """
    Consumidor Kafka para o Revisor V3.

    Consome tópico: article-published
    Group ID: revisor-consumers (DIFERENTE de fotografo-consumers)
    Concorrência: até MAX_CONCURRENT_REVIEWS por instância
    """

    TOPICO = "article-published"
    GROUP_ID = "revisor-consumers"
    MAX_CONCURRENT_REVIEWS = 5      # Revisões em paralelo por instância
    BATCH_TIMEOUT_MS = 1000         # Aguardar até 1s por batch

    def __init__(self):
        self.settings = get_settings()
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REVIEWS)
        self._tasks = set()

    async def iniciar(self):
        """Inicializa o consumer Kafka e começa a processar mensagens."""
        self.consumer = AIOKafkaConsumer(
            self.TOPICO,
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.GROUP_ID,
            auto_offset_reset="latest",       # Processar apenas mensagens novas
            enable_auto_commit=False,          # Commit manual após processamento
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            max_poll_records=10,               # Processar até 10 por poll
            session_timeout_ms=30000,          # 30s timeout de sessão
            heartbeat_interval_ms=10000,       # Heartbeat a cada 10s
        )

        await self.consumer.start()
        self._running = True

        # Registrar signal handlers para shutdown gracioso
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.parar()))

        logger.info(
            f"[Revisor] Consumer Kafka iniciado. "
            f"Tópico: {self.TOPICO} | Group: {self.GROUP_ID}"
        )

        await self._loop_processamento()

    async def parar(self):
        """Shutdown gracioso: finaliza revisões em andamento antes de parar."""
        logger.info("[Revisor] Iniciando shutdown gracioso...")
        self._running = False

        # Aguardar tarefas em andamento (max 30s)
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=30)

        if self.consumer:
            await self.consumer.stop()

        logger.info("[Revisor] Consumer Kafka parado com sucesso")

    async def _loop_processamento(self):
        """Loop principal de processamento de mensagens."""
        while self._running:
            try:
                # Poll com timeout para verificar _running periodicamente
                records = await self.consumer.getmany(
                    timeout_ms=self.BATCH_TIMEOUT_MS,
                    max_records=self.MAX_CONCURRENT_REVIEWS,
                )

                if not records:
                    continue

                # Processar cada mensagem em paralelo (até MAX_CONCURRENT_REVIEWS)
                tasks = []
                for tp, msgs in records.items():
                    for msg in msgs:
                        task = asyncio.create_task(
                            self._processar_com_semaforo(msg.value, msg.offset)
                        )
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)
                        tasks.append(task)

                # Aguardar todas as tarefas do batch
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Commit após processar o batch completo
                await self.consumer.commit()

            except KafkaError as e:
                logger.error(f"[Revisor] Erro Kafka: {e}")
                await asyncio.sleep(5)  # Backoff antes de retomar

            except Exception as e:
                logger.error(f"[Revisor] Erro inesperado no loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _processar_com_semaforo(self, evento_raw: dict, offset: int):
        """Processa uma mensagem com controle de concorrência via semáforo."""
        async with self._semaphore:
            await self._processar_evento(evento_raw, offset)

    async def _processar_evento(self, evento_raw: dict, offset: int):
        """
        Processa um único evento article_published.
        Valida o schema, instancia o state e executa o grafo LangGraph.
        """
        try:
            # Validar schema do evento
            evento = EventoArticlePublished(**evento_raw)
        except Exception as e:
            logger.warning(f"[Revisor] Evento inválido (offset {offset}): {e}")
            return

        post_id = evento.post_id
        logger.info(f"[Revisor] Processando post {post_id}: '{evento.titulo[:50]}...'")

        # Verificar lock Redis (evitar dupla revisão)
        from brasileira.cache import get_redis
        redis = await get_redis()
        lock_key = f"revisor:lock:{post_id}"
        session_id = str(uuid.uuid4())

        adquiriu = await redis.set(lock_key, session_id, nx=True, ex=300)  # 5 min
        if not adquiriu:
            logger.info(f"[Revisor] Post {post_id} já está sendo revisado por outra instância")
            return

        try:
            # Criar estado inicial
            state = RevisorState(
                session_id=session_id,
                post_id=post_id,
                event_data=evento_raw,
                editoria=evento.editoria,
                iniciado_em=datetime.utcnow(),
            )

            # Executar grafo LangGraph
            resultado = await REVISOR_GRAPH.ainvoke(state)

            # Logar resultado
            total = len(resultado.todas_correcoes) if hasattr(resultado, "todas_correcoes") else 0
            logger.info(
                f"[Revisor] Post {post_id} concluído: "
                f"{total} correções | "
                f"patch={'✓' if resultado.patch_aplicado else '✗'} | "
                f"custo=${resultado.total_custo_usd:.6f}"
            )

            # Atualizar stats Redis
            stats_key = "revisor:stats:hoje"
            await redis.hincrby(stats_key, "total_revisoes", 1)
            await redis.hincrby(stats_key, "total_correcoes", total)
            await redis.expire(stats_key, 86400)  # 24 horas

        except Exception as e:
            logger.error(f"[Revisor] Erro ao processar post {post_id}: {e}", exc_info=True)

        finally:
            # Liberar lock
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            await redis.eval(script, 1, lock_key, session_id)
```

### 13.2 Entrypoint Principal

```python
# brasileira/agents/revisor/__main__.py
# Executar com: python -m brasileira.agents.revisor

import asyncio
import logging
import sys
from .kafka_consumer import RevisorKafkaConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)

logger = logging.getLogger("brasileira.revisor")


async def main():
    """Entrypoint do Revisor V3."""
    logger.info("=" * 60)
    logger.info("  REVISOR V3 — QA Pós-Publicação — brasileira.news")
    logger.info("=" * 60)
    logger.info("Tópico Kafka: article-published")
    logger.info("Group ID: revisor-consumers")
    logger.info("LLM Tier: PADRÃO")
    logger.info("Modo: NÃO REJEITA, NUNCA DESPUBLICA")
    logger.info("=" * 60)

    consumer = RevisorKafkaConsumer()
    await consumer.iniciar()


if __name__ == "__main__":
    asyncio.run(main())
```

### 13.3 Classe RevisorAgent (Wrapper de Alto Nível)

```python
# brasileira/agents/revisor/agent.py — Seção da classe

class RevisorAgent:
    """
    Wrapper de alto nível para o Revisor V3.
    Encapsula o grafo LangGraph e a lógica de execução.

    Uso:
        agent = RevisorAgent()
        resultado = await agent.revisar(post_id=12345, editoria="politica")
    """

    def __init__(self):
        self.graph = REVISOR_GRAPH
        self.logger = logging.getLogger(__name__)

    async def revisar(self, post_id: int, editoria: str = "geral") -> RevisorState:
        """
        Executa o pipeline de revisão completo em um post publicado.

        Args:
            post_id: ID do post WordPress a revisar
            editoria: Editoria do post (para contextualizar o LLM)

        Returns:
            RevisorState com todos os resultados da revisão

        Raises:
            Nunca levanta exceção — erros são capturados em state.erros
        """
        import uuid
        state = RevisorState(
            session_id=str(uuid.uuid4()),
            post_id=post_id,
            editoria=editoria,
            iniciado_em=datetime.utcnow(),
        )

        try:
            resultado = await self.graph.ainvoke(state)
            return resultado
        except Exception as e:
            self.logger.error(f"[Revisor] Erro fatal no grafo: {e}", exc_info=True)
            state.adicionar_erro("graph_execution", e, fatal=True)
            return state

    async def revisar_multiplos(
        self,
        posts: list[dict],
        max_concorrente: int = 3
    ) -> list[RevisorState]:
        """
        Revisa múltiplos posts em paralelo com controle de concorrência.
        Útil para recuperação de posts não revisados após downtime.
        """
        semaforo = asyncio.Semaphore(max_concorrente)

        async def revisar_com_semaforo(post: dict) -> RevisorState:
            async with semaforo:
                return await self.revisar(
                    post_id=post["post_id"],
                    editoria=post.get("editoria", "geral"),
                )

        tasks = [revisar_com_semaforo(p) for p in posts]
        return await asyncio.gather(*tasks, return_exceptions=False)
```

### 13.4 Dockerfile

```dockerfile
# Dockerfile para o Revisor V3
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev --no-interaction

COPY . .

# Variáveis de ambiente obrigatórias
ENV KAFKA_BOOTSTRAP_SERVERS=""
ENV WP_URL=""
ENV WP_USER=""
ENV WP_PASSWORD=""
ENV DATABASE_URL=""
ENV REDIS_URL=""

# Variáveis LLM (pelo menos um provedor PADRÃO é obrigatório)
ENV OPENAI_API_KEY=""
ENV ANTHROPIC_API_KEY=""
ENV GOOGLE_API_KEY=""

CMD ["python", "-m", "brasileira.agents.revisor"]
```

### 13.5 docker-compose.yaml (serviço Revisor)

```yaml
# Em docker-compose.yaml — adicionar ao services existente:

revisor:
  build:
    context: .
    dockerfile: Dockerfile
  command: python -m brasileira.agents.revisor
  environment:
    - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS}
    - WP_URL=${WP_URL}
    - WP_USER=${WP_USER}
    - WP_PASSWORD=${WP_PASSWORD}
    - DATABASE_URL=${DATABASE_URL}
    - REDIS_URL=${REDIS_URL}
    - OPENAI_API_KEY=${OPENAI_API_KEY}
    - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    - GOOGLE_API_KEY=${GOOGLE_API_KEY}
  depends_on:
    - kafka
    - postgres
    - redis
  restart: unless-stopped
  deploy:
    replicas: 2   # 2 instâncias para paralelismo
    resources:
      limits:
        memory: 512M
        cpus: "0.5"
  healthcheck:
    test: ["CMD", "python", "-c", "import brasileira.agents.revisor; print('ok')"]
    interval: 30s
    timeout: 10s
    retries: 3
  logging:
    driver: "json-file"
    options:
      max-size: "50m"
      max-file: "3"
```

---

## PARTE XIV — TESTES E CHECKLIST

### 14.1 Testes Unitários

```python
# tests/agents/revisor/test_nodes.py

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from brasileira.agents.revisor.state import RevisorState, PostCarregado
from brasileira.agents.revisor.nodes import (
    node_carregar_post,
    node_revisar_gramatica,
    node_verificar_fatos,
    node_revisar_seo,
    node_aplicar_correcoes,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def estado_basico():
    return RevisorState(
        session_id="test-session-01",
        post_id=12345,
        editoria="politica",
    )

@pytest.fixture
def post_exemplo():
    return PostCarregado(
        post_id=12345,
        titulo="Presidente anuncia nova política econômica nesta quarta-feira",
        conteudo_html="""
            <p>O presidente da República anunciou hoje, 26 de março de 2026,
            uma nova política economica para o país. De acordo com o ministério
            da fazenda, as medidas entram em vigor no proximo mês.</p>
            <p>Segundo comunicado oficial, o pacote inclui redução de impostos
            e investimentos em infraestrutura.</p>
        """,
        excerpt="O presidente anunciou nova política econômica nesta quarta-feira.",
        slug="presidente-anuncia-nova-politica-economica",
        status="publish",
        editoria="politica",
        meta={
            "_yoast_wpseo_title": "",
            "_yoast_wpseo_metadesc": "",
            "fonte_original": "https://agenciabrasil.ebc.com.br/...",
        },
        link="https://brasileira.news/politica/presidente-anuncia...",
        data_publicacao="2026-03-26T12:00:00-03:00",
    )

@pytest.fixture
def estado_com_post(estado_basico, post_exemplo):
    estado_basico.post = post_exemplo
    return estado_basico


# ─────────────────────────────────────────────
# Testes de Carregamento
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_carregar_post_sucesso(estado_basico, post_exemplo):
    """Verifica que o nó carrega o post corretamente."""
    with patch("brasileira.agents.revisor.nodes.WordPressClient") as MockWP:
        MockWP.return_value.get_post = AsyncMock(return_value=post_exemplo)
        resultado = await node_carregar_post(estado_basico)

    assert resultado.post is not None
    assert resultado.post.post_id == 12345
    assert resultado.post.status == "publish"
    assert len(resultado.erros) == 0


@pytest.mark.asyncio
async def test_carregar_post_nao_encontrado(estado_basico):
    """Verifica que post não encontrado registra erro mas não levanta exceção."""
    with patch("brasileira.agents.revisor.nodes.WordPressClient") as MockWP:
        MockWP.return_value.get_post = AsyncMock(
            side_effect=ValueError("Post 12345 não encontrado no WordPress")
        )
        resultado = await node_carregar_post(estado_basico)

    assert resultado.post is None
    assert len(resultado.erros) > 0
    assert any(e["etapa"] == "carregar_post" for e in resultado.erros)


# ─────────────────────────────────────────────
# Testes de Revisão Gramatical
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revisar_gramatica_sem_post(estado_basico):
    """Verifica que o nó pula graciosamente se não há post."""
    resultado = await node_revisar_gramatica(estado_basico)
    assert len(resultado.correcoes_gramatica) == 0
    assert len(resultado.erros) == 0


@pytest.mark.asyncio
async def test_revisar_gramatica_encontra_erros(estado_com_post):
    """Verifica que o LLM é chamado e as correções são parseadas."""
    mock_response = MagicMock()
    mock_response.content = '''{"correcoes": [
        {
            "tipo": "ortografia",
            "campo": "content",
            "original": "política economica",
            "corrigido": "política econômica",
            "justificativa": "Ausência de acento em 'econômica'"
        }
    ], "resumo": "1 erro ortográfico encontrado", "total_erros_encontrados": 1}'''
    mock_response.usage = MagicMock(prompt_tokens=500, completion_tokens=100, cost_usd=0.0001)

    with patch("brasileira.agents.revisor.nodes.SmartLLMRouter") as MockRouter:
        MockRouter.return_value.complete = AsyncMock(return_value=mock_response)
        resultado = await node_revisar_gramatica(estado_com_post)

    assert len(resultado.correcoes_gramatica) == 1
    assert resultado.correcoes_gramatica[0].original == "política economica"
    assert resultado.correcoes_gramatica[0].corrigido == "política econômica"
    assert resultado.llm_calls == 1


# ─────────────────────────────────────────────
# Testes de Verificação de Fatos
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verificar_fatos_data_numerica(estado_com_post):
    """Verifica que datas no formato DD/MM/AAAA são detectadas."""
    estado_com_post.post.conteudo_html = "<p>Em 26/03/2026, o presidente anunciou...</p>"
    resultado = await node_verificar_fatos(estado_com_post)

    correcoes_data = [c for c in resultado.correcoes_fatos if c.tipo.value == "fato_data"]
    assert len(correcoes_data) == 1
    assert correcoes_data[0].original == "26/03/2026"
    assert correcoes_data[0].corrigido == "26 de março de 2026"


@pytest.mark.asyncio
async def test_verificar_fatos_percentual(estado_com_post):
    """Verifica que 'X por cento' é convertido para 'X%'."""
    estado_com_post.post.conteudo_html = "<p>O crescimento foi de 5 por cento no ano.</p>"
    resultado = await node_verificar_fatos(estado_com_post)

    correcoes_perc = [c for c in resultado.correcoes_fatos if c.tipo.value == "fato_numero"]
    assert len(correcoes_perc) == 1
    assert correcoes_perc[0].original == "5 por cento"
    assert correcoes_perc[0].corrigido == "5%"


# ─────────────────────────────────────────────
# Testes de Aplicação das Correções (INVIOLÁVEL)
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aplicar_correcoes_nunca_altera_status(estado_com_post):
    """CRÍTICO: Verifica que o payload NUNCA contém 'status'."""
    from brasileira.agents.revisor.state import Correcao, CorrecaoTipo
    estado_com_post.correcoes_gramatica = [
        Correcao(
            tipo=CorrecaoTipo.ORTOGRAFIA,
            campo="content",
            original="política economica",
            corrigido="política econômica",
            justificativa="Acento",
        )
    ]

    payloads_enviados = []

    with patch("brasileira.agents.revisor.nodes.WordPressClient") as MockWP:
        async def mock_patch(post_id, payload):
            payloads_enviados.append(payload)
            return {"id": post_id, "modified": "2026-03-26T12:05:00"}

        MockWP.return_value.patch_post = mock_patch
        await node_aplicar_correcoes(estado_com_post)

    assert len(payloads_enviados) == 1
    payload = payloads_enviados[0]
    assert "status" not in payload, "VIOLAÇÃO CRÍTICA: payload contém 'status'"
    assert "date" not in payload, "VIOLAÇÃO CRÍTICA: payload contém 'date'"
    assert "author" not in payload, "VIOLAÇÃO CRÍTICA: payload contém 'author'"


@pytest.mark.asyncio
async def test_aplicar_correcoes_sem_correcoes(estado_com_post):
    """Verifica que sem correções, o nó executa normalmente (patch vazio)."""
    with patch("brasileira.agents.revisor.nodes.WordPressClient") as MockWP:
        MockWP.return_value.patch_post = AsyncMock(
            return_value={"id": 12345, "status": "sem_alteracoes"}
        )
        resultado = await node_aplicar_correcoes(estado_com_post)

    assert resultado.patch_aplicado is True
    assert len(resultado.erros) == 0


# ─────────────────────────────────────────────
# Testes de Integração — Grafo Completo
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grafo_completo_sem_erros(post_exemplo):
    """Teste de integração: executa o grafo completo com mocks."""
    from brasileira.agents.revisor.agent import REVISOR_GRAPH
    from datetime import datetime

    state = RevisorState(
        session_id="integration-test-01",
        post_id=12345,
        editoria="politica",
        iniciado_em=datetime.utcnow(),
    )

    mock_wp_response = MagicMock()
    mock_response_llm = MagicMock()
    mock_response_llm.content = '{"correcoes": [], "resumo": "Sem erros", "total_erros_encontrados": 0}'
    mock_response_llm.usage = MagicMock(prompt_tokens=100, completion_tokens=50, cost_usd=0.00002)

    with (
        patch("brasileira.agents.revisor.nodes.WordPressClient") as MockWP,
        patch("brasileira.agents.revisor.nodes.SmartLLMRouter") as MockRouter,
        patch("brasileira.agents.revisor.nodes.get_pg_pool", AsyncMock()),
        patch("brasileira.agents.revisor.nodes.get_redis", AsyncMock()),
    ):
        MockWP.return_value.get_post = AsyncMock(return_value=post_exemplo)
        MockWP.return_value.patch_post = AsyncMock(return_value={"id": 12345})
        MockRouter.return_value.complete = AsyncMock(return_value=mock_response_llm)

        resultado = await REVISOR_GRAPH.ainvoke(state)

    assert resultado.patch_aplicado is True
    assert resultado.sucesso is True
    # Verifica que o grafo percorreu todos os nós
    assert resultado.post is not None
```

### 14.2 Checklist de Implementação

```
CHECKLIST DE IMPLEMENTAÇÃO — REVISOR V3
Status: [ ] Não iniciado | [~] Em progresso | [x] Concluído

PARTE I — FUNDAÇÃO
[ ] state.py criado com RevisorState, Correcao, CorrecaoTipo, PostCarregado
[ ] schemas.py criado com EventoArticlePublished e ResultadoRevisao
[ ] wp_client.py criado com WordPressClient (GET + PATCH)
[ ] prompts.py criado com todos os system prompts e templates

PARTE II — GRAFO LANGGRAPH
[ ] nodes.py criado com os 7 nós
[ ] agent.py com build_revisor_graph() e REVISOR_GRAPH
[ ] Fluxo LINEAR sem branches verificado
[ ] node_aplicar_correcoes SEMPRE executa (mesmo com zero correções)

PARTE III — NÓS INDIVIDUAIS
[ ] node_carregar_post: GET WordPress com retry e backoff
[ ] node_revisar_gramatica: LLM PADRÃO, temperatura 0.1
[ ] node_revisar_estilo: LLM PADRÃO, temperatura 0.2
[ ] node_verificar_fatos: SEM LLM, apenas regex
[ ] node_revisar_seo: LLM PADRÃO, temperatura 0.3
[ ] node_aplicar_correcoes: PATCH WordPress, sem "status" no payload
[ ] node_registrar_revisao: PostgreSQL + Redis + pgvector

PARTE IV — KAFKA CONSUMER
[ ] kafka_consumer.py com RevisorKafkaConsumer
[ ] Group ID: revisor-consumers (diferente do fotografo-consumers)
[ ] Semáforo de concorrência (MAX_CONCURRENT_REVIEWS=5)
[ ] Lock Redis anti-dupla-revisão por post_id
[ ] Shutdown gracioso implementado
[ ] __main__.py com entrypoint

PARTE V — MEMÓRIA
[ ] memory.py com RevisorMemory
[ ] Memória working (Redis, TTL 4h)
[ ] Memória episódica (PostgreSQL, revisoes_realizadas)
[ ] Memória semântica (pgvector, memoria_agentes)
[ ] Busca semântica de padrões similares implementada

PARTE VI — BANCO DE DADOS
[ ] Tabela revisoes_realizadas criada (SQL)
[ ] Índices criados
[ ] View v_revisor_metricas criada
[ ] Migration script em scripts/migrate_revisor.sql

PARTE VII — TESTES
[ ] test_wp_client.py — GET e PATCH testados
[ ] test_nodes.py — todos os 7 nós testados
[ ] test_agent.py — grafo completo testado
[ ] test_kafka_consumer.py — consumer testado com mock Kafka
[ ] Teste crítico: payload nunca contém "status" ou "date"

PARTE VIII — INFRAESTRUTURA
[ ] Dockerfile criado
[ ] docker-compose.yaml atualizado com serviço revisor
[ ] 2 réplicas configuradas
[ ] Healthcheck configurado

VERIFICAÇÕES FINAIS OBRIGATÓRIAS
[ ] ✓ Revisor NUNCA rejeita artigos
[ ] ✓ Revisor NUNCA despublica artigos
[ ] ✓ Revisor NUNCA altera status do post
[ ] ✓ Revisor NUNCA bloqueia o pipeline
[ ] ✓ LLM tier é PADRÃO (não PREMIUM) em todas as chamadas
[ ] ✓ Group ID Kafka é "revisor-consumers" (diferente do Fotógrafo)
[ ] ✓ Funciona em PARALELO com Fotógrafo (ambos consomem article-published)
[ ] ✓ Memória tem três camadas: semântica + episódica + working
[ ] ✓ Lock Redis previne dupla revisão do mesmo post
```

### 14.3 Testes Manuais de Fumaça (Smoke Tests)

```bash
# 1. Verificar que o consumer sobe corretamente
docker-compose up revisor
# Esperado: "REVISOR V3 — QA Pós-Publicação — brasileira.news" nos logs

# 2. Publicar evento de teste no Kafka
python -c "
from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode()
)
producer.send('article-published', {
    'event': 'article_published',
    'post_id': 99999,
    'titulo': 'Teste do Revisor V3',
    'editoria': 'tecnologia',
    'urgencia': 'normal',
    'url': 'https://brasileira.news/teste',
    'fonte_original': 'https://fonte.com/teste',
    'timestamp': '2026-03-26T12:00:00-03:00'
})
producer.flush()
print('Evento publicado')
"

# 3. Verificar logs do revisor
docker-compose logs revisor --tail=50

# Esperado nos logs:
# [Revisor] Processando post 99999: 'Teste do Revisor V3'
# [Revisor] Carregando post 99999 do WordPress...
# [Revisor] Post carregado: 'Teste do Revisor V3...' (XXXX chars)
# [Revisor] Gramática: X correções encontradas
# [Revisor] Estilo: X ajustes
# [Revisor] Fatos: X inconsistências de formatação
# [Revisor] SEO: X campos otimizados
# [Revisor] Post 99999: aplicando X correções em Y campos
# [Revisor] Post 99999: PATCH aplicado com sucesso
# [Revisor] Post 99999: revisão registrada

# 4. Verificar no PostgreSQL
psql $DATABASE_URL -c "SELECT * FROM revisoes_realizadas WHERE post_id = 99999;"

# 5. Verificar stats no Redis
redis-cli hgetall revisor:stats:hoje
```

### 14.4 Métricas de Saúde do Revisor

```python
# Métricas esperadas em produção (1000 artigos/dia):

METRICAS_ESPERADAS = {
    "revisoes_por_hora": "40-50",          # ~1000/dia / 24h
    "tempo_medio_revisao_ms": "< 8000",     # < 8 segundos por artigo
    "correcoes_media_por_artigo": "2-8",    # 2 a 8 correções são normais
    "taxa_sucesso_patch": "> 99%",          # Quase nunca falha o PATCH
    "custo_por_revisao_usd": "< 0.003",    # < R$ 0,02 por artigo
    "custo_diario_total_usd": "< 3.00",    # < R$ 18/dia para 1000 artigos
    "erros_fatais_por_hora": "< 1",        # Quase sem erros fatais
}

# Dashboard query:
QUERY_DASHBOARD = """
SELECT
    COUNT(*) AS total_revisoes,
    ROUND(AVG(total_correcoes), 1) AS media_correcoes,
    ROUND(AVG(custo_usd) * 1000, 4) AS custo_medio_mcents,
    ROUND(AVG(duracao_ms) / 1000.0, 2) AS duracao_media_seg,
    SUM(CASE WHEN sucesso THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 AS taxa_sucesso_pct,
    SUM(CASE WHEN patch_aplicado THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 AS taxa_patch_pct
FROM revisoes_realizadas
WHERE revisado_em > NOW() - INTERVAL '1 hour';
"""
```

### 14.5 Resumo de Decisões de Design

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Momento de revisão | PÓS-publicação | Regra #11 do sistema: publicar primeiro |
| LLM tier | PADRÃO | Correção gramatical não exige PREMIUM |
| Número de LLM calls | 3 por revisão (gramática, estilo, SEO) | Equilíbrio custo/qualidade |
| Verificação de fatos | Sem LLM (regex) | Custo zero, sem alucinação |
| Kafka group ID | revisor-consumers | Independente do Fotógrafo |
| Concorrência | Semáforo + Lock Redis | Evita dupla revisão sem bloquear |
| Fallback em erro | Continua sem correções | Não bloqueia pipeline |
| Payload PATCH | Sem "status" | Nunca altera publicação |
| Memória | 3 camadas | Padrão obrigatório da V3 |
| Shutdown | Gracioso | Finaliza revisões em andamento |

---

## APÊNDICE A — REGRAS INVIOLÁVEIS (RESUMO)

```
╔══════════════════════════════════════════════════════════════════╗
║              REGRAS INVIOLÁVEIS DO REVISOR V3                   ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  1. NUNCA rejeita um artigo                                     ║
║  2. NUNCA despublica um artigo                                  ║
║  3. NUNCA inclui "status" no payload do PATCH                   ║
║  4. NUNCA bloqueia o pipeline de publicação                     ║
║  5. NUNCA solicita aprovação humana                             ║
║  6. SEMPRE usa LLM PADRÃO (não PREMIUM)                        ║
║  7. SEMPRE executa node_aplicar_correcoes (mesmo sem erros)     ║
║  8. SEMPRE opera em paralelo com Fotógrafo                      ║
║  9. SEMPRE mantém três camadas de memória                       ║
║  10. SEMPRE consome Kafka como subscriber (não é chamado        ║
║       diretamente pelo Reporter)                                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

## APÊNDICE B — DIFERENÇAS CRÍTICAS V2 vs V3 (REFERÊNCIA RÁPIDA)

```python
# V2 — ERRADO (não implementar)
class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"        # ← NÃO EXISTE NA V3

APPROVE_THRESHOLD = 5.5      # ← NÃO EXISTE NA V3
REVISE_THRESHOLD = 3.5       # ← NÃO EXISTE NA V3

# V2 opera sobre:
article_draft = {...}        # ← draft, NÃO post publicado

# V2 LLM:
task_type="quality_review"   # ← roteado para PREMIUM na V2
                             # ← PADRÃO na V3


# V3 — CORRETO (implementar assim)
# Sem enum de decisão — sempre corrige
# Sem thresholds — sempre aplica

# V3 opera sobre:
post_id: int                 # ← ID do post JÁ publicado no WordPress

# V3 LLM:
tier=LLMTier.PADRAO,         # ← PADRÃO, não PREMIUM
task_type="revisao_texto",   # ← mapeado para PADRÃO no SmartRouter

# V3 resultado:
await wp_client.patch_post(post_id, payload)  # ← sempre aplica
```

---

*Briefing gerado em 26 de março de 2026 para a IA de implementação.*
*Componente #6 de 9 no sistema brasileira.news V3.*
*Para contexto completo do sistema, consulte `/home/user/workspace/contexto-subagentes.md`.*
