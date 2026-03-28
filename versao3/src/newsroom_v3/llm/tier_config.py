from dataclasses import dataclass


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str


TIER_POOLS: dict[str, list[ModelTarget]] = {
    'premium': [
        ModelTarget('anthropic', 'claude-sonnet-4-6'),
        ModelTarget('openai', 'gpt-5.4'),
        ModelTarget('google', 'gemini-3.1-pro-preview'),
        ModelTarget('xai', 'grok-4'),
        ModelTarget('perplexity', 'sonar-pro'),
    ],
    'padrao': [
        ModelTarget('openai', 'gpt-4.1-mini'),
        ModelTarget('google', 'gemini-2.5-flash'),
        ModelTarget('xai', 'grok-4-1-fast-reasoning'),
        ModelTarget('deepseek', 'deepseek-chat'),
        ModelTarget('alibaba', 'qwen3.5-plus'),
    ],
    'economico': [
        ModelTarget('alibaba', 'qwen3.5-flash'),
        ModelTarget('deepseek', 'deepseek-chat'),
        ModelTarget('google', 'gemini-2.5-flash-lite'),
        ModelTarget('openai', 'gpt-4.1-nano'),
    ],
}

TASK_TO_TIER: dict[str, str] = {
    'redacao_artigo': 'premium',
    'imagem_query': 'premium',
    'homepage_scoring': 'premium',
    'consolidacao_sintese': 'premium',
    'pauta_especial': 'premium',
    'seo_otimizacao': 'padrao',
    'revisao_texto': 'padrao',
    'trending_detection': 'padrao',
    'analise_metricas': 'padrao',
    'classificacao_categoria': 'economico',
    'extracao_entidades': 'economico',
    'deduplicacao_texto': 'economico',
    'monitoring_health': 'economico',
}


def resolve_tier(task_type: str) -> str:
    return TASK_TO_TIER.get(task_type, 'padrao')
