# AUDITORIA DE ENGENHARIA DE CONTEXTO — brasileira.news v2

> **Tipo:** Documento de referência para agentes de IA  
> **Gerado em:** 2026-03-25  
> **Codebase auditado:** `/home/bitnami/versao2/src/newsroom/` (41.145 linhas, 64 arquivos Python)  
> **Framework de referência:** Diretrizes de Engenharia de Contexto brasileira.news v1.0 (`/home/bitnami/context-engineering-brasileira-news.md`)  
> **Aderência medida:** ~35-40%

---

## COMO USAR ESTE DOCUMENTO

Este documento descreve o estado atual do codebase V2 do brasileira.news e lista todos os gaps identificados entre a implementação e as Diretrizes de Engenharia de Contexto. Use-o como base para correções, refatorações ou implementações futuras. Cada finding tem um ID único (F1.1, F2.3, etc.), severidade, e localização exata no código.

**NÃO altere este documento.** Ele é um snapshot da auditoria. Atualize-o apenas ao concluir findings.

---

## ARQUITETURA ATUAL DO CODEBASE

### Estrutura de diretórios relevante

```
versao2/src/newsroom/
├── agents/                 # 20 agentes LangGraph (20 .py, ~20K linhas)
│   ├── base.py             # BaseAgent abstrato (710 linhas)
│   ├── reporter.py         # Repórter (798 linhas)
│   ├── revisor.py          # Revisor/Quality Gate (1.373 linhas)
│   ├── diretor.py          # Diretor de Redação (1.504 linhas)
│   ├── editor_chefe.py     # Editor-Chefe (35K bytes)
│   ├── editor_editoria.py  # Editor de Editoria × 4 (43K bytes)
│   ├── curador_home.py     # Curador Homepage (74K bytes)
│   ├── curador_homepage.py # Curador Homepage v2 (30K bytes)
│   ├── curador_secao.py    # Curador Seção (44K bytes)
│   ├── consolidador.py     # Consolidador multi-fonte (47K bytes)
│   ├── fotografo.py        # Editor Fotografia (42K bytes)
│   ├── focas.py            # Gerente de Fontes (43K bytes)
│   ├── pauteiro.py         # Pauteiro/Assignment Editor (22K bytes)
│   ├── publisher.py        # Publicador WordPress (24K bytes)
│   ├── monitor.py          # Monitor de Sistema (45K bytes)
│   ├── monitor_concorrencia.py  # Monitor Concorrência (41K bytes)
│   ├── analista.py         # Analista de Métricas (46K bytes)
│   ├── qa_imagem.py        # QA de Imagem (42K bytes)
│   └── qa_layout.py        # QA de Layout (53K bytes)
├── llm/
│   ├── gateway.py          # LLM Gateway LiteLLM (2.588 linhas, 101K bytes)
│   └── tiers.py            # 4-Tier system (325 linhas)
├── memory/
│   ├── redis_store.py      # Short-term (18K bytes)
│   ├── pg_store.py         # Medium-term PostgreSQL (39K bytes)
│   └── semantic.py         # Long-term pgvector (28K bytes)
├── pipeline/
│   ├── editorial.py        # Pipeline editorial LangGraph (28K bytes)
│   └── runner.py           # Runner do pipeline (17K bytes)
├── communication/
│   └── pubsub.py           # Redis Pub/Sub EventBus
├── media/
│   ├── cascade.py          # Cascade de imagens 5-tier
│   ├── image_search.py     # Busca de imagens
│   └── query_generator.py  # Gerador de queries
├── monitoring/
│   └── competitor.py       # Monitor de concorrência
├── sources/
│   └── catalog.py          # Catálogo 630+ fontes (559 linhas)
├── migration/
│   ├── bridge.py           # Bridge v1↔v2
│   ├── cutover.py          # Cutover automático
│   └── validator.py        # Validação de paridade
├── utils/
│   ├── logging.py          # Structured logging + LangSmith (893 linhas)
│   └── costs.py            # Cost utilities (19K bytes)
└── config.py               # Settings Pydantic (9K bytes)
```

### Padrões Arquiteturais em Uso

