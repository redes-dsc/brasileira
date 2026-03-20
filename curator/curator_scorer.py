"""
Módulo de pontuação editorial — Home Curator Agent

Calcula score de relevância em duas fases:
  1. Score objetivo (critérios mensuráveis, sem LLM)
  2. Score LLM (avaliação editorial via Gemini Flash)

Score final = objetivo + LLM (0 a ~130 teórico, prático até ~100)
"""

import logging
import re
import time
from datetime import datetime, timedelta

import curator_config as cfg

logger = logging.getLogger("curator")


# ─── Fase 1: Score Objetivo ──────────────────────────

def _count_words(html_content: str) -> int:
    """Conta palavras no conteúdo HTML (remove tags)."""
    text = re.sub(r"<[^>]+>", " ", html_content)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text.split())


def _is_official_source(source_url: str) -> bool:
    """Verifica se a URL da fonte é de um domínio oficial brasileiro."""
    if not source_url:
        return False
    source_lower = source_url.lower()
    return any(domain in source_lower for domain in cfg.OFFICIAL_DOMAINS)


def _has_br_context(tags: list[str]) -> bool:
    """Heurística: post internacional tem contexto BR se tem tags BR."""
    br_keywords = [
        "brasil", "brasileiro", "governo", "lula", "congresso",
        "senado", "câmara", "stf", "real", "ibovespa",
    ]
    for tag in tags:
        tag_lower = tag.lower()
        if any(kw in tag_lower for kw in br_keywords):
            return True
    return False


def score_objective(post: dict) -> tuple[int, dict]:
    """
    Calcula score objetivo de um post.
    
    Args:
        post: dict com chaves:
            - post_title: str
            - post_excerpt: str
            - post_content: str
            - post_date: datetime
            - featured_media: int (0 = sem imagem)
            - tags: list[str] (slugs das tags)
            - tag_names: list[str] (nomes das tags)
            - categories: list[int] (IDs das categorias)
            - source_url: str (URL da fonte original)
    
    Returns:
        (score_total, breakdown_dict)
    """
    score = 0
    breakdown = {}
    
    title = post.get("post_title", "")
    excerpt = post.get("post_excerpt", "")
    content = post.get("post_content", "")
    post_date = post.get("post_date", datetime.now())
    featured_media = post.get("featured_media", 0)
    tags = post.get("tags", [])
    tag_names = post.get("tag_names", [])
    categories = set(post.get("categories", []))
    source_url = post.get("source_url", "")
    
    word_count = _count_words(content)
    
    # ── Filtro eliminatório ──────────────────────────
    if word_count < cfg.MIN_WORDS:
        return -1, {"eliminado": f"< {cfg.MIN_WORDS} palavras ({word_count})"}
    
    # ── Critérios POSITIVOS ──────────────────────────
    
    # +30: Fonte oficial
    if _is_official_source(source_url):
        score += cfg.SCORE_FONTE_OFICIAL
        breakdown["fonte_oficial"] = cfg.SCORE_FONTE_OFICIAL
    
    # +20: Matéria consolidada
    if "consolidada" in tags:
        score += cfg.SCORE_CONSOLIDADA
        breakdown["consolidada"] = cfg.SCORE_CONSOLIDADA
    
    # +15: Tema de alto interesse
    if categories & cfg.HIGH_INTEREST_CATEGORY_IDS:
        score += cfg.SCORE_ALTO_INTERESSE
        breakdown["alto_interesse"] = cfg.SCORE_ALTO_INTERESSE
    
    # +10: Post recente (< 1h)
    if isinstance(post_date, datetime):
        age = datetime.now() - post_date
        if age < timedelta(hours=1):
            score += cfg.SCORE_RECENTE
            breakdown["recente"] = cfg.SCORE_RECENTE
    
    # +10: Tem imagem de destaque
    if featured_media and int(featured_media) > 0:
        score += cfg.SCORE_TEM_IMAGEM
        breakdown["tem_imagem"] = cfg.SCORE_TEM_IMAGEM
    
    # +5: Título SEO ideal (50-80 chars)
    title_len = len(title)
    if 50 <= title_len <= 80:
        score += cfg.SCORE_TITULO_SEO
        breakdown["titulo_seo"] = cfg.SCORE_TITULO_SEO
    
    # +5: Excerpt preenchido
    if excerpt and len(excerpt.strip()) > 10:
        score += cfg.SCORE_EXCERPT
        breakdown["excerpt"] = cfg.SCORE_EXCERPT
    
    # +5: Tags relevantes (>= 3)
    # Filtrar tags editoriais (home-*) da contagem
    editorial_prefixes = ("home-", "consolidada")
    real_tags = [t for t in tags if not any(t.startswith(p) for p in editorial_prefixes)]
    if len(real_tags) >= 3:
        score += cfg.SCORE_TAGS_RELEVANTES
        breakdown["tags_relevantes"] = cfg.SCORE_TAGS_RELEVANTES
    
    # ── Critérios NEGATIVOS ──────────────────────────
    
    # -20: Internacional sem contexto BR
    if categories & cfg.INTERNATIONAL_CATEGORY_IDS:
        if not _has_br_context(tag_names):
            score += cfg.PENALTY_INTL_SEM_BR
            breakdown["intl_sem_br"] = cfg.PENALTY_INTL_SEM_BR
    
    # -15: Tema de nicho
    if categories & cfg.NICHE_CATEGORY_IDS:
        score += cfg.PENALTY_NICHO
        breakdown["nicho"] = cfg.PENALTY_NICHO
    
    # -10: Conteúdo curto (< 300 palavras)
    if word_count < cfg.MIN_WORDS_PENALTY:
        score += cfg.PENALTY_CURTO
        breakdown["curto"] = cfg.PENALTY_CURTO
    
    # -10: Sem imagem
    if not featured_media or int(featured_media) == 0:
        score += cfg.PENALTY_SEM_IMAGEM
        breakdown["sem_imagem"] = cfg.PENALTY_SEM_IMAGEM
    
    # -5: Título muito curto
    if title_len < 30:
        score += cfg.PENALTY_TITULO_CURTO
        breakdown["titulo_curto"] = cfg.PENALTY_TITULO_CURTO
    
    breakdown["word_count"] = word_count
    breakdown["title_len"] = title_len
    breakdown["total_objetivo"] = score
    
    return max(score, 0), breakdown


