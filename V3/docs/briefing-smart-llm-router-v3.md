# Briefing Completo para IA — SmartLLMRouter V3

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #1 (Prioridade Máxima)
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / LiteLLM / Redis / PostgreSQL / asyncio
**Componente:** `brasileira/llm/smart_router.py` + módulos auxiliares

---

## LEIA ISTO PRIMEIRO — Por que este é o Componente #1

O SmartLLMRouter é a **fundação de todo o sistema multi-agente da brasileira.news V3**. Todos os 9 agentes — Reporter, Fotógrafo, Revisor, Consolidador, Curador, Pauteiro, Editor-Chefe, Monitor Concorrência e Monitor Sistema — dependem dele para fazer chamadas LLM. Se o roteador não funciona, **nada funciona**. Se o roteador trava com um provedor fora, **tudo trava**.

**Volume de produção:** O sistema deve suportar **1.000+ artigos/dia**, cada um exigindo 2-5 chamadas LLM (redação, SEO, revisão, imagem, curadoria). Isso é **2.000 a 5.000 chamadas LLM/dia no mínimo**, distribuídas por 7 provedores, 3 tiers de qualidade, com zero downtime.

**Este briefing contém TUDO que você precisa para implementar o SmartLLMRouter do zero.** Não consulte outros documentos. Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ QUEBRADO NA V2

### 1.1 Problema Central: Roteador Engessado

O sistema V2 tem **dois** roteadores LLM — ambos quebrados de maneiras diferentes:

**Arquivo 1: `brasileira/motor_rss/llm_router.py` (602 linhas)**

Problemas fatais:
1. **Modelos hardcoded e desatualizados:** Usa `gpt-4o`, `claude-sonnet-4-20250514`, `grok-3`, `gemini-2.0-flash`, `gemini-2.5-pro-preview-05-06` — todos desatualizados (março 2026).
2. **Funções separadas por provedor:** Uma função `_call_openai_premium()`, outra `_call_claude_premium()`, outra `_call_grok_premium()`, etc. — são 8 funções quase idênticas com modelo hardcoded dentro de cada uma.
3. **6 cascatas fixas:** `_TIER1_PROVIDERS`, `_TIER2_PROVIDERS`, `_TIER3_PROVIDERS`, `_TIER_CURATOR_PROVIDERS`, `_TIER_CONSOLIDATOR_PROVIDERS`, `_TIER_PHOTO_EDITOR_PROVIDERS` — cada uma é uma lista estática de tuplas `(nome, função, keys)`. Impossível alterar em runtime.
4. **Sem health scoring:** Circuit breaker rudimentar (3 falhas → 30min cooldown) é tudo que existe. Não avalia latência, taxa de sucesso recente, ou custo.
5. **Key rotation fraca:** Round-robin simples sem awareness de rate limit por key.
6. **Síncrono:** Todas as chamadas são bloqueantes. Nenhum uso de async.
7. **Sem downgrade de tier:** Se todos os modelos PREMIUM falham, retorna `None` — não tenta modelos PADRÃO.
8. **JSON parsing acoplado:** O roteador faz parse de JSON e valida campos de artigo dentro do próprio módulo de roteamento. Responsabilidades misturadas.

**Código V2 que exemplifica os problemas (de `llm_router.py`):**

```python
# PROBLEMA 1: Modelo hardcoded dentro da função
def _call_openai_premium(system_prompt: str, user_prompt: str) -> str:
    """GPT-4o completo — melhor qualidade de redação e JSON."""
    key = _next_key("openai", config.OPENAI_KEYS)
    if not key:
        raise ValueError("Nenhuma OPENAI_API_KEY configurada")
    from openai import OpenAI
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model="gpt-4o",  # ← HARDCODED, desatualizado
        messages=[...],
        max_tokens=4096,
        timeout=config.LLM_TIMEOUT,
    )
    return response.choices[0].message.content

# PROBLEMA 2: Cascata fixa, impossível alterar em runtime
_TIER1_PROVIDERS = [
    ("openai:gpt-4o",        _call_openai_premium,  config.OPENAI_KEYS),
    ("claude:sonnet-4",      _call_claude_premium,   config.ANTHROPIC_KEYS),
    ("grok:grok-3",          _call_grok_premium,     config.GROK_KEYS),
    ("gemini:2.5-pro",       _call_gemini_premium,   config.GEMINI_KEYS),
    # Sem Perplexity, sem DeepSeek no Premium, sem Alibaba/Qwen
]

# PROBLEMA 3: Circuit breaker primitivo
CIRCUIT_BREAKER_THRESHOLD = 3    # bloqueia após 3 falhas — muito agressivo
CIRCUIT_BREAKER_COOLDOWN = 1800  # 30 min de cooldown — muito longo!

# PROBLEMA 4: Sem downgrade de tier
def generate_article(title, content, source, categories, url="", tier=2):
    providers = _TIER_MAP.get(tier, _TIER2_PROVIDERS)
    for provider_name, call_fn, keys in providers:
        # tenta cada provedor do tier
        ...
    # Se TODOS falharam:
    logger.error("TODOS os LLMs (TIER %s) falharam para: %s", tier, title[:80])
    return None, ""  # ← RETORNA NONE, não tenta outro tier!
```

**Arquivo 2: `brasileira/roteador_ia.py` (188 linhas)**

Roteador legado ainda mais problemático:
1. **Usa `requests` síncrono** para chamadas HTTP diretas à API Anthropic (nem SDK)
2. **Modelos antigos:** `gpt-4o`, `grok-beta`, `llama-3.1-sonar-large-128k-chat`, `claude-3-5-sonnet-20241022`, `gemini-1.5-pro`
3. **DALL-E desativado:** `return None # [TRAVA EDITORIAL - DALL-E 3 DESATIVADO]` — geração de imagem completamente quebrada
4. **Sem circuit breaker** nenhum, nem key rotation

**Arquivo 3: `brasileira/motor_rss/config.py` (368 linhas)**

Padrões que devemos **manter e evoluir:**
1. **Key loading com `_load_keys()`** — carrega KEY, KEY_2, KEY_3, ..., KEY_9 do .env. Bom padrão. Manter.
2. **Constantes de timeout:** `LLM_TIMEOUT = 60` — vamos reduzir para 30s por tentativa no V3.
3. **Keys de 7 provedores** já declaradas: ANTHROPIC, GEMINI, GROK, PERPLEXITY, OPENAI, DEEPSEEK, QWEN.

### 1.2 Resumo dos Problemas a Resolver

| # | Problema V2 | Solução V3 |
|---|-------------|------------|
| 1 | Modelos hardcoded em funções | LiteLLM como abstração universal — modelo é string de config |
| 2 | 8 funções separadas por provedor | Uma única chamada `litellm.acompletion()` para tudo |
| 3 | Cascatas fixas em código | Pools dinâmicos em Redis, atualizáveis em runtime |
| 4 | Circuit breaker primitivo (3 falhas / 30min) | Health scoring contínuo (0-100) com window de 20 chamadas |
| 5 | Sem health scoring | Score baseado em taxa de sucesso (50%), latência (30%), recência de erros (20%) |
| 6 | Síncrono | 100% async com asyncio + litellm.acompletion |
| 7 | Sem downgrade de tier | Cascata: PREMIUM → PADRÃO → ECONÔMICO → last resort |
| 8 | Key rotation round-robin cega | Key rotation com awareness de rate limit + cooldown por key individual |
| 9 | JSON parsing dentro do roteador | Separação total: roteador retorna texto, quem chamou faz parse |
| 10 | 6 cascatas separadas por função editorial | 3 tiers universais + mapeamento task → tier |

---

## PARTE II — ARQUITETURA DO SmartLLMRouter V3

### 2.1 Visão Geral

```
                   ┌──────────────────────────────┐
                   │     QUALQUER AGENTE           │
                   │  Reporter / Fotógrafo / etc.  │
                   └──────────┬───────────────────┘
                              │
                   route_request(task_type, messages)
                              │
                   ┌──────────▼───────────────────┐
                   │      SmartLLMRouter            │
                   │                                │
                   │  1. Resolve tier via task_type  │
                   │  2. Carrega pool do tier        │
                   │     (Redis → fallback código)   │
                   │  3. Ordena por health score     │
                   │  4. Tenta cada modelo           │
                   │  5. Se tier esgotou → downgrade │
                   │  6. Se TUDO falhou → last resort│
                   └──────────┬───────────────────┘
                              │
              ┌───────────────┼───────────────────┐
              │               │                     │
    ┌─────────▼──┐  ┌────────▼───┐  ┌─────────────▼──────┐
    │  LiteLLM    │  │   Health    │  │   Redis             │
    │  Gateway    │  │   Tracker   │  │   (pools, health,   │
    │  (abstrai   │  │   (scores)  │  │    key states)      │
    │   7 APIs)   │  │             │  │                     │
    └─────────────┘  └─────────────┘  └──────────────────┘
              │
    ┌─────────▼──────────────────────────────────┐
    │  7 PROVEDORES                                │
    │  Anthropic │ OpenAI │ Google │ xAI │          │
    │  Perplexity │ DeepSeek │ Alibaba/Qwen        │
    └──────────────────────────────────────────────┘
```

### 2.2 Princípios OBRIGATÓRIOS

1. **NUNCA hardcoda modelo em código.** Modelos são strings em config (Redis ou YAML). `litellm.acompletion(model="anthropic/claude-sonnet-4-6")`.
2. **Se um provedor falha, tenta TODOS os outros do tier** antes de desistir.
3. **Se o tier inteiro falha, faz downgrade automático** para o tier abaixo (PREMIUM → PADRÃO → ECONÔMICO).
4. **NUNCA retorna erro sem ter tentado todos os 7 provedores** em pelo menos um tier.
5. **Pools de modelos são dinâmicos** — carregáveis de Redis em runtime, sem deploy.
6. **100% async** — todas as chamadas LLM usam `await litellm.acompletion()`.
7. **Nenhum modelo open-source local.** Não temos Llama, Mixtral, etc. Apenas APIs externas.
8. **Health scoring é contínuo** — não binário (ativo/bloqueado), mas um score 0-100 por modelo.