1. **LangGraph StateGraph** em cada agente: `_build_graph()` → `add_node()` → `add_edge()` → `compile()`
2. **Pydantic v2 BaseModel** para todos os states (`AgentState`, `ReporterState`, etc.)
3. **4-Tier LLM routing** via LiteLLM: PREMIUM, REDAÇÃO, ECONÔMICO, MULTIMODAL
4. **34 task types** mapeados para tiers em `TASK_TIER_MAP`
5. **BaseAgent** genérico com: checkpointing, cost tracking, memory hooks (Redis/PG/pgvector), event bus
6. **EventBus** via Redis Pub/Sub para handoff inter-agente
7. **Per-agent daily budgets** com `BudgetExceededError` no gateway
8. **Circuit breaker** por tier (3 failures → 30min cooldown)
9. **Semantic cache** via Redis com TTLs por tier
10. **Batch API** para tasks não-urgentes com 50% discount

### Testes

- **Localização:** `versao2/tests/` — 21 test files + `conftest.py` (17K bytes)
- **Estado:** 12/21 test files falham na coleta (import errors). 0 testes passam.
- **Framework:** pytest + pytest-asyncio (misconfigured — 283 warnings)

---

## FINDINGS — LISTA COMPLETA

### Severidade P0 — Resolver Imediatamente

#### F1.1 — Sem AGENTS.md
- **O que falta:** Arquivo `AGENTS.md` na raiz do repositório descrevendo mapa do sistema, hierarquia de agentes, canais de comunicação, tier LLM por agente.
- **Por que importa:** Agentes de IA (Claude Code, Codex) que trabalham no codebase não têm mapa do sistema. Viola Seção 6 das Diretrizes.
- **Onde criar:** `/home/bitnami/versao2/AGENTS.md`

#### F1.2 — Sem CLAUDE.md
- **O que falta:** Arquivo `CLAUDE.md` com regras globais para assistentes de código.
- **Onde criar:** `/home/bitnami/versao2/CLAUDE.md`

#### F1.3 — Sem `.context.md` por agente
- **O que falta:** Nenhum agente tem arquivo `.context.md` com template Identity/Input Schema/Output Schema/Tools/Token Budget.
- **Por que importa:** Sem context files, cada agente recebe contexto indiferenciado. Viola Seção 4.1 das Diretrizes.
- **Onde criar:** Um `.context.md` dentro de `agents/` para cada agente, ou um diretório `agents/context/`.

#### F2.1 — Sem token budget enforcement
- **O que falta:** Nenhum agente declara ou mede o orçamento de tokens do system prompt contra limites definidos nas Diretrizes (Seção 5.2-5.5).
- **Onde implementar:** Em `BaseAgent._build_graph()` ou via decorator nos system prompts.
- **Referência:** Seção 5.2-5.5 das Diretrizes.

#### F2.3 — Sem AGENT_CONTEXT_FILTERS
- **O que falta:** Agentes recebem todo o state dict, não apenas campos relevantes. Não há filtragem de contexto por agente.
- **Por que importa:** Poluição de contexto = Context Distraction (Patologia §2.4).
- **Onde implementar:** Criar `AGENT_CONTEXT_FILTERS` dict em `config.py` ou `agents/__init__.py` definindo para cada agente quais campos do state são incluídos/excluídos.
- **Referência:** Seção 2.4 das Diretrizes.

#### F6.1-F6.6 — Sem detecção de patologias
- **O que falta:** Nenhum dos 6 detectores de patologias de contexto existe:
  - `ContextRotDetector` — conteúdo desatualizado no contexto
  - `ContextPoisoningDetector` — prompt injection, dados não confiáveis
  - Lost in the Middle — bookending, batch ≤5 itens
  - Context Distraction — `AGENT_CONTEXT_FILTERS`
  - Context Confusion — taxonomia desambiguada
  - Context Clash — hierarquia de confiança `SOURCE_TRUST`
- **Onde implementar:** Novo módulo `newsroom/context/` com detectors.
- **Referência:** Seção 2 das Diretrizes.

#### F8.1 — Suite de testes quebrada
- **Status:** 12/21 test files em `versao2/tests/` falham na coleta (import errors prováveis).
- **Teste exato:** `cd /home/bitnami/versao2 && .venv/bin/python -m pytest tests/ --tb=short -q`
- **Arquivos afetados:** Todos em `tests/test_agents/`, `tests/test_analytics/`, `tests/test_base_agent.py`
- **Provável causa:** Imports quebrados após refatoração, ou dependências faltando no venv.