# ─── Fase 2: Score LLM ──────────────────────────────

def score_llm(title: str, excerpt: str) -> int:
    """
    Avalia relevância editorial via Gemini Flash.
    Retorna score de 0 a 50.
    Fallback retorna LLM_FALLBACK_SCORE se falhar.
    """
    try:
        from google import genai
        
        key_idx = hash(title) % len(cfg.GEMINI_KEYS) if cfg.GEMINI_KEYS else 0
        key = cfg.GEMINI_KEYS[key_idx] if cfg.GEMINI_KEYS else None
        if not key:
            logger.warning("Sem GEMINI_API_KEY — retornando score fallback")
            return cfg.LLM_FALLBACK_SCORE
        
        client = genai.Client(api_key=key)
        
        prompt = cfg.LLM_CURATOR_SCORE_PROMPT.format(
            title=title,
            excerpt=excerpt or "(sem resumo)"
        )
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{cfg.LLM_CURATOR_SYSTEM_PROMPT}\n\n{prompt}",
        )
        
        # Extrair número da resposta
        text = response.text.strip()
        # Pegar primeiro número inteiro encontrado
        match = re.search(r"\b(\d{1,2})\b", text)
        if match:
            score = int(match.group(1))
            return min(max(score, 0), 50)
        
        logger.warning("LLM não retornou número válido: %s", text[:100])
        return cfg.LLM_FALLBACK_SCORE
        
    except Exception as e:
        logger.warning("Erro na avaliação LLM: %s", e)
        return cfg.LLM_FALLBACK_SCORE


# ─── Decisão de manchete (Premium) ──────────────────