### 2.3 Stack do Componente

| Dependência | Versão | Função |
|-------------|--------|--------|
| `litellm` | `>=1.80.0,!=1.82.7,!=1.82.8` | Gateway LLM universal (7+ provedores com uma única API) |
| `redis[hiredis]` | `>=5.0` | Pools dinâmicos, health scores, key states |
| `asyncpg` | `>=0.29` | Logging de health em PostgreSQL |
| `pydantic` | `>=2.5` | Schemas de configuração e validação |
| `opentelemetry-api` | `>=1.24` | Tracing de chamadas LLM |

**ALERTA DE SEGURANÇA sobre LiteLLM:** As versões 1.82.7 e 1.82.8 do PyPI foram comprometidas por um ataque supply chain em março de 2026. **NUNCA instale essas versões.** Use `litellm>=1.80.0,!=1.82.7,!=1.82.8` no requirements.txt. Se usar Docker, prefira a imagem oficial que não foi afetada.

---

## PARTE III — PROVEDORES E MODELOS (MARÇO 2026)

**IMPORTANTE:** NÃO temos modelos open-source locais. Apenas APIs dos 7 provedores abaixo.

### 3.1 Catálogo Completo

| Provedor | SDK/Prefixo LiteLLM | API Base | Modelos disponíveis |
|----------|---------------------|----------|---------------------|
| **Anthropic** | `anthropic/` | `api.anthropic.com/v1` | claude-opus-4.6, claude-opus-4.5, claude-sonnet-4-6, claude-sonnet-4-5, claude-haiku-4-5, claude-haiku-3-5 |
| **OpenAI** | `openai/` ou sem prefixo | `api.openai.com/v1` | gpt-5.4, gpt-5.2, gpt-4.1, gpt-5.4-mini, gpt-4.1-mini, gpt-5.4-nano, gpt-4.1-nano |
| **Google** | `gemini/` | `generativelanguage.googleapis.com` | gemini-3.1-pro-preview, gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite |
| **xAI** | `xai/` | `api.x.ai/v1` | grok-4, grok-4-1-fast-reasoning, grok-4-1-fast-non-reasoning, grok-3-mini |
| **Perplexity** | `perplexity/` | `api.perplexity.ai` | sonar-pro, sonar |
| **DeepSeek** | `deepseek/` | `api.deepseek.com/v1` | deepseek-chat (V3.2) |
| **Alibaba** | `openai/` (compat) | `dashscope-intl.aliyuncs.com/compatible-mode/v1` | qwen3.5-plus, qwen3.5-flash, qwen-turbo |

### 3.2 Preços (USD por 1M tokens — Input/Output)

| Modelo | Input | Output | Tier Recomendado |
|--------|-------|--------|-----------------|
| Claude Sonnet 4.6 | $3,00 | $15,00 | PREMIUM |
| GPT-5.4 | $2,50 | $15,00 | PREMIUM |
| Gemini 3.1 Pro | $2,00 | $12,00 | PREMIUM |
| Grok 4 | $3,00 | $15,00 | PREMIUM |
| Sonar Pro | $3,00 | $15,00 | PREMIUM |
| Claude Opus 4.6 | $5,00 | $25,00 | PREMIUM (reserva) |
| GPT-5.2 | $1,75 | $14,00 | PREMIUM (reserva) |
| Gemini 2.5 Pro | $2,50* | $15,00* | PREMIUM (reserva) |
| GPT-4.1 Mini | $0,20 | $0,80 | PADRÃO |
| Gemini 2.5 Flash | $0,30 | $2,50 | PADRÃO |
| Grok 4.1 Fast | $0,20 | $0,50 | PADRÃO |
| DeepSeek V3.2 | $0,28 | $0,42 | PADRÃO |
| Qwen3.5 Plus | $0,26 | $1,56 | PADRÃO |
| Claude Haiku 4.5 | $1,00 | $5,00 | PADRÃO |
| GPT-5.4 Mini | $0,75 | $4,50 | PADRÃO |
| Qwen3.5 Flash | $0,07 | $0,26 | ECONÔMICO |
| Gemini 2.5 Flash-Lite | $0,10 | $0,40 | ECONÔMICO |
| GPT-4.1 Nano | $0,05 | $0,20 | ECONÔMICO |
| Grok 4.1 Fast (non-reasoning) | $0,20 | $0,50 | ECONÔMICO |
| Qwen Turbo | $0,03 | $0,13 | ECONÔMICO |
| GPT-5.4 Nano | $0,20 | $1,25 | ECONÔMICO |

*Gemini 2.5 Pro: preço variável conforme tier de uso.

---

## PARTE IV — CONFIGURAÇÃO DOS POOLS POR TIER

### 4.1 Definição dos 3 Tiers

**PREMIUM** — Para tarefas que exigem máxima qualidade editorial:
- Redação de artigos (Reporter)
- Geração de queries de imagem (Fotógrafo)
- Scoring editorial da homepage (Curador)
- Consolidação e síntese (Consolidador)
- Pautas especiais (Pauteiro)

**PADRÃO** — Para tarefas que precisam de competência mas não máxima sofisticação:
- SEO (títulos, meta descriptions, slugs)
- Revisão gramatical e de estilo (Revisor)
- Trending detection (Pauteiro)
- Análise de métricas (Editor-Chefe)

**ECONÔMICO** — Para tarefas simples e repetitivas:
- Classificação de categorias
- Extração de entidades (NER)
- Deduplicação por texto
- Health monitoring

### 4.2 Pools Padrão (Defaults em Código)

Estes são os valores padrão codificados. Podem ser sobrescritos em runtime via Redis.

```python
DEFAULT_TIER_POOLS: dict[str, list[dict]] = {
    "premium": [
        {"provider": "anthropic", "model": "claude-sonnet-4-6", "weight": 1.0},
        {"provider": "openai", "model": "gpt-5.4", "weight": 1.0},
        {"provider": "google", "model": "gemini-3.1-pro-preview", "weight": 1.0},
        {"provider": "xai", "model": "grok-4", "weight": 1.0},
        {"provider": "perplexity", "model": "sonar-pro", "weight": 0.8},
        # Reservas (usados quando os primários estão com health baixo)
        {"provider": "anthropic", "model": "claude-opus-4.6", "weight": 0.5},
        {"provider": "openai", "model": "gpt-5.2", "weight": 0.5},
        {"provider": "google", "model": "gemini-2.5-pro", "weight": 0.5},
    ],
    "padrao": [
        {"provider": "openai", "model": "gpt-4.1-mini", "weight": 1.0},
        {"provider": "google", "model": "gemini-2.5-flash", "weight": 1.0},
        {"provider": "xai", "model": "grok-4-1-fast-reasoning", "weight": 1.0},
        {"provider": "deepseek", "model": "deepseek-chat", "weight": 1.0},
        {"provider": "alibaba", "model": "qwen3.5-plus", "weight": 1.0},
        {"provider": "anthropic", "model": "claude-haiku-4-5", "weight": 0.8},
        {"provider": "openai", "model": "gpt-5.4-mini", "weight": 0.8},
    ],
    "economico": [
        {"provider": "alibaba", "model": "qwen3.5-flash", "weight": 1.0},
        {"provider": "deepseek", "model": "deepseek-chat", "weight": 1.0},
        {"provider": "google", "model": "gemini-2.5-flash-lite", "weight": 1.0},
        {"provider": "openai", "model": "gpt-4.1-nano", "weight": 1.0},
        {"provider": "xai", "model": "grok-4-1-fast-non-reasoning", "weight": 0.8},
        {"provider": "alibaba", "model": "qwen-turbo", "weight": 0.8},
        {"provider": "openai", "model": "gpt-5.4-nano", "weight": 0.7},
    ],
}
```

### 4.3 Mapeamento Task → Tier

```python
TASK_TIER_MAP: dict[str, str] = {
    # PREMIUM — qualidade editorial máxima
    "redacao_artigo": "premium",
    "imagem_query": "premium",
    "homepage_scoring": "premium",
    "consolidacao_sintese": "premium",
    "pauta_especial": "premium",

    # PADRÃO — competência sem custo máximo
    "seo_otimizacao": "padrao",
    "revisao_texto": "padrao",
    "trending_detection": "padrao",
    "analise_metricas": "padrao",
    "gap_analysis": "padrao",

    # ECONÔMICO — tarefas simples e repetitivas
    "classificacao_categoria": "economico",
    "extracao_entidades": "economico",
    "deduplicacao_texto": "economico",
    "monitoring_health": "economico",
    "summarize_short": "economico",
}

# Tier padrão se task_type não está no mapa
DEFAULT_TIER = "padrao"
```

### 4.4 Cascata de Downgrade

```
PREMIUM (falhou todos) → PADRÃO (falhou todos) → ECONÔMICO (falhou todos) → last_resort_any_model()
```

A função `last_resort_any_model()` tenta **qualquer modelo de qualquer tier** que tenha health > 0, ignorando tier assignment. É a última barreira antes de retornar erro.

---

## PARTE V — HEALTH SCORING DINÂMICO

### 5.1 Princípios

- Cada **modelo individual** (não provedor) tem um health score de 0 a 100.
- Score é calculado sobre as **últimas 20 chamadas** feitas a esse modelo.
- Score < 30 → modelo é **deprioritizado** (vai para o final da fila, mas NÃO excluído).
- Score = 0 → modelo é **skippado** por 5 minutos (cooldown), depois recebe uma tentativa (half-open).
- Score é armazenado em **Redis** com TTL de 1 hora.
- Todas as chamadas (sucesso e falha) são logadas em **PostgreSQL** para análise histórica.

### 5.2 Fórmula do Health Score