---

### Severidade P1 — Próximas 2 Semanas

#### F5.1 — gateway.py é god-class
- **Arquivo:** `versao2/src/newsroom/llm/gateway.py` (2.588 linhas, 101K bytes)
- **Problema:** Contém CircuitBreaker, SemanticCache, BatchAPI, BudgetManager, CostTracking tudo no mesmo arquivo.
- **Ação:** Extrair em módulos: `llm/circuit_breaker.py`, `llm/semantic_cache.py`, `llm/batch.py`, `llm/budget.py`.

#### F-ASYNC — asyncio.new_event_loop() anti-pattern
- **Problema:** TODOS os agentes criam event loops novos dentro de steps LangGraph:
  ```python
  def _step_observe(self, state):
      loop = asyncio.new_event_loop()
      try:
          return loop.run_until_complete(self._observe_async(state))
      finally:
          loop.close()
  ```
- **Por que é problema:** LangGraph pode rodar em event loop existente. Criar loops novos causa conflitos, resource leaks, e impede `ainvoke()`.
- **Ação:** Converter todos os step methods para `async def` nativos.
- **Arquivos afetados:** Todos os 20 agentes em `agents/`.

#### F3.1 — Redis Pub/Sub em vez de Streams
- **Arquivo:** `versao2/src/newsroom/communication/pubsub.py`
- **Problema:** Pub/Sub perde mensagens quando subscriber está offline. Streams têm persistência e consumer groups.
- **Referência:** Seção 7.1 das Diretrizes.

#### F3.2 — Sem HANDOFF_SCOPE_MAP
- **O que falta:** Todo o state é passado via EventBus sem filtragem por receiver.
- **Referência:** Seção 7.2 das Diretrizes.

#### F2.2 — Sem bookending
- **O que falta:** Informação crítica não é repetida no início E fim dos system prompts.
- **Referência:** Seção 2.3 das Diretrizes.

#### F2.5 — Sem tool de raciocínio (think/scratchpad)
- **O que falta:** Agentes com decisões complexas (Diretor, Editor-Chefe) não têm área de raciocínio intermediário.
- **Referência:** Seção 3.1.1 das Diretrizes.

#### F5.3 — Sem global daily budget ceiling
- **Problema:** Per-agent budgets existem, mas sem teto global para o sistema inteiro.
- **Onde implementar:** Em `DiretorRedacaoAgent` ou no `LLMGateway`.

#### F8.3 — pytest-asyncio misconfigured
- **Problema:** 283 warnings `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio`.
- **Causa:** `pytest-asyncio` não instalado ou versão incompatível. `pyproject.toml` lista `pytest-asyncio>=0.23` mas pode não estar no venv.

---

### Severidade P2 — Próximas 4 Semanas

#### F4.1 — Temporal weighting incompleto
- **Arquivo:** `versao2/src/newsroom/memory/semantic.py`
- **Problema:** Reporter passa `temporal_weight=0.3` mas a fórmula `score_temporal_combinado` das Diretrizes (half-life 7 dias) não foi encontrada na implementação.
- **Referência:** Seção 8.1.3 das Diretrizes.

#### F4.2 — Sem chunking strategy
- **O que falta:** Chunker semântico (seções > parágrafos > sentenças) para RAG.
- **Referência:** Seção 8.1.1 das Diretrizes.

#### F4.3 — Sem busca híbrida
- **O que falta:** Meilisearch (lexical) + pgvector (semântica) com RRF fusion.
- **Referência:** Seção 8.1 das Diretrizes.

#### F7.1 — Sem Prometheus
- **Problema:** `prometheus_client` não importado em nenhum arquivo. Observabilidade depende exclusivamente de LangSmith.
- **Referência:** Seção 9.1 das Diretrizes.

#### F7.3 — Sem métricas de contexto
- **O que falta:** Métricas `context_tokens_used_total`, `context_utilization_ratio` das Diretrizes.
- **Referência:** Seção 9.1 das Diretrizes.

