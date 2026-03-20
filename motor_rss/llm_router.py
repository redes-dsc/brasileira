"""
Roteamento multi-LLM com 3 TIERS de qualidade, circuit breaker e rotação de keys.

TIER 1 (Premium)  — Artigos de IMPRENSA: consolidação analítica, anti-plágio,
                     junção de fontes para conteúdo original e denso.
                     GPT-4o → Claude Sonnet 4 → Grok-3 → Gemini 2.5 Pro
TIER 2 (Standard) — Artigos INSTITUCIONAIS/GOVERNO: reescrita editorial com
                     parâmetros da Brasileira.News, sem tanta elaboração.
                     Gemini 2.0 Flash → GPT-4o-mini → DeepSeek
TIER 3 (Economy)  — Triagem, classificação, tarefas auxiliares
                     DeepSeek → Qwen → Gemini Flash
"""

import json
import logging
import re
import time

import config

logger = logging.getLogger("motor_rss")


# ─── Circuit Breaker ─────────────────────────────────

_circuit_breaker: dict[str, dict] = {}
CIRCUIT_BREAKER_THRESHOLD = 3    # bloqueia após N falhas consecutivas
CIRCUIT_BREAKER_COOLDOWN = 1800  # 30 min de cooldown


def _cb_is_open(provider: str) -> bool:
    """Verifica se o circuit breaker está aberto (provider bloqueado)."""
    state = _circuit_breaker.get(provider)
    if not state:
        return False
    if state["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        if time.time() < state["blocked_until"]:
            return True
        logger.info("Circuit breaker reset para %s (cooldown expirou)", provider)
        _circuit_breaker.pop(provider, None)
        return False
    return False


def _cb_record_failure(provider: str):
    """Registra uma falha no circuit breaker."""
    state = _circuit_breaker.setdefault(provider, {"failures": 0, "blocked_until": 0})
    state["failures"] += 1
    if state["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        state["blocked_until"] = time.time() + CIRCUIT_BREAKER_COOLDOWN
        logger.warning(
            "Circuit breaker ABERTO para %s (%d falhas). Bloqueado por %ds.",
            provider, state["failures"], CIRCUIT_BREAKER_COOLDOWN,
        )


def _cb_record_success(provider: str):
    """Registra um sucesso — reseta o circuit breaker."""
    if provider in _circuit_breaker:
        _circuit_breaker.pop(provider)


# ─── Key Rotation ────────────────────────────────────

_key_index: dict[str, int] = {}


def _next_key(provider: str, keys: list[str]) -> str | None:
    """Retorna a próxima key em rotação round-robin."""
    if not keys:
        return None
    idx = _key_index.get(provider, 0) % len(keys)
    _key_index[provider] = idx + 1
    return keys[idx]


def _rotate_key(provider: str, keys: list[str]):
    """Força rotação para a próxima key (chamado após rate limit)."""
    if len(keys) > 1:
        _key_index[provider] = _key_index.get(provider, 0) + 1
        logger.info("Key rotacionada para %s (key #%d)", provider, _key_index[provider] % len(keys) + 1)


# ─── JSON Parsing ────────────────────────────────────

def _clean_json_response(text: str) -> str:
    """Remove markdown code fences e extrai JSON puro."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start : brace_end + 1]
    return text


def _parse_llm_json(text: str) -> dict:
    """Faz parse do JSON retornado pelo LLM."""
    cleaned = _clean_json_response(text)
    data = json.loads(cleaned)
    
    # Prevenção Ativa: Se o LLM colocar blocos markdown (```html) dentro da string "conteudo"
    if isinstance(data, dict) and "conteudo" in data and isinstance(data["conteudo"], str):
        content = data["conteudo"]
        content = re.sub(r'```(?:html|json)?\s*', '', content)
        content = re.sub(r'```', '', content)
        data["conteudo"] = content.strip()
        
    return data


def _validate_response(data: dict) -> bool:
    """Valida se a resposta contém todos os campos obrigatórios."""
    required = [
        "titulo", "conteudo", "excerpt", "categoria",
        "tags", "seo_title", "seo_description",
    ]
    for key in required:
        if key not in data or not data[key]:
            logger.warning("Campo obrigatório ausente ou vazio: %s", key)
            return False
    if not isinstance(data["tags"], list):
        data["tags"] = [t.strip() for t in str(data["tags"]).split(",") if t.strip()]
    return True


# ─── Providers (modelos PREMIUM — TIER 1) ────────────
# Usados para redação editorial, conteúdo de destaque, fontes governamentais

def _call_openai_premium(system_prompt: str, user_prompt: str) -> str:
    """GPT-4o completo — melhor qualidade de redação e JSON."""
    key = _next_key("openai", config.OPENAI_KEYS)
    if not key:
        raise ValueError("Nenhuma OPENAI_API_KEY configurada")
    from openai import OpenAI
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
        timeout=config.LLM_TIMEOUT,
    )
    return response.choices[0].message.content


def _call_claude_premium(system_prompt: str, user_prompt: str) -> str:
    """Claude Sonnet 4 — excelência em redação jornalística."""
    key = _next_key("claude", config.ANTHROPIC_KEYS)
    if not key:
        raise ValueError("Nenhuma ANTHROPIC_API_KEY configurada")
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=config.LLM_TIMEOUT)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _call_grok_premium(system_prompt: str, user_prompt: str) -> str:
    """Grok-3 completo — bom raciocínio e redação."""
    key = _next_key("grok", config.GROK_KEYS)
    if not key:
        raise ValueError("Nenhuma GROK_API_KEY configurada")
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
    response = client.chat.completions.create(
        model="grok-3",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
        timeout=config.LLM_TIMEOUT,
    )
    return response.choices[0].message.content


def _call_gemini_premium(system_prompt: str, user_prompt: str) -> str:
    """Gemini 2.5 Pro — modelo mais capaz do Google."""
    key = _next_key("gemini", config.GEMINI_KEYS)
    if not key:
        raise ValueError("Nenhuma GEMINI_API_KEY configurada")
    from google import genai
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model="gemini-2.5-pro-preview-05-06",
        contents=f"{system_prompt}\n\n{user_prompt}",
    )
    return response.text


# ─── Providers (modelos STANDARD — TIER 2) ───────────
# Usados para artigos normais de imprensa

def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    """Gemini 2.0 Flash — rápido, gratuito, comprovado."""
    key = _next_key("gemini", config.GEMINI_KEYS)
    if not key:
        raise ValueError("Nenhuma GEMINI_API_KEY configurada")
    from google import genai
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"{system_prompt}\n\n{user_prompt}",
    )
    return response.text


def _call_openai(system_prompt: str, user_prompt: str) -> str:
    """GPT-4o-mini — confiável, bom JSON."""
    key = _next_key("openai", config.OPENAI_KEYS)
    if not key:
        raise ValueError("Nenhuma OPENAI_API_KEY configurada")
    from openai import OpenAI
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
        timeout=config.LLM_TIMEOUT,
    )
    return response.choices[0].message.content


def _call_deepseek(system_prompt: str, user_prompt: str) -> str:
    """DeepSeek V3 — capaz e barato, porém lento (~34s)."""
    key = _next_key("deepseek", config.DEEPSEEK_KEYS)
    if not key:
        raise ValueError("Nenhuma DEEPSEEK_API_KEY configurada")
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
        timeout=config.LLM_TIMEOUT,
    )
    return response.choices[0].message.content


# ─── Providers (modelos ECONOMY — TIER 3) ────────────
# Usados para triagem, classificação, tarefas auxiliares

def _call_qwen(system_prompt: str, user_prompt: str) -> str:
    """Qwen Plus — alternativa econômica."""
    key = _next_key("qwen", config.QWEN_KEYS)
    if not key:
        raise ValueError("Nenhuma QWEN_API_KEY configurada")
    from openai import OpenAI
    client = OpenAI(
        api_key=key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    response = client.chat.completions.create(
        model="qwen-plus",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
        timeout=config.LLM_TIMEOUT,
    )
    return response.choices[0].message.content


def _call_grok_mini(system_prompt: str, user_prompt: str) -> str:
    """Grok-3 Mini — versão leve para tarefas simples."""
    key = _next_key("grok", config.GROK_KEYS)
    if not key:
        raise ValueError("Nenhuma GROK_API_KEY configurada")
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
    response = client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
        timeout=config.LLM_TIMEOUT,
    )
    return response.choices[0].message.content


# ─── Cascatas por TIER ────────────────────────────────

# TIER 1: IMPRENSA — modelos premium para consolidação analítica
# Artigos de portais que exigem reescrita profunda, junção de fontes, anti-plágio
_TIER1_PROVIDERS = [
    ("openai:gpt-4o",        _call_openai_premium,  config.OPENAI_KEYS),
    ("claude:sonnet-4",      _call_claude_premium,   config.ANTHROPIC_KEYS),
    ("grok:grok-3",          _call_grok_premium,     config.GROK_KEYS),
    ("gemini:2.5-pro",       _call_gemini_premium,   config.GEMINI_KEYS),
    # Fallback para standard se todos premium falharem
    ("gemini:2.0-flash",     _call_gemini,           config.GEMINI_KEYS),
    ("deepseek:v3",          _call_deepseek,         config.DEEPSEEK_KEYS),
]

# TIER 2: INSTITUCIONAL/GOVERNO — reescrita editorial, menos elaboração
# Senado, Câmara, Gov.br, STF etc. — tom oficial, reescrita direta
_TIER2_PROVIDERS = [
    ("gemini:2.0-flash",     _call_gemini,           config.GEMINI_KEYS),
    ("openai:gpt-4o-mini",   _call_openai,           config.OPENAI_KEYS),
    ("deepseek:v3",          _call_deepseek,         config.DEEPSEEK_KEYS),
    ("qwen:plus",            _call_qwen,             config.QWEN_KEYS),
    ("grok:grok-3-mini",     _call_grok_mini,        config.GROK_KEYS),
]

# TIER 3: Triagem e tarefas auxiliares — máxima economia
_TIER3_PROVIDERS = [
    ("deepseek:v3",          _call_deepseek,         config.DEEPSEEK_KEYS),
    ("qwen:plus",            _call_qwen,             config.QWEN_KEYS),
    ("gemini:2.0-flash",     _call_gemini,           config.GEMINI_KEYS),
    ("grok:grok-3-mini",     _call_grok_mini,        config.GROK_KEYS),
]

# TIER CURATOR: Curadoria editorial de HOME — decisões de destaque
# Avalia relevância, seleciona manchetes, organiza home page
# Precisa de modelos com bom julgamento editorial
_TIER_CURATOR_PROVIDERS = [
    ("gemini:2.5-pro",       _call_gemini_premium,   config.GEMINI_KEYS),
    ("openai:gpt-4o",        _call_openai_premium,   config.OPENAI_KEYS),
    ("claude:sonnet-4",      _call_claude_premium,   config.ANTHROPIC_KEYS),
    ("gemini:2.0-flash",     _call_gemini,           config.GEMINI_KEYS),
    ("deepseek:v3",          _call_deepseek,         config.DEEPSEEK_KEYS),
]

# TIER CONSOLIDATOR: Artigos consolidados multi-fonte
# Junta múltiplas matérias sobre o mesmo tema em análise original
# Exige máxima capacidade de síntese e redação jornalística
_TIER_CONSOLIDATOR_PROVIDERS = [
    ("claude:sonnet-4",      _call_claude_premium,   config.ANTHROPIC_KEYS),
    ("openai:gpt-4o",        _call_openai_premium,   config.OPENAI_KEYS),
    ("gemini:2.5-pro",       _call_gemini_premium,   config.GEMINI_KEYS),
    ("grok:grok-3",          _call_grok_premium,     config.GROK_KEYS),
    ("gemini:2.0-flash",     _call_gemini,           config.GEMINI_KEYS),
    ("deepseek:v3",          _call_deepseek,         config.DEEPSEEK_KEYS),
]

# TIER PHOTO EDITOR: Curadoria de imagem jornalística
# Tarefa curta (poucos tokens) que exige julgamento editorial premium
# para decidir a cena visual mais relevante da notícia.
_TIER_PHOTO_EDITOR_PROVIDERS = [
    ("openai:gpt-4o",        _call_openai_premium,   config.OPENAI_KEYS),
    ("claude:sonnet-4",      _call_claude_premium,   config.ANTHROPIC_KEYS),
    ("gemini:2.5-pro",       _call_gemini_premium,   config.GEMINI_KEYS),
    ("grok:grok-3",          _call_grok_premium,     config.GROK_KEYS),
]

# Constantes de tier para uso externo
TIER_PREMIUM = 1
TIER_STANDARD = 2
TIER_ECONOMY = 3
TIER_CURATOR = "curator"
TIER_CONSOLIDATOR = "consolidator"
TIER_PHOTO_EDITOR = "photo_editor"

_TIER_MAP = {
    1:              _TIER1_PROVIDERS,
    2:              _TIER2_PROVIDERS,
    3:              _TIER3_PROVIDERS,
    "curator":      _TIER_CURATOR_PROVIDERS,
    "consolidator": _TIER_CONSOLIDATOR_PROVIDERS,
    "photo_editor": _TIER_PHOTO_EDITOR_PROVIDERS,
}


# ─── Classificador de complexidade ───────────────────

# Fontes INSTITUCIONAIS/GOVERNO → TIER 2 (reescrita editorial direta)
_INSTITUTIONAL_SOURCES = {
    "senado", "câmara", "gov.br", "stf", "stj", "tse", "tcu", "cgu",
    "presidência", "planalto", "congresso", "ministério", "agência brasil",
    "radioagência",
}

# Temas institucionais → TIER 2
_INSTITUTIONAL_THEMES = {"governo"}


def classify_tier(
    source: str = "",
    feed_tema: str = "",
    content_length: int = 0,
    score: float = 0.0,
) -> int:
    """
    Classifica o tier de qualidade necessário para o artigo.

    TIER 1 — IMPRENSA (Premium):
      Artigos de portais jornalísticos que precisam de consolidação
      analítica, reescrita profunda para evitar plágio, e produção
      de conteúdo original e denso a partir de múltiplas fontes.
      • Artigos longos (>3000 chars) de imprensa
      • Score alto (>70) de imprensa
      • Qualquer fonte NÃO institucional

    TIER 2 — INSTITUCIONAL/GOVERNO (Standard):
      Matérias de fontes oficiais que precisam apenas de reescrita
      editorial com os parâmetros da Brasileira.News.
      • Senado, Câmara, Gov.br, STF, Agência Brasil, etc.
      • Conteúdo já consolidado pela fonte oficial

    TIER 3 — Economy (reservado para tarefas auxiliares)
    """
    source_lower = source.lower()

    # Fontes institucionais/governo → TIER 2 (reescrita editorial)
    if any(gov in source_lower for gov in _INSTITUTIONAL_SOURCES):
        return 2

    # Tema governo → TIER 2
    if feed_tema in _INSTITUTIONAL_THEMES:
        return 2

    # Tudo que é imprensa → TIER 1 (consolidação analítica premium)
    return 1


# ─── Error keywords ──────────────────────────────────

_RATE_LIMIT_KEYWORDS = ("rate limit", "quota", "too many requests", "429", "resource_exhausted")
_CREDIT_KEYWORDS = ("credit balance", "insufficient_quota", "billing", "exceeded your current quota")


# ─── Router principal ────────────────────────────────

def generate_article(
    title: str,
    content: str,
    source: str,
    categories: list[str],
    url: str = "",
    tier: int = 2,
) -> tuple[dict | None, str]:
    """
    Gera artigo reescrito usando cascata de LLMs do tier apropriado.
    """
    # ── Budget Check ──────────────────────────────────────
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path("/home/bitnami")))
    import gestor_budget
    
    ok, usage = gestor_budget.check_budget_ok()
    if not ok:
        logger.error("BUDGET EXCEDIDO (%d chamadas hoje). Abortando geração.", usage)
        return None, "budget_limit"

    providers = _TIER_MAP.get(tier, _TIER2_PROVIDERS)

    system_prompt = config.LLM_SYSTEM_PROMPT
    user_prompt = config.LLM_REWRITE_PROMPT_TEMPLATE.format(
        title=title,
        content=content[:6000],
        source=source,
        url=url,
        categories=", ".join(categories),
    )

    logger.info("Roteamento TIER %d para: %s (fonte: %s)", tier, title[:50], source)

    for provider_name, call_fn, keys in providers:
        # Circuit breaker usa nome base do provider (sem modelo)
        cb_name = provider_name.split(":")[0]

        if _cb_is_open(cb_name):
            logger.debug("Circuit breaker aberto para %s — pulando.", cb_name)
            continue

        try:
            logger.info("Tentando LLM: %s [TIER %d]", provider_name, tier)
            start = time.time()
            raw_response = call_fn(system_prompt, user_prompt)
            elapsed = time.time() - start
            logger.info("LLM %s respondeu em %.1fs", provider_name, elapsed)

            data = _parse_llm_json(raw_response)
            if _validate_response(data):
                logger.info(
                    "Artigo gerado com sucesso via %s [TIER %d]",
                    provider_name, tier,
                )
                _cb_record_success(cb_name)
                # Registrar no budget
                import gestor_budget
                gestor_budget.registrar_chamada(provider_name)
                return data, provider_name

            logger.warning("Resposta do %s inválida, tentando próximo.", provider_name)

        except json.JSONDecodeError as e:
            logger.warning("JSON inválido do %s: %s", provider_name, e)

        except Exception as e:
            error_msg = str(e).lower()

            if any(kw in error_msg for kw in _CREDIT_KEYWORDS):
                logger.warning("Erro de crédito/billing no %s: %s", provider_name, e)
                for _ in range(CIRCUIT_BREAKER_THRESHOLD):
                    _cb_record_failure(cb_name)
                continue

            if any(kw in error_msg for kw in _RATE_LIMIT_KEYWORDS):
                logger.warning("Rate limit no %s — rotacionando key.", provider_name)
                _rotate_key(cb_name, keys)

            logger.warning("Erro no %s: %s", provider_name, e)
            _cb_record_failure(cb_name)

    logger.error("TODOS os LLMs (TIER %s) falharam para: %s", tier, title[:80])
    return None, ""


def call_llm(
    system_prompt: str,
    user_prompt: str,
    tier: int | str = TIER_STANDARD,
    parse_json: bool = False,
) -> tuple[str | dict | None, str]:
    """
    Chamada genérica de LLM para qualquer agente do sistema.
    """
    # ── Budget Check ──────────────────────────────────────
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path("/home/bitnami")))
    import gestor_budget
    
    ok, usage = gestor_budget.check_budget_ok()
    if not ok:
        logger.error("BUDGET EXCEDIDO (%d chamadas hoje). Abortando call_llm.", usage)
        return None, "budget_limit"

    providers = _TIER_MAP.get(tier, _TIER2_PROVIDERS)

    logger.info("call_llm [TIER %s] — prompt: %s...", tier, user_prompt[:50])

    for provider_name, call_fn, keys in providers:
        cb_name = provider_name.split(":")[0]

        if _cb_is_open(cb_name):
            logger.debug("Circuit breaker aberto para %s — pulando.", cb_name)
            continue

        try:
            logger.info("Tentando LLM: %s [TIER %s]", provider_name, tier)
            start = time.time()
            raw = call_fn(system_prompt, user_prompt)
            elapsed = time.time() - start
            logger.info("LLM %s respondeu em %.1fs", provider_name, elapsed)

            _cb_record_success(cb_name)
            
            # Registrar no budget
            import gestor_budget
            gestor_budget.registrar_chamada(provider_name)

            if parse_json:
                data = _parse_llm_json(raw)
                return data, provider_name
            else:
                return raw.strip(), provider_name

        except json.JSONDecodeError as e:
            logger.warning("JSON inválido do %s: %s", provider_name, e)

        except Exception as e:
            error_msg = str(e).lower()

            if any(kw in error_msg for kw in _CREDIT_KEYWORDS):
                logger.warning("Erro de crédito/billing no %s: %s", provider_name, e)
                for _ in range(CIRCUIT_BREAKER_THRESHOLD):
                    _cb_record_failure(cb_name)
                continue

            if any(kw in error_msg for kw in _RATE_LIMIT_KEYWORDS):
                logger.warning("Rate limit no %s — rotacionando key.", provider_name)
                _rotate_key(cb_name, keys)

            logger.warning("Erro no %s: %s", provider_name, e)
            _cb_record_failure(cb_name)

    logger.error("TODOS os LLMs (TIER %s) falharam.", tier)
    return None, ""