```python
def calculate_health_score(model_id: str, recent_calls: list[CallRecord]) -> float:
    """
    Score 0-100 baseado em 3 fatores:
    - 50% = Taxa de sucesso nas últimas 20 chamadas
    - 30% = Fator de latência (menor = melhor)
    - 20% = Tempo desde o último erro (mais tempo = melhor)
    """
    if not recent_calls:
        return 70.0  # Score neutro para modelos sem histórico

    total = len(recent_calls)
    successes = sum(1 for c in recent_calls if c.success)

    # Fator 1: Taxa de sucesso (50%)
    success_rate = successes / total
    success_score = success_rate * 50

    # Fator 2: Latência média (30%)
    # Normalizado: 0s = 30 pontos, 30s+ = 0 pontos
    avg_latency = mean(c.latency_ms for c in recent_calls if c.success) / 1000
    latency_factor = 1.0 - min(avg_latency / 30.0, 1.0)
    latency_score = latency_factor * 30

    # Fator 3: Recência do último erro (20%)
    # 0s desde erro = 0 pontos, 5min+ = 20 pontos
    last_error = max(
        (c.timestamp for c in recent_calls if not c.success),
        default=None
    )
    if last_error is None:
        recency_score = 20.0  # Sem erros = score máximo
    else:
        seconds_since = (now() - last_error).total_seconds()
        recency_score = min(seconds_since / 300, 1.0) * 20

    return success_score + latency_score + recency_score
```

### 5.3 Redis Keys para Health

```
health:{provider}:{model}:score     → FLOAT (score 0-100)    TTL: 1h
health:{provider}:{model}:calls     → LIST (últimas 20)      TTL: 1h
health:{provider}:{model}:cooldown  → STRING "1"             TTL: 5min (se score=0)
```

### 5.4 PostgreSQL para Health Log (Análise Histórica)

```sql
CREATE TABLE llm_health_log (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd FLOAT,
    error_type VARCHAR(50),       -- 'rate_limit', 'timeout', 'auth', 'server_error', 'invalid_response'
    error_message TEXT,
    task_type VARCHAR(50),        -- 'redacao_artigo', 'seo_otimizacao', etc.
    tier VARCHAR(20),             -- 'premium', 'padrao', 'economico'
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_health_recent ON llm_health_log(provider, model, timestamp DESC);
CREATE INDEX idx_health_task ON llm_health_log(task_type, timestamp DESC);
CREATE INDEX idx_health_errors ON llm_health_log(success, timestamp DESC) WHERE NOT success;
```

---

## PARTE VI — CARREGAMENTO DE CHAVES

### 6.1 Padrão Existente (MANTER)

O sistema V2 já tem um bom padrão de carregamento de keys em `config.py`. Manter e evoluir:

```python
# config.py V2 (FUNCIONAL, manter padrão)
def _load_keys(prefix: str) -> list[str]:
    """Carrega todas as keys de um provider (KEY, KEY_2, KEY_3, ...)."""
    keys = []
    base = os.getenv(prefix, "")
    if base:
        keys.append(base)
    for i in range(2, 10):
        k = os.getenv(f"{prefix}_{i}", "")
        if k:
            keys.append(k)
    return keys

ANTHROPIC_KEYS = _load_keys("ANTHROPIC_API_KEY")
GEMINI_KEYS = _load_keys("GEMINI_API_KEY")
GROK_KEYS = _load_keys("GROK_API_KEY")
PERPLEXITY_KEYS = _load_keys("PERPLEXITY_API_KEY")
OPENAI_KEYS = _load_keys("OPENAI_API_KEY")
DEEPSEEK_KEYS = _load_keys("DEEPSEEK_API_KEY")
QWEN_KEYS = _load_keys("QWEN_API_KEY")
```

### 6.2 Evolução V3: Provider Config Completo

```python
from pydantic import BaseModel
from typing import Optional

class ProviderConfig(BaseModel):
    """Configuração de um provedor LLM."""
    name: str                          # "anthropic", "openai", etc.
    api_keys: list[str]                # Lista de keys (rotação)
    api_base: Optional[str] = None     # Base URL custom (Qwen, Grok, DeepSeek)
    max_rpm: Optional[int] = None      # Rate limit requests/min (se conhecido)
    max_tpm: Optional[int] = None      # Rate limit tokens/min (se conhecido)
    enabled: bool = True               # Pode ser desabilitado em runtime

# Carregamento
PROVIDERS: dict[str, ProviderConfig] = {
    "anthropic": ProviderConfig(
        name="anthropic",
        api_keys=_load_keys("ANTHROPIC_API_KEY"),
    ),
    "openai": ProviderConfig(
        name="openai",
        api_keys=_load_keys("OPENAI_API_KEY"),
    ),
    "google": ProviderConfig(
        name="google",
        api_keys=_load_keys("GEMINI_API_KEY"),
    ),
    "xai": ProviderConfig(
        name="xai",
        api_keys=_load_keys("GROK_API_KEY"),
        api_base="https://api.x.ai/v1",
    ),
    "perplexity": ProviderConfig(
        name="perplexity",
        api_keys=_load_keys("PERPLEXITY_API_KEY"),
        api_base="https://api.perplexity.ai",
    ),
    "deepseek": ProviderConfig(
        name="deepseek",
        api_keys=_load_keys("DEEPSEEK_API_KEY"),
        api_base="https://api.deepseek.com/v1",
    ),
    "alibaba": ProviderConfig(
        name="alibaba",
        api_keys=_load_keys("QWEN_API_KEY"),
        api_base="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    ),
}
```

### 6.3 Formato do .env

```bash
# === CHAVES LLM (suporta múltiplas por provedor para rotação) ===

# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-xxxx
ANTHROPIC_API_KEY_2=sk-ant-yyyy
ANTHROPIC_API_KEY_3=sk-ant-zzzz

# OpenAI (GPT)
OPENAI_API_KEY=sk-xxxx
OPENAI_API_KEY_2=sk-yyyy

# Google (Gemini)
GEMINI_API_KEY=AIzaSyxxxx
GEMINI_API_KEY_2=AIzaSyyyy

# xAI (Grok)
GROK_API_KEY=xai-xxxx
GROK_API_KEY_2=xai-yyyy

# Perplexity (Sonar)
PERPLEXITY_API_KEY=pplx-xxxx

# DeepSeek
DEEPSEEK_API_KEY=sk-xxxx

# Alibaba Cloud (Qwen)
QWEN_API_KEY=sk-xxxx

# === REDIS ===
REDIS_URL=redis://localhost:6379/0

# === POSTGRESQL ===
DATABASE_URL=postgresql://user:pass@localhost:5432/brasileira_v3

# === TIMEOUTS ===
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES_PER_MODEL=1
```

---

## PARTE VII — IMPLEMENTAÇÃO COMPLETA

### 7.1 Estrutura de Arquivos

```
brasileira/
├── llm/
│   ├── __init__.py
│   ├── smart_router.py          # Classe principal SmartLLMRouter
│   ├── health_tracker.py        # ProviderHealthTracker
│   ├── key_manager.py           # Gerenciamento de keys com rotação
│   ├── tier_config.py           # Pools e mapeamento task→tier
│   ├── models.py                # Pydantic models (request/response)
│   └── exceptions.py            # Exceções customizadas
├── config/
│   ├── __init__.py
│   ├── settings.py              # Configurações gerais (evolução do config.py V2)
│   └── providers.py             # ProviderConfig para os 7 provedores
└── integrations/
    ├── redis_client.py          # Redis async client
    └── postgres_client.py       # PostgreSQL async client
```

### 7.2 Modelos Pydantic (`llm/models.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class TierName(str, Enum):
    PREMIUM = "premium"
    PADRAO = "padrao"
    ECONOMICO = "economico"


class LLMRequest(BaseModel):
    """Request para o SmartLLMRouter."""
    task_type: str                              # "redacao_artigo", "seo_otimizacao", etc.
    messages: list[dict]                        # [{"role": "system", ...}, {"role": "user", ...}]
    temperature: float = 0.3
    max_tokens: int = 4096
    response_format: Optional[dict] = None      # {"type": "json_object"} se necessário
    timeout: int = 30                            # Timeout por tentativa em segundos
    trace_id: Optional[str] = None              # Para observabilidade


class LLMResponse(BaseModel):
    """Response do SmartLLMRouter."""
    content: str                                # Texto gerado
    provider: str                               # "anthropic", "openai", etc.
    model: str                                  # "claude-sonnet-4-6", "gpt-5.4", etc.
    tier_used: TierName                         # Tier efetivamente usado
    tier_requested: TierName                    # Tier originalmente solicitado
    downgraded: bool = False                    # True se houve downgrade de tier
    latency_ms: int                             # Latência da chamada em ms
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    trace_id: Optional[str] = None


class CallRecord(BaseModel):
    """Registro de uma chamada LLM para health tracking."""
    provider: str
    model: str
    success: bool
    latency_ms: int
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    task_type: str
    tier: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ModelPoolEntry(BaseModel):
    """Entrada no pool de modelos de um tier."""
    provider: str
    model: str
    weight: float = 1.0                         # Peso para priorização
```

### 7.3 Exceções (`llm/exceptions.py`)

```python
class LLMRouterError(Exception):
    """Erro base do roteador."""
    pass


class AllProvidersFailedError(LLMRouterError):
    """Todos os provedores falharam em todos os tiers."""
    def __init__(self, task_type: str, tiers_attempted: list[str], errors: list[dict]):
        self.task_type = task_type
        self.tiers_attempted = tiers_attempted
        self.errors = errors
        super().__init__(
            f"Todos os provedores falharam para {task_type}. "
            f"Tiers tentados: {tiers_attempted}. "
            f"Total de erros: {len(errors)}"
        )


class NoKeysConfiguredError(LLMRouterError):
    """Nenhuma key configurada para o provedor."""
    pass
```

### 7.4 Health Tracker (`llm/health_tracker.py`)

```python
import time
import json
import logging
from statistics import mean
from typing import Optional
from datetime import datetime, timezone

import redis.asyncio as redis

from .models import CallRecord

logger = logging.getLogger("brasileira.llm.health")