#### F5.2 — 4 tiers (não 6)
- **Arquivo:** `versao2/src/newsroom/llm/tiers.py`
- **Problema:** Diretrizes definem 6 tiers (0-5), V2 implementa 4 (PREMIUM, REDAÇÃO, ECONÔMICO, MULTIMODAL). Sem tier "streaming" ou "emergency".

#### F5.4 — litellm_config.yaml excessivo
- **Arquivo:** `versao2/litellm_config.yaml` (46K bytes)
- **Problema:** Tamanho sugere duplicações ou configurações redundantes. Revisar e consolidar.

#### F1.6 — VALID_CATEGORIES duplicada
- **Problema:** Lista de 16 categorias definida separadamente em `reporter.py` (L81-98) E `revisor.py` (L120-137).
- **Ação:** Extrair para `newsroom/constants.py` e importar em ambos.

#### F2.4 — Sem auto-compact
- **O que falta:** Sem detecção de janela de contexto a 95% para triggerar compaction automática.
- **Referência:** Seção 3.3 das Diretrizes.

---

### Severidade P3 — Backlog

#### F4.4 — Sem verificação de stale embeddings
- **O que falta:** Job para reindexar conteúdo atualizado no pgvector.

#### F3.3 — Sem narrative casting
- **O que falta:** Output do agente fonte não é reemoldurado como contexto para o receptor.
- **Referência:** Seção 7.3 das Diretrizes.

#### F3.4 — Sem Dead Letter Queue
- **O que falta:** Mensagens falhadas no EventBus não são capturadas.

#### F3.5 — Sem continuity handoff
- **O que falta:** Sem spawn de agente fresco quando contexto atual atinge 90% da janela.
- **Referência:** Seção 4.5 das Diretrizes.

#### F2.6 — Sem staged processing
- **O que falta:** Consolidador e sintetizador não processam em batches de 5.
- **Referência:** Seção 4.3 das Diretrizes.

#### F2.7 — Sem guardrail de tools
- **O que falta:** Sem validação de que nenhum agente tem >30 tools.
- **Referência:** Seção 2.5 das Diretrizes.

#### F9.1 — Credenciais no v1
- **Problema:** `motor_rss/.env`, `motor_scrapers/.env` com keys na raiz.

#### F9.3 — Backfill não executado
- **O que falta:** 9.180 artigos do v1 não indexados no pgvector.

---

## MATRIZ DE CONFORMIDADE

| Seção das Diretrizes | Status | Detalhe |
|---|---|---|
| §2 Patologias (6 tipos) | ❌ Ausente | Nenhum detector implementado |
| §3.1 Write (scratchpads) | ✅ Conforme | Pydantic states funcionam como scratchpads |
| §3.2 Select (RAG/JIT) | ⚠️ Parcial | SemanticMemory existe, sem context filters |
| §3.3 Compress (auto-compact) | ❌ Ausente | Sem detecção de threshold |
| §3.4 Isolate (sub-agents) | ✅ Conforme | 20 agentes isolados |
| §4 Single-turn design | ⚠️ Parcial | LangGraph é multi-step mas sem multi-turn LLM |
| §5 Token budgets | ⚠️ Parcial | max_tokens por tier, sem enforcement por agente |
| §6 AGENTS.md/CLAUDE.md | ❌ Ausente | Nenhum arquivo de documentação |
| §7 Handoff | ⚠️ Parcial | Pub/Sub sem scope/narrative/DLQ |
| §8 RAG pipeline | ⚠️ Parcial | pgvector sem temporal weighting/chunking |
| §9 Observabilidade | ⚠️ Parcial | LangSmith sem Prometheus |

---

## REFERÊNCIAS CRUZADAS

- **Diretrizes completas:** `/home/bitnami/context-engineering-brasileira-news.md`
- **Master Plan V2:** `/home/bitnami/V2_MASTER_PLAN_SUMMARY.md`
- **Bug audits v1:** `/home/bitnami/curator/bugs_*.md` (5 arquivos, ~265K total)
- **Config LiteLLM:** `/home/bitnami/versao2/litellm_config.yaml` (46K)
- **pyproject.toml:** `/home/bitnami/versao2/pyproject.toml`
- **Tests conftest:** `/home/bitnami/versao2/tests/conftest.py` (17K)