def decide_headline(candidates: list[dict]) -> int:
    """
    Usa LLM Premium (Claude → GPT-4o → Gemini Pro) para decidir
    qual dos candidatos deve ser a manchete principal.
    
    Args:
        candidates: lista de dicts com {post_id, post_title, post_excerpt, score}
    
    Returns:
        Índice do candidato escolhido (0-based), ou 0 se falhar.
    """
    if not candidates:
        return 0
    if len(candidates) == 1:
        return 0
    
    # Formatar candidatos
    text_candidates = ""
    for i, c in enumerate(candidates[:5], 1):
        text_candidates += f"\n{i}. [{c['score']}pts] {c['post_title']}"
        if c.get("post_excerpt"):
            text_candidates += f"\n   {c['post_excerpt'][:150]}"
    
    prompt = cfg.LLM_HEADLINE_PROMPT.format(
        candidates=text_candidates,
        count=min(len(candidates), 5),
    )
    
    # Cascata: Claude → GPT-4o → Gemini Pro → fallback (maior score)
    providers = [
        ("claude", _call_claude_headline),
        ("openai", _call_openai_headline),
        ("gemini", _call_gemini_headline),
    ]
    
    for provider_name, call_fn in providers:
        try:
            result = call_fn(cfg.LLM_HEADLINE_SYSTEM_PROMPT, prompt)
            match = re.search(r"\b(\d)\b", result.strip())
            if match:
                idx = int(match.group(1)) - 1  # 1-based → 0-based
                if 0 <= idx < len(candidates):
                    logger.info("Manchete decidida por %s: candidato %d", provider_name, idx + 1)
                    return idx
        except Exception as e:
            logger.warning("Erro em %s para manchete: %s", provider_name, e)
    
    # Fallback: maior score
    logger.info("Manchete por fallback (maior score)")
    return 0


def _call_claude_headline(system_prompt: str, user_prompt: str) -> str:
    """Claude Sonnet 4 para decisão editorial."""
    key = cfg.ANTHROPIC_KEYS[0] if cfg.ANTHROPIC_KEYS else None
    if not key:
        raise ValueError("Sem ANTHROPIC_API_KEY")
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=cfg.LLM_TIMEOUT)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _call_openai_headline(system_prompt: str, user_prompt: str) -> str:
    """GPT-4o para decisão editorial."""
    key = cfg.OPENAI_KEYS[0] if cfg.OPENAI_KEYS else None
    if not key:
        raise ValueError("Sem OPENAI_API_KEY")
    from openai import OpenAI
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=100,
        timeout=cfg.LLM_TIMEOUT,
    )
    return response.choices[0].message.content


def _call_gemini_headline(system_prompt: str, user_prompt: str) -> str:
    """Gemini 2.5 Pro para decisão editorial."""
    key = cfg.GEMINI_KEYS[0] if cfg.GEMINI_KEYS else None
    if not key:
        raise ValueError("Sem GEMINI_API_KEY")
    from google import genai
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model="gemini-2.5-pro-preview-05-06",
        contents=f"{system_prompt}\n\n{user_prompt}",
    )
    return response.text


# ─── Score combinado ─────────────────────────────────

def score_post(post: dict, llm_budget: dict) -> tuple[int, dict]:
    """
    Calcula score total: objetivo + LLM.
    
    Args:
        post: dados do post
        llm_budget: {"remaining": int} — decrementado a cada chamada LLM
    
    Returns:
        (score_final, breakdown_dict)
    """
    obj_score, breakdown = score_objective(post)
    
    # Eliminado por filtro?
    if obj_score < 0:
        return -1, breakdown
    
    breakdown["score_objetivo"] = obj_score
    
    # Chamar LLM se score objetivo alto o suficiente e budget permite
    if obj_score >= cfg.LLM_SCORE_THRESHOLD and llm_budget["remaining"] > 0:
        llm_score = score_llm(
            post.get("post_title", ""),
            post.get("post_excerpt", ""),
        )
        llm_budget["remaining"] -= 1
        breakdown["score_llm"] = llm_score
        total = obj_score + llm_score
    else:
        breakdown["score_llm"] = 0
        breakdown["llm_skipped"] = True
        total = obj_score
    
    breakdown["score_total"] = total
    return total, breakdown
