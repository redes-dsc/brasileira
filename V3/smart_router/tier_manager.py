"""Configuração de tiers e pools dinâmicos."""

from __future__ import annotations

from shared.schemas import ModelPoolEntry

DEFAULT_TIER = "padrao"

DEFAULT_TIER_POOLS: dict[str, list[dict[str, object]]] = {
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
    "redacao_artigo": "premium",
    "imagem_query": "premium",
    "homepage_scoring": "premium",
    "consolidacao_sintese": "premium",
    "pauta_especial": "premium",
    "seo_otimizacao": "padrao",
    "revisao_texto": "padrao",
    "trending_detection": "padrao",
    "analise_metricas": "padrao",
    "gap_analysis": "padrao",
    "classificacao_categoria": "economico",
    "extracao_entidades": "economico",
    "deduplicacao_texto": "economico",
    "monitoring_health": "economico",
    "summarize_short": "economico",
}

DOWNGRADE_ORDER = ["premium", "padrao", "economico"]


def resolve_tier(task_type: str) -> str:
    """Resolve tier por tipo de tarefa."""

    return TASK_TIER_MAP.get(task_type, DEFAULT_TIER)


def normalize_pool(entries: list[dict[str, object]]) -> list[ModelPoolEntry]:
    """Valida e normaliza entradas de pool."""

    return [ModelPoolEntry(**entry) for entry in entries]


def tiers_from(start_tier: str) -> list[str]:
    """Retorna cascata de downgrade a partir do tier inicial."""

    if start_tier not in DOWNGRADE_ORDER:
        return [DEFAULT_TIER, "economico"]
    start_index = DOWNGRADE_ORDER.index(start_tier)
    return DOWNGRADE_ORDER[start_index:]