# Constantes
HEALTH_WINDOW_SIZE = 20          # Últimas N chamadas para cálculo
HEALTH_TTL_SECONDS = 3600        # TTL do score no Redis (1h)
COOLDOWN_TTL_SECONDS = 300       # Cooldown quando score=0 (5min)
DEPRIORITIZE_THRESHOLD = 30      # Score abaixo disso = deprioritizado
COOLDOWN_THRESHOLD = 0           # Score igual a isso = cooldown
DEFAULT_HEALTH_SCORE = 70.0      # Score para modelos sem histórico


class ProviderHealthTracker:
    """
    Rastreia health score (0-100) por modelo individual.
    
    Score composto de:
    - 50% = Taxa de sucesso nas últimas 20 chamadas
    - 30% = Fator de latência (menor = melhor)
    - 20% = Tempo desde o último erro (mais tempo = melhor)
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def _score_key(self, provider: str, model: str) -> str:
        return f"health:{provider}:{model}:score"

    def _calls_key(self, provider: str, model: str) -> str:
        return f"health:{provider}:{model}:calls"

    def _cooldown_key(self, provider: str, model: str) -> str:
        return f"health:{provider}:{model}:cooldown"

    async def record_call(self, record: CallRecord) -> float:
        """
        Registra uma chamada (sucesso ou falha) e recalcula o health score.
        Retorna o novo score.
        """
        calls_key = self._calls_key(record.provider, record.model)
        score_key = self._score_key(record.provider, record.model)
        cooldown_key = self._cooldown_key(record.provider, record.model)

        # Serializa e adiciona ao final da lista
        call_data = json.dumps({
            "success": record.success,
            "latency_ms": record.latency_ms,
            "timestamp": record.timestamp.isoformat(),
            "error_type": record.error_type,
        })

        pipe = self.redis.pipeline()
        pipe.rpush(calls_key, call_data)
        pipe.ltrim(calls_key, -HEALTH_WINDOW_SIZE, -1)  # Mantém só as últimas N
        pipe.expire(calls_key, HEALTH_TTL_SECONDS)
        await pipe.execute()

        # Recalcula score
        new_score = await self._calculate_score(record.provider, record.model)

        # Salva score
        await self.redis.set(score_key, str(new_score), ex=HEALTH_TTL_SECONDS)

        # Gerencia cooldown
        if new_score <= COOLDOWN_THRESHOLD:
            await self.redis.set(cooldown_key, "1", ex=COOLDOWN_TTL_SECONDS)
            logger.warning(
                "Modelo %s/%s em COOLDOWN (score=%.1f). Será reativado em %ds.",
                record.provider, record.model, new_score, COOLDOWN_TTL_SECONDS
            )
        elif await self.redis.exists(cooldown_key):
            # Score subiu: remover cooldown
            await self.redis.delete(cooldown_key)

        return new_score

    async def get_health_score(self, provider: str, model: str) -> float:
        """Retorna o health score atual. Default 70 se não há histórico."""
        score_key = self._score_key(provider, model)
        raw = await self.redis.get(score_key)
        if raw is None:
            return DEFAULT_HEALTH_SCORE
        return float(raw)

    async def is_in_cooldown(self, provider: str, model: str) -> bool:
        """Verifica se o modelo está em cooldown (score=0)."""
        cooldown_key = self._cooldown_key(provider, model)
        return bool(await self.redis.exists(cooldown_key))

    async def _calculate_score(self, provider: str, model: str) -> float:
        """Calcula health score 0-100 baseado nas últimas N chamadas."""
        calls_key = self._calls_key(provider, model)
        raw_calls = await self.redis.lrange(calls_key, 0, -1)

        if not raw_calls:
            return DEFAULT_HEALTH_SCORE

        calls = [json.loads(c) for c in raw_calls]
        total = len(calls)
        successes = sum(1 for c in calls if c["success"])

        # Fator 1: Taxa de sucesso (50%)
        success_rate = successes / total
        success_score = success_rate * 50

        # Fator 2: Latência média das chamadas com sucesso (30%)
        successful_latencies = [c["latency_ms"] for c in calls if c["success"]]
        if successful_latencies:
            avg_latency_s = mean(successful_latencies) / 1000.0
            latency_factor = 1.0 - min(avg_latency_s / 30.0, 1.0)
        else:
            latency_factor = 0.0
        latency_score = latency_factor * 30

        # Fator 3: Tempo desde o último erro (20%)
        error_timestamps = [
            datetime.fromisoformat(c["timestamp"])
            for c in calls if not c["success"]
        ]
        if not error_timestamps:
            recency_score = 20.0  # Sem erros = score máximo
        else:
            last_error = max(error_timestamps)
            now = datetime.now(timezone.utc)
            if last_error.tzinfo is None:
                last_error = last_error.replace(tzinfo=timezone.utc)
            seconds_since = (now - last_error).total_seconds()
            recency_score = min(seconds_since / 300, 1.0) * 20

        return round(success_score + latency_score + recency_score, 1)

    async def get_all_scores(self) -> dict[str, float]:
        """Retorna todos os scores (para dashboard/monitoring)."""
        scores = {}
        # Escaneia keys health:*:score
        async for key in self.redis.scan_iter("health:*:score"):
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(":")
            if len(parts) == 4:
                provider, model = parts[1], parts[2]
                raw = await self.redis.get(key)
                if raw:
                    scores[f"{provider}/{model}"] = float(raw)
        return scores
```

### 7.5 Key Manager (`llm/key_manager.py`)

```python
import logging
import time
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger("brasileira.llm.keys")

# Constantes
KEY_COOLDOWN_SECONDS = 120       # Cooldown por key individual após rate limit
KEY_ROTATION_TTL = 3600          # TTL do estado de rotação no Redis


class KeyManager:
    """
    Gerencia rotação de API keys por provedor.
    
    Melhoria sobre V2:
    - Key rotation com awareness de rate limit (V2 era round-robin cego)
    - Cooldown individual por key (V2 bloqueava o provedor inteiro)
    - Estado persistido em Redis (V2 era in-memory, perdido em restart)
    """

    def __init__(self, redis_client: redis.Redis, provider_keys: dict[str, list[str]]):
        """
        Args:
            provider_keys: {"anthropic": ["sk-1", "sk-2"], "openai": ["sk-a", "sk-b"], ...}
        """
        self.redis = redis_client
        self.provider_keys = provider_keys

    def _index_key(self, provider: str) -> str:
        return f"keys:{provider}:index"

    def _cooldown_key(self, provider: str, key_index: int) -> str:
        return f"keys:{provider}:{key_index}:cooldown"

    async def get_next_key(self, provider: str) -> Optional[str]:
        """
        Retorna a próxima key disponível (não em cooldown) para o provedor.
        Usa rotação round-robin, pulando keys em cooldown.
        Retorna None se todas as keys estão em cooldown.
        """
        keys = self.provider_keys.get(provider, [])
        if not keys:
            return None

        # Obtém índice atual e incrementa atomicamente
        index_key = self._index_key(provider)
        current = await self.redis.incr(index_key)
        await self.redis.expire(index_key, KEY_ROTATION_TTL)

        # Tenta cada key, começando pela próxima na rotação
        for offset in range(len(keys)):
            idx = (current + offset) % len(keys)
            cooldown_key = self._cooldown_key(provider, idx)

            if not await self.redis.exists(cooldown_key):
                return keys[idx]

        # Todas em cooldown — retorna a mais antiga (que deve sair de cooldown primeiro)
        logger.warning(
            "Todas as %d keys do provedor %s estão em cooldown!",
            len(keys), provider
        )
        return keys[current % len(keys)]  # Fallback: retorna mesmo em cooldown

    async def mark_rate_limited(self, provider: str, key: str) -> None:
        """Marca uma key como rate-limited (cooldown individual)."""
        keys = self.provider_keys.get(provider, [])
        try:
            idx = keys.index(key)
        except ValueError:
            return

        cooldown_key = self._cooldown_key(provider, idx)
        await self.redis.set(cooldown_key, "1", ex=KEY_COOLDOWN_SECONDS)
        logger.info(
            "Key #%d do %s em cooldown por %ds (rate limit).",
            idx + 1, provider, KEY_COOLDOWN_SECONDS
        )

    async def mark_billing_exhausted(self, provider: str, key: str) -> None:
        """Marca key com erro de billing (cooldown longo)."""
        keys = self.provider_keys.get(provider, [])
        try:
            idx = keys.index(key)
        except ValueError:
            return

        # Cooldown de 1h para erros de billing (crédito insuficiente)
        cooldown_key = self._cooldown_key(provider, idx)
        await self.redis.set(cooldown_key, "billing", ex=3600)
        logger.warning(
            "Key #%d do %s BLOQUEADA por 1h (billing/crédito).",
            idx + 1, provider
        )

    async def get_available_key_count(self, provider: str) -> int:
        """Retorna quantas keys estão disponíveis (não em cooldown)."""
        keys = self.provider_keys.get(provider, [])
        available = 0
        for idx in range(len(keys)):
            if not await self.redis.exists(self._cooldown_key(provider, idx)):
                available += 1
        return available
```

### 7.6 SmartLLMRouter — Classe Principal (`llm/smart_router.py`)

```python
import time
import json
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

import litellm
import redis.asyncio as redis

from .models import (
    LLMRequest, LLMResponse, CallRecord,
    ModelPoolEntry, TierName,
)
from .health_tracker import ProviderHealthTracker, DEPRIORITIZE_THRESHOLD
from .key_manager import KeyManager
from .tier_config import DEFAULT_TIER_POOLS, TASK_TIER_MAP, DEFAULT_TIER
from .exceptions import AllProvidersFailedError, NoKeysConfiguredError

logger = logging.getLogger("brasileira.llm.router")

# Classificação de erros para tratamento adequado
RATE_LIMIT_KEYWORDS = ("rate_limit", "rate limit", "quota", "too many requests", "429", "resource_exhausted")
BILLING_KEYWORDS = ("credit", "insufficient_quota", "billing", "exceeded your current quota", "payment")
AUTH_KEYWORDS = ("401", "unauthorized", "invalid_api_key", "authentication", "permission")
TIMEOUT_KEYWORDS = ("timeout", "timed out", "deadline exceeded")

# Ordem de downgrade
TIER_DOWNGRADE: dict[str, Optional[str]] = {
    "premium": "padrao",
    "padrao": "economico",
    "economico": None,  # Sem mais downgrade
}

# Desabilitar logs verbosos do litellm
litellm.suppress_debug_info = True


class SmartLLMRouter:
    """
    Roteador LLM inteligente para brasileira.news V3.

    Princípios:
    1. NUNCA hardcoda modelo — escolhe MELHOR DISPONÍVEL do tier
    2. Se provedor falha → tenta TODOS antes de desistir
    3. Se tier inteiro falha → downgrade automático
    4. NUNCA retorna erro sem ter tentado todos os provedores
    5. Pools dinâmicos — atualizáveis via Redis em runtime

    Uso:
        router = SmartLLMRouter(redis_client, provider_keys, pg_pool)
        response = await router.route_request(LLMRequest(
            task_type="redacao_artigo",
            messages=[
                {"role": "system", "content": "Você é um jornalista..."},
                {"role": "user", "content": "Reescreva: ..."},
            ],
        ))
        print(response.content)  # Texto gerado
        print(response.model)    # "claude-sonnet-4-6" (ou o que foi usado)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        provider_keys: dict[str, list[str]],
        pg_pool=None,  # asyncpg pool (opcional, para logging em PostgreSQL)
    ):
        self.redis = redis_client
        self.health_tracker = ProviderHealthTracker(redis_client)
        self.key_manager = KeyManager(redis_client, provider_keys)
        self.pg_pool = pg_pool
        self.provider_keys = provider_keys

    # ─── API PÚBLICA ─────────────────────────────────

    async def route_request(self, request: LLMRequest) -> LLMResponse:
        """
        Rota uma request LLM para o melhor modelo disponível.
        
        Fluxo:
        1. Resolve tier via task_type
        2. Tenta todos os modelos do tier, ordenados por health
        3. Se tier esgotou → downgrade
        4. Se TUDO falhou → last resort com qualquer modelo
        5. Se realmente TUDO falhou → levanta AllProvidersFailedError
        """
        tier_requested = self._resolve_tier(request.task_type)
        all_errors: list[dict] = []
        tiers_attempted: list[str] = []

        # Tenta o tier solicitado + downgrades
        current_tier: Optional[str] = tier_requested
        while current_tier is not None:
            tiers_attempted.append(current_tier)
            result = await self._try_tier(request, current_tier, tier_requested, all_errors)
            if result is not None:
                return result

            # Downgrade
            next_tier = TIER_DOWNGRADE.get(current_tier)
            if next_tier:
                logger.warning(
                    "Tier %s esgotado para %s. Downgrade para %s.",
                    current_tier, request.task_type, next_tier
                )
            current_tier = next_tier

        # Last resort: qualquer modelo com health > 0
        logger.warning(
            "Todos os tiers falharam para %s. Tentando last resort.",
            request.task_type
        )
        result = await self._last_resort(request, tier_requested, all_errors)
        if result is not None:
            return result

        # Falha total
        raise AllProvidersFailedError(
            task_type=request.task_type,
            tiers_attempted=tiers_attempted,
            errors=all_errors,
        )

    async def route_request_safe(self, request: LLMRequest) -> Optional[LLMResponse]:
        """
        Versão safe que retorna None em vez de levantar exceção.
        Útil para tarefas onde falha do LLM não deve bloquear o pipeline.
        """
        try:
            return await self.route_request(request)
        except AllProvidersFailedError as e:
            logger.error("route_request_safe: %s", e)
            return None

    # ─── RESOLUÇÃO DE TIER ──────────────────────────

    def _resolve_tier(self, task_type: str) -> str:
        """Resolve qual tier usar baseado no tipo de tarefa."""
        return TASK_TIER_MAP.get(task_type, DEFAULT_TIER)

    # ─── CARREGAMENTO DE POOLS ──────────────────────

    async def _load_pool(self, tier: str) -> list[ModelPoolEntry]:
        """
        Carrega pool de modelos para o tier.
        Prioridade: Redis (runtime) → Default (código).
        """
        redis_key = f"llm:tier_pools:{tier}"
        raw = await self.redis.get(redis_key)

        if raw:
            try:
                pool_data = json.loads(raw)
                return [ModelPoolEntry(**entry) for entry in pool_data]
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Erro ao carregar pool do Redis para tier %s: %s. Usando default.", tier, e)

        # Fallback: pool default do código
        default_pool = DEFAULT_TIER_POOLS.get(tier, DEFAULT_TIER_POOLS["padrao"])
        return [ModelPoolEntry(**entry) for entry in default_pool]

    # ─── ORDENAÇÃO POR HEALTH ───────────────────────

    async def _rank_pool(self, pool: list[ModelPoolEntry]) -> list[ModelPoolEntry]:
        """
        Ordena o pool por: health score (desc), weight (desc).
        Remove modelos em cooldown.
        """
        scored: list[tuple[float, float, ModelPoolEntry]] = []

        for entry in pool:
            # Verifica cooldown
            if await self.health_tracker.is_in_cooldown(entry.provider, entry.model):
                logger.debug("Modelo %s/%s em cooldown — pulando.", entry.provider, entry.model)
                continue

            # Verifica se há keys para o provedor
            if not self.provider_keys.get(entry.provider):
                logger.debug("Sem keys para %s — pulando.", entry.provider)
                continue

            score = await self.health_tracker.get_health_score(entry.provider, entry.model)
            scored.append((score, entry.weight, entry))

        # Ordena por score desc, weight desc
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        ranked = [entry for _, _, entry in scored]

        if not ranked:
            # Se todos estão em cooldown, tenta todos mesmo assim (último recurso do tier)
            logger.warning("Todos os modelos do pool estão em cooldown. Tentando todos.")
            return pool

        return ranked

    # ─── TENTATIVA DE TIER ──────────────────────────

    async def _try_tier(
        self,
        request: LLMRequest,
        tier: str,
        tier_requested: str,
        all_errors: list[dict],
    ) -> Optional[LLMResponse]:
        """Tenta todos os modelos de um tier. Retorna None se todos falharam."""
        pool = await self._load_pool(tier)
        ranked_pool = await self._rank_pool(pool)

        for entry in ranked_pool:
            result = await self._try_model(request, entry, tier, tier_requested, all_errors)
            if result is not None:
                return result

        return None

    # ─── TENTATIVA DE MODELO INDIVIDUAL ─────────────

    async def _try_model(
        self,
        request: LLMRequest,
        entry: ModelPoolEntry,
        tier: str,
        tier_requested: str,
        all_errors: list[dict],
    ) -> Optional[LLMResponse]:
        """Tenta um modelo específico. Retorna None se falhou."""
        # Obtém key
        api_key = await self.key_manager.get_next_key(entry.provider)
        if not api_key:
            logger.debug("Sem key disponível para %s.", entry.provider)
            return None

        # Monta o model string para litellm
        litellm_model = self._build_litellm_model(entry)

        # Monta kwargs para litellm
        litellm_kwargs = self._build_litellm_kwargs(entry, api_key, request)

        start_ms = int(time.time() * 1000)

        try:
            logger.info(
                "[%s] Tentando %s/%s [tier: %s]",
                request.task_type, entry.provider, entry.model, tier
            )

            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=litellm_model,
                    messages=request.messages,
                    **litellm_kwargs,
                ),
                timeout=request.timeout,
            )

            elapsed_ms = int(time.time() * 1000) - start_ms
            content = response.choices[0].message.content or ""
            usage = response.usage

            # Registra sucesso
            record = CallRecord(
                provider=entry.provider,
                model=entry.model,
                success=True,
                latency_ms=elapsed_ms,
                tokens_in=usage.prompt_tokens if usage else None,
                tokens_out=usage.completion_tokens if usage else None,
                cost_usd=self._estimate_cost(entry, usage),
                task_type=request.task_type,
                tier=tier,
            )
            await self._record_call(record)

            logger.info(
                "[%s] Sucesso via %s/%s em %dms [tier: %s]",
                request.task_type, entry.provider, entry.model, elapsed_ms, tier
            )

            return LLMResponse(
                content=content,
                provider=entry.provider,
                model=entry.model,
                tier_used=TierName(tier),
                tier_requested=TierName(tier_requested),
                downgraded=(tier != tier_requested),
                latency_ms=elapsed_ms,
                tokens_in=usage.prompt_tokens if usage else None,
                tokens_out=usage.completion_tokens if usage else None,
                cost_usd=self._estimate_cost(entry, usage),
                trace_id=request.trace_id,
            )

        except asyncio.TimeoutError:
            elapsed_ms = int(time.time() * 1000) - start_ms
            self._log_and_record_error(
                entry, elapsed_ms, "timeout",
                f"Timeout após {request.timeout}s",
                request, tier, all_errors, api_key
            )
            return None

        except Exception as e:
            elapsed_ms = int(time.time() * 1000) - start_ms
            error_msg = str(e).lower()
            error_type = self._classify_error(error_msg)

            # Tratamento especial por tipo de erro
            if error_type == "rate_limit":
                await self.key_manager.mark_rate_limited(entry.provider, api_key)
            elif error_type == "billing":
                await self.key_manager.mark_billing_exhausted(entry.provider, api_key)
            elif error_type == "auth":
                await self.key_manager.mark_billing_exhausted(entry.provider, api_key)

            self._log_and_record_error(
                entry, elapsed_ms, error_type,
                str(e)[:500], request, tier, all_errors, api_key
            )
            return None

    # ─── LAST RESORT ────────────────────────────────

    async def _last_resort(
        self,
        request: LLMRequest,
        tier_requested: str,
        all_errors: list[dict],
    ) -> Optional[LLMResponse]:
        """
        Última tentativa: qualquer modelo de qualquer tier com health > 0.
        Ignora tier assignment. Prioriza modelos com melhor health.
        """
        all_models: list[ModelPoolEntry] = []
        for tier_name in ["premium", "padrao", "economico"]:
            pool = await self._load_pool(tier_name)
            all_models.extend(pool)

        # Remove duplicatas (mesmo provider+model)
        seen = set()
        unique_models = []
        for entry in all_models:
            key = f"{entry.provider}:{entry.model}"
            if key not in seen:
                seen.add(key)
                unique_models.append(entry)

        # Ordena por health score, incluindo modelos em cooldown
        scored = []
        for entry in unique_models:
            if not self.provider_keys.get(entry.provider):
                continue
            score = await self.health_tracker.get_health_score(entry.provider, entry.model)
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        for _, entry in scored:
            result = await self._try_model(request, entry, "last_resort", tier_requested, all_errors)
            if result is not None:
                return result

        return None

    # ─── HELPERS ────────────────────────────────────

    def _build_litellm_model(self, entry: ModelPoolEntry) -> str:
        """Monta o model string no formato do LiteLLM."""
        provider_prefix_map = {
            "anthropic": "anthropic/",
            "openai": "",                # OpenAI não precisa de prefixo
            "google": "gemini/",
            "xai": "xai/",
            "perplexity": "perplexity/",
            "deepseek": "deepseek/",
            "alibaba": "openai/",         # Qwen usa compat OpenAI
        }
        prefix = provider_prefix_map.get(entry.provider, "")
        return f"{prefix}{entry.model}"

    def _build_litellm_kwargs(
        self,
        entry: ModelPoolEntry,
        api_key: str,
        request: LLMRequest,
    ) -> dict:
        """Monta kwargs para litellm.acompletion()."""
        kwargs = {
            "api_key": api_key,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        # API base custom para provedores não-padrão
        provider_bases = {
            "xai": "https://api.x.ai/v1",
            "perplexity": "https://api.perplexity.ai",
            "deepseek": "https://api.deepseek.com/v1",
            "alibaba": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        }
        if entry.provider in provider_bases:
            kwargs["api_base"] = provider_bases[entry.provider]

        # Response format (JSON mode)
        if request.response_format:
            kwargs["response_format"] = request.response_format

        return kwargs

    def _classify_error(self, error_msg: str) -> str:
        """Classifica o tipo de erro baseado na mensagem."""
        if any(kw in error_msg for kw in RATE_LIMIT_KEYWORDS):
            return "rate_limit"
        if any(kw in error_msg for kw in BILLING_KEYWORDS):
            return "billing"
        if any(kw in error_msg for kw in AUTH_KEYWORDS):
            return "auth"
        if any(kw in error_msg for kw in TIMEOUT_KEYWORDS):
            return "timeout"
        return "server_error"

    def _estimate_cost(self, entry: ModelPoolEntry, usage) -> Optional[float]:
        """Estima custo em USD. Usa tabela de preços conhecida."""
        if not usage:
            return None
        # Tabela simplificada de preços (USD por 1M tokens)
        prices = {
            "claude-sonnet-4-6": (3.0, 15.0),
            "claude-opus-4.6": (5.0, 25.0),
            "claude-haiku-4-5": (1.0, 5.0),
            "gpt-5.4": (2.5, 15.0),
            "gpt-5.2": (1.75, 14.0),
            "gpt-5.4-mini": (0.75, 4.5),
            "gpt-5.4-nano": (0.2, 1.25),
            "gpt-4.1-mini": (0.2, 0.8),
            "gpt-4.1-nano": (0.05, 0.2),
            "gemini-3.1-pro-preview": (2.0, 12.0),
            "gemini-2.5-pro": (2.5, 15.0),
            "gemini-2.5-flash": (0.3, 2.5),
            "gemini-2.5-flash-lite": (0.1, 0.4),
            "grok-4": (3.0, 15.0),
            "grok-4-1-fast-reasoning": (0.2, 0.5),
            "grok-4-1-fast-non-reasoning": (0.2, 0.5),
            "grok-3-mini": (0.3, 0.5),
            "sonar-pro": (3.0, 15.0),
            "sonar": (1.0, 1.0),
            "deepseek-chat": (0.28, 0.42),
            "qwen3.5-plus": (0.26, 1.56),
            "qwen3.5-flash": (0.07, 0.26),
            "qwen-turbo": (0.03, 0.13),
        }
        price = prices.get(entry.model)
        if not price:
            return None
        input_cost = (usage.prompt_tokens / 1_000_000) * price[0]
        output_cost = (usage.completion_tokens / 1_000_000) * price[1]
        return round(input_cost + output_cost, 6)

    def _log_and_record_error(
        self,
        entry: ModelPoolEntry,
        elapsed_ms: int,
        error_type: str,
        error_message: str,
        request: LLMRequest,
        tier: str,
        all_errors: list[dict],
        api_key: str,
    ):
        """Registra erro no log, health tracker, e lista de erros."""
        logger.warning(
            "[%s] Falha em %s/%s (%s): %s [%dms]",
            request.task_type, entry.provider, entry.model,
            error_type, error_message[:200], elapsed_ms,
        )

        all_errors.append({
            "provider": entry.provider,
            "model": entry.model,
            "error_type": error_type,
            "error_message": error_message[:200],
            "elapsed_ms": elapsed_ms,
            "tier": tier,
        })

        # Fire-and-forget: registra no health tracker
        record = CallRecord(
            provider=entry.provider,
            model=entry.model,
            success=False,
            latency_ms=elapsed_ms,
            error_type=error_type,
            error_message=error_message[:500],
            task_type=request.task_type,
            tier=tier,
        )
        asyncio.create_task(self._record_call(record))

    async def _record_call(self, record: CallRecord):
        """Registra chamada no health tracker e opcionalmente no PostgreSQL."""
        try:
            await self.health_tracker.record_call(record)
        except Exception as e:
            logger.error("Erro ao registrar no health tracker: %s", e)

        # Log no PostgreSQL (assíncrono, não bloqueia)
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO llm_health_log
                            (provider, model, success, latency_ms, tokens_in, tokens_out,
                             cost_usd, error_type, error_message, task_type, tier)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        """,
                        record.provider, record.model, record.success,
                        record.latency_ms, record.tokens_in, record.tokens_out,
                        record.cost_usd, record.error_type, record.error_message,
                        record.task_type, record.tier,
                    )
            except Exception as e:
                logger.error("Erro ao registrar no PostgreSQL: %s", e)

    # ─── API ADMIN (Runtime Pool Management) ────────

    async def update_tier_pool(self, tier: str, pool: list[dict]) -> None:
        """
        Atualiza pool de um tier em runtime via Redis.
        
        Uso:
            await router.update_tier_pool("premium", [
                {"provider": "anthropic", "model": "claude-sonnet-4-6", "weight": 1.0},
                {"provider": "openai", "model": "gpt-5.4", "weight": 1.0},
            ])
        """
        # Valida entries
        validated = [ModelPoolEntry(**entry).model_dump() for entry in pool]
        redis_key = f"llm:tier_pools:{tier}"
        await self.redis.set(redis_key, json.dumps(validated))
        logger.info("Pool do tier %s atualizado com %d modelos.", tier, len(validated))

    async def get_tier_pool(self, tier: str) -> list[dict]:
        """Retorna o pool atual de um tier (Redis → default)."""
        pool = await self._load_pool(tier)
        return [entry.model_dump() for entry in pool]

    async def get_health_dashboard(self) -> dict:
        """
        Retorna status completo de todos os modelos para dashboard.
        
        Retorna:
            {
                "models": {
                    "anthropic/claude-sonnet-4-6": {"score": 85.3, "tier": "premium", "cooldown": false},
                    ...
                },
                "providers": {
                    "anthropic": {"available_keys": 3, "enabled": true},
                    ...
                },
            }
        """
        scores = await self.health_tracker.get_all_scores()
        
        models = {}
        for model_id, score in scores.items():
            provider, model = model_id.split("/", 1)
            models[model_id] = {
                "score": score,
                "cooldown": await self.health_tracker.is_in_cooldown(provider, model),
                "deprioritized": score < DEPRIORITIZE_THRESHOLD,
            }

        providers = {}
        for provider, keys in self.provider_keys.items():
            available = await self.key_manager.get_available_key_count(provider)
            providers[provider] = {
                "total_keys": len(keys),
                "available_keys": available,
                "enabled": len(keys) > 0,
            }

        return {"models": models, "providers": providers}
```

### 7.7 Tier Config (`llm/tier_config.py`)

```python
"""
Configuração de tiers e mapeamento task → tier.

Este módulo contém os pools padrão e o mapeamento de tarefas.
Os pools podem ser sobrescritos em runtime via Redis.
"""

DEFAULT_TIER_POOLS: dict[str, list[dict]] = {
    "premium": [
        {"provider": "anthropic", "model": "claude-sonnet-4-6", "weight": 1.0},
        {"provider": "openai", "model": "gpt-5.4", "weight": 1.0},
        {"provider": "google", "model": "gemini-3.1-pro-preview", "weight": 1.0},
        {"provider": "xai", "model": "grok-4", "weight": 1.0},
        {"provider": "perplexity", "model": "sonar-pro", "weight": 0.8},
        {"provider": "anthropic", "model": "claude-opus-4.6", "weight": 0.5},
        {"provider": "openai", "model": "gpt-5.2", "weight": 0.5},
        {"provider": "google", "model": "gemini-2.5-pro", "weight": 0.5},
    ],
    "padrao": [
        {"provider": "openai", "model": "gpt-4.1-mini", "weight": 1.0},
        {"provider": "google", "model": "gemini-2.5-flash", "weight": 1.0},
        {"provider": "xai", "model": "grok-4-1-fast-reasoning", "weight": 1.0},
        {"provider": "deepseek", "model": "deepseek-chat", "weight": 1.0},
        {"provider": "alibaba", "model": "qwen3.5-plus", "weight": 1.0},
        {"provider": "anthropic", "model": "claude-haiku-4-5", "weight": 0.8},
        {"provider": "openai", "model": "gpt-5.4-mini", "weight": 0.8},
    ],
    "economico": [
        {"provider": "alibaba", "model": "qwen3.5-flash", "weight": 1.0},
        {"provider": "deepseek", "model": "deepseek-chat", "weight": 1.0},
        {"provider": "google", "model": "gemini-2.5-flash-lite", "weight": 1.0},
        {"provider": "openai", "model": "gpt-4.1-nano", "weight": 1.0},
        {"provider": "xai", "model": "grok-4-1-fast-non-reasoning", "weight": 0.8},
        {"provider": "alibaba", "model": "qwen-turbo", "weight": 0.8},
        {"provider": "openai", "model": "gpt-5.4-nano", "weight": 0.7},
    ],
}

TASK_TIER_MAP: dict[str, str] = {
    # PREMIUM — qualidade editorial máxima
    "redacao_artigo": "premium",
    "imagem_query": "premium",
    "homepage_scoring": "premium",
    "consolidacao_sintese": "premium",
    "pauta_especial": "premium",

    # PADRÃO — competência sem custo máximo
    "seo_otimizacao": "padrao",
    "revisao_texto": "padrao",
    "trending_detection": "padrao",
    "analise_metricas": "padrao",
    "gap_analysis": "padrao",

    # ECONÔMICO — tarefas simples e repetitivas
    "classificacao_categoria": "economico",
    "extracao_entidades": "economico",
    "deduplicacao_texto": "economico",
    "monitoring_health": "economico",
    "summarize_short": "economico",
}

DEFAULT_TIER = "padrao"
```

---

## PARTE VIII — COMO OS AGENTES USAM O ROUTER

### 8.1 Exemplo: Reporter (Redação de Artigo — PREMIUM)

```python
from brasileira.llm.smart_router import SmartLLMRouter
from brasileira.llm.models import LLMRequest

async def redigir_artigo(router: SmartLLMRouter, raw_article: dict) -> str:
    """Reporter usa tier PREMIUM para redação de artigo."""
    request = LLMRequest(
        task_type="redacao_artigo",  # → resolve para tier PREMIUM
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_REPORTER},
            {"role": "user", "content": f"Reescreva: {raw_article['content'][:6000]}"},
        ],
        temperature=0.3,
        max_tokens=4096,
        response_format={"type": "json_object"},
        trace_id=f"art-{raw_article['source_id']}-{int(time.time())}",
    )

    response = await router.route_request(request)

    # Response contém metadados úteis
    logger.info(
        "Artigo redigido via %s/%s [tier: %s, downgraded: %s, custo: $%.4f, latência: %dms]",
        response.provider, response.model,
        response.tier_used.value, response.downgraded,
        response.cost_usd or 0, response.latency_ms,
    )

    return response.content  # JSON string — quem chamou faz parse
```

### 8.2 Exemplo: Fotógrafo (Query de Imagem — PREMIUM)

```python
async def gerar_queries_imagem(router: SmartLLMRouter, artigo: dict) -> dict:
    """Fotógrafo usa tier PREMIUM para gerar queries de busca de imagem."""
    request = LLMRequest(
        task_type="imagem_query",  # → resolve para tier PREMIUM
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_FOTOGRAFO},
            {"role": "user", "content": f"Gere queries para: {artigo['titulo']}"},
        ],
        temperature=0.5,
        max_tokens=512,
        response_format={"type": "json_object"},
    )

    response = await router.route_request(request)
    return json.loads(response.content)
```

### 8.3 Exemplo: Classificador (Classificação — ECONÔMICO)

```python
async def classificar_artigo(router: SmartLLMRouter, titulo: str, resumo: str) -> str:
    """Classificador usa tier ECONÔMICO para categorizar artigo."""
    request = LLMRequest(
        task_type="classificacao_categoria",  # → resolve para tier ECONÔMICO
        messages=[
            {"role": "system", "content": "Classifique em uma das 16 categorias..."},
            {"role": "user", "content": f"Título: {titulo}\nResumo: {resumo}"},
        ],
        temperature=0.0,
        max_tokens=100,
    )

    response = await router.route_request(request)
    return response.content.strip()
```

### 8.4 Exemplo: Atualização de Pool em Runtime

```python
# Adicionar um novo modelo ao tier premium sem deploy
await router.update_tier_pool("premium", [
    {"provider": "anthropic", "model": "claude-sonnet-4-6", "weight": 1.0},
    {"provider": "openai", "model": "gpt-5.4", "weight": 1.0},
    {"provider": "google", "model": "gemini-3.1-pro-preview", "weight": 1.0},
    {"provider": "xai", "model": "grok-4", "weight": 1.0},
    # NOVO MODELO ADICIONADO:
    {"provider": "openai", "model": "gpt-6.0", "weight": 1.0},
])
# Efeito IMEDIATO na próxima chamada — sem deploy, sem restart
```

### 8.5 Exemplo: Dashboard de Health

```python
dashboard = await router.get_health_dashboard()
print(json.dumps(dashboard, indent=2))
# {
#   "models": {
#     "anthropic/claude-sonnet-4-6": {"score": 92.3, "cooldown": false, "deprioritized": false},
#     "openai/gpt-5.4": {"score": 87.1, "cooldown": false, "deprioritized": false},
#     "deepseek/deepseek-chat": {"score": 18.5, "cooldown": false, "deprioritized": true},
#     ...
#   },
#   "providers": {
#     "anthropic": {"total_keys": 3, "available_keys": 2, "enabled": true},
#     "openai": {"total_keys": 2, "available_keys": 2, "enabled": true},
#     ...
#   }
# }
```

---

## PARTE IX — INICIALIZAÇÃO E WIRING

### 9.1 Factory Function

```python
# brasileira/llm/__init__.py

import os
import redis.asyncio as redis
import asyncpg
from .smart_router import SmartLLMRouter
from .key_manager import _load_keys


async def create_router() -> SmartLLMRouter:
    """
    Factory function para criar o SmartLLMRouter.
    Conecta Redis + PostgreSQL e carrega keys do .env.
    """
    # Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = redis.from_url(redis_url, decode_responses=True)

    # PostgreSQL (opcional — health logging)
    pg_pool = None
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        pg_pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)

    # Keys por provedor
    provider_keys = {
        "anthropic": _load_keys("ANTHROPIC_API_KEY"),
        "openai": _load_keys("OPENAI_API_KEY"),
        "google": _load_keys("GEMINI_API_KEY"),
        "xai": _load_keys("GROK_API_KEY"),
        "perplexity": _load_keys("PERPLEXITY_API_KEY"),
        "deepseek": _load_keys("DEEPSEEK_API_KEY"),
        "alibaba": _load_keys("QWEN_API_KEY"),
    }

    # Log de provedores disponíveis
    for provider, keys in provider_keys.items():
        if keys:
            print(f"[SmartRouter] {provider}: {len(keys)} key(s) configurada(s)")
        else:
            print(f"[SmartRouter] {provider}: SEM KEYS — provedor desabilitado")

    return SmartLLMRouter(
        redis_client=redis_client,
        provider_keys=provider_keys,
        pg_pool=pg_pool,
    )


def _load_keys(prefix: str) -> list[str]:
    """Carrega todas as keys de um provider (KEY, KEY_2, KEY_3, ..., KEY_9)."""
    keys = []
    base = os.getenv(prefix, "")
    if base:
        keys.append(base)
    for i in range(2, 10):
        k = os.getenv(f"{prefix}_{i}", "")
        if k:
            keys.append(k)
    return keys
```

### 9.2 Uso no Main do Sistema

```python
# brasileira/main.py

import asyncio
from brasileira.llm import create_router

async def main():
    # Cria o router (compartilhado por TODOS os agentes)
    router = await create_router()

    # Injeta em cada agente
    reporter = Reporter(router=router)
    fotografo = Fotografo(router=router)
    revisor = Revisor(router=router)
    curador = Curador(router=router)
    # ... etc.

    # Inicia agentes
    await asyncio.gather(
        reporter.run(),
        fotografo.run(),
        revisor.run(),
        curador.run(),
        # ...
    )

if __name__ == "__main__":
    asyncio.run(main())
```

---

## PARTE X — TESTES

### 10.1 Testes Obrigatórios

```python
# tests/test_smart_router.py

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from brasileira.llm.smart_router import SmartLLMRouter
from brasileira.llm.models import LLMRequest, LLMResponse
from brasileira.llm.exceptions import AllProvidersFailedError


@pytest.fixture
async def router():
    """Router com Redis mockado e keys de teste."""
    redis_mock = AsyncMock()
    redis_mock.get.return_value = None  # Sem pools em Redis
    redis_mock.exists.return_value = False  # Sem cooldowns
    redis_mock.pipeline.return_value = AsyncMock()

    provider_keys = {
        "anthropic": ["sk-test-1"],
        "openai": ["sk-test-2"],
        "google": ["AIza-test"],
        "xai": ["xai-test"],
        "perplexity": ["pplx-test"],
        "deepseek": ["sk-ds-test"],
        "alibaba": ["sk-qwen-test"],
    }

    return SmartLLMRouter(
        redis_client=redis_mock,
        provider_keys=provider_keys,
    )


class TestTierResolution:
    """Testes de resolução task → tier."""

    def test_premium_tasks(self, router):
        assert router._resolve_tier("redacao_artigo") == "premium"
        assert router._resolve_tier("imagem_query") == "premium"
        assert router._resolve_tier("homepage_scoring") == "premium"

    def test_padrao_tasks(self, router):
        assert router._resolve_tier("seo_otimizacao") == "padrao"
        assert router._resolve_tier("revisao_texto") == "padrao"

    def test_economico_tasks(self, router):
        assert router._resolve_tier("classificacao_categoria") == "economico"
        assert router._resolve_tier("deduplicacao_texto") == "economico"

    def test_unknown_task_defaults_to_padrao(self, router):
        assert router._resolve_tier("tarefa_desconhecida") == "padrao"


class TestDowngrade:
    """Testes de downgrade de tier."""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_premium_downgrades_to_padrao(self, mock_llm, router):
        """Se todos PREMIUM falharem, tenta PADRÃO."""
        call_count = 0

        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            # Falha nas primeiras 8 (todos PREMIUM), sucesso na 9ª (PADRÃO)
            if call_count <= 8:
                raise Exception("rate limit")
            return mock_llm_response()

        mock_llm.side_effect = side_effect

        request = LLMRequest(
            task_type="redacao_artigo",
            messages=[{"role": "user", "content": "test"}],
        )
        response = await router.route_request(request)
        assert response.downgraded is True
        assert response.tier_used.value == "padrao"


class TestAllProvidersFail:
    """Testes de falha total."""

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_raises_error_when_all_fail(self, mock_llm, router):
        """Se TODOS falharem em TODOS os tiers, levanta AllProvidersFailedError."""
        mock_llm.side_effect = Exception("server error")

        request = LLMRequest(
            task_type="redacao_artigo",
            messages=[{"role": "user", "content": "test"}],
        )
        with pytest.raises(AllProvidersFailedError):
            await router.route_request(request)


class TestHealthScoring:
    """Testes do health tracker."""

    @pytest.mark.asyncio
    async def test_success_increases_score(self, router):
        # Score default = 70
        score = await router.health_tracker.get_health_score("openai", "gpt-5.4")
        assert score == 70.0

    @pytest.mark.asyncio
    async def test_cooldown_on_zero_score(self, router):
        is_cool = await router.health_tracker.is_in_cooldown("openai", "gpt-5.4")
        assert is_cool is False


class TestKeyManager:
    """Testes do gerenciador de keys."""

    @pytest.mark.asyncio
    async def test_rotation(self, router):
        key = await router.key_manager.get_next_key("anthropic")
        assert key == "sk-test-1"

    @pytest.mark.asyncio
    async def test_no_keys(self, router):
        key = await router.key_manager.get_next_key("unknown_provider")
        assert key is None
```

### 10.2 Teste de Integração (Manual)

```python
# tests/test_integration_router.py

"""
Teste de integração real — requer keys válidas no .env.
Executar manualmente: python -m pytest tests/test_integration_router.py -v
"""

import asyncio
import pytest
from brasileira.llm import create_router
from brasileira.llm.models import LLMRequest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_call_premium():
    """Faz uma chamada real ao tier PREMIUM."""
    router = await create_router()

    request = LLMRequest(
        task_type="redacao_artigo",
        messages=[
            {"role": "system", "content": "Responda em português do Brasil."},
            {"role": "user", "content": "Resuma em 1 frase: Python é uma linguagem de programação."},
        ],
        max_tokens=100,
    )

    response = await router.route_request(request)
    assert response.content
    assert response.provider in ("anthropic", "openai", "google", "xai", "perplexity")
    assert response.tier_used.value == "premium"
    print(f"Provider: {response.provider}/{response.model}")
    print(f"Content: {response.content}")
    print(f"Latency: {response.latency_ms}ms")
    print(f"Cost: ${response.cost_usd:.6f}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_call_economico():
    """Faz uma chamada real ao tier ECONÔMICO."""
    router = await create_router()

    request = LLMRequest(
        task_type="classificacao_categoria",
        messages=[
            {"role": "user", "content": "Classifique: 'Lula anuncia reforma tributária'. Categoria: "},
        ],
        max_tokens=50,
    )

    response = await router.route_request(request)
    assert response.content
    assert response.tier_used.value == "economico"
    print(f"Provider: {response.provider}/{response.model}")
    print(f"Content: {response.content}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_dashboard():
    """Verifica que o dashboard funciona após algumas chamadas."""
    router = await create_router()

    # Faz 3 chamadas para popular health data
    for _ in range(3):
        await router.route_request_safe(LLMRequest(
            task_type="monitoring_health",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=10,
        ))

    dashboard = await router.get_health_dashboard()
    assert "models" in dashboard
    assert "providers" in dashboard
    print(f"Models tracked: {len(dashboard['models'])}")
    print(f"Providers: {dashboard['providers']}")
```

---

## PARTE XI — REQUIREMENTS E INFRAESTRUTURA

### 11.1 requirements.txt (Mínimo para o SmartLLMRouter)

```
# LLM Gateway — ALERTA: evitar 1.82.7 e 1.82.8 (supply chain attack)
litellm>=1.80.0,!=1.82.7,!=1.82.8

# Redis async
redis[hiredis]>=5.0

# PostgreSQL async
asyncpg>=0.29

# Validação
pydantic>=2.5

# .env loading
python-dotenv>=1.0

# Observabilidade (opcional mas recomendado)
opentelemetry-api>=1.24
opentelemetry-sdk>=1.24
```

### 11.2 Docker Compose (Redis + PostgreSQL para desenvolvimento)

```yaml
# docker-compose.dev.yml
version: "3.8"

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

  postgres:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: brasileira
      POSTGRES_PASSWORD: brasileira_dev
      POSTGRES_DB: brasileira_v3
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./sql/init.sql:/docker-compose-entrypoint-initdb.d/init.sql

volumes:
  redis-data:
  postgres-data:
```

### 11.3 SQL de Inicialização (`sql/init.sql`)

```sql
-- Extensão pgvector (para memória semântica dos agentes — futuro)
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela de health log do SmartLLMRouter
CREATE TABLE IF NOT EXISTS llm_health_log (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd FLOAT,
    error_type VARCHAR(50),
    error_message TEXT,
    task_type VARCHAR(50),
    tier VARCHAR(20),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_recent
    ON llm_health_log(provider, model, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_health_task
    ON llm_health_log(task_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_health_errors
    ON llm_health_log(success, timestamp DESC) WHERE NOT success;

-- Limpeza automática de registros antigos (manter 30 dias)
-- Executar via cron externo ou pg_cron:
-- DELETE FROM llm_health_log WHERE timestamp < NOW() - INTERVAL '30 days';
```

---

## PARTE XII — CHECKLIST DE VALIDAÇÃO

Antes de considerar o SmartLLMRouter pronto para produção, **todos** estes itens devem ser verificados:

### Funcional

- [ ] Chamada com `task_type="redacao_artigo"` usa tier PREMIUM
- [ ] Chamada com `task_type="classificacao_categoria"` usa tier ECONÔMICO
- [ ] Se provedor #1 falha, tenta provedor #2 automaticamente
- [ ] Se TODOS do tier PREMIUM falham, downgrade para PADRÃO
- [ ] Se TODOS de TODOS os tiers falham, last_resort tenta qualquer modelo
- [ ] Se realmente TUDO falha, levanta `AllProvidersFailedError` com lista de erros
- [ ] `route_request_safe()` retorna None em vez de exceção
- [ ] Health score calculado corretamente (sucesso, latência, recência)
- [ ] Modelo com score=0 entra em cooldown de 5 minutos
- [ ] Modelo com score<30 é deprioritizado mas não excluído
- [ ] Key rotation funciona: rate limit → próxima key
- [ ] Key com billing error → cooldown de 1 hora
- [ ] Pools carregados de Redis quando disponíveis
- [ ] Pools atualizáveis em runtime via `update_tier_pool()`
- [ ] Dashboard de health retorna todos os modelos e provedores
- [ ] Todas as chamadas logadas em PostgreSQL
- [ ] Todos os 7 provedores suportados: Anthropic, OpenAI, Google, xAI, Perplexity, DeepSeek, Alibaba

### Performance

- [ ] Chamada individual < 30s (timeout)
- [ ] Cascata completa (tier inteiro) < 2 minutos
- [ ] Sem chamadas síncronas — tudo async
- [ ] Redis é único ponto de leitura quente (não PostgreSQL)
- [ ] PostgreSQL write é fire-and-forget (não bloqueia resposta)

### Resiliência

- [ ] Redis offline → usa pools default do código
- [ ] PostgreSQL offline → health logging silenciosamente desabilitado
- [ ] Nenhuma falha de provedor faz o sistema inteiro parar
- [ ] Sem retry loops infinitos — máximo 1 tentativa por modelo

### Configuração

- [ ] Keys carregadas do .env (padrão V2: KEY, KEY_2, ..., KEY_9)
- [ ] LiteLLM versão segura (!=1.82.7, !=1.82.8)
- [ ] `.env.example` documentado com todas as variáveis necessárias

---

## PARTE XIII — O QUE ESTE COMPONENTE NÃO FAZ

Para evitar scope creep, o SmartLLMRouter **NÃO** é responsável por:

1. **Parse de JSON** — Quem chama o router recebe texto bruto (string). O parse de JSON, validação de campos, extração de dados é responsabilidade do agente que chamou.
2. **Prompt engineering** — System prompts e user prompts são construídos pelo agente. O router apenas os encaminha.
3. **Lógica editorial** — Classificação de tier por fonte/tipo de conteúdo (ex: "imprensa → PREMIUM, governo → PADRÃO") é feita pelo agente antes de chamar o router.
4. **Kafka** — O router não produz nem consome mensagens Kafka.
5. **WordPress** — O router não interage com o WordPress.
6. **Geração de imagem** — DALL-E/Flux para geração de imagem é um pipeline separado do Fotógrafo, não do router LLM.

O SmartLLMRouter faz **uma coisa**: recebe messages, escolhe o melhor modelo disponível, faz a chamada, trata erros, e retorna a resposta.

---

*Este briefing faz parte do planejamento completo da V3 da brasileira.news. O documento mestre de implementação com os 9 agentes, pipeline de ingestão, Kafka, PostgreSQL, WordPress e todos os outros componentes está em `briefing-implementacao-brasileira-news-v3.pplx.md`. Documentos de pesquisa de referência: `catalogo_modelos_llm_2026.md` (modelos e preços), `benchmarking_arquitetura.md` (padrões de mercado), `diagnostico_completo_v2.md` (análise dos 20 arquivos V2).*
