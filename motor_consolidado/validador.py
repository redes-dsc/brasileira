"""
Validador de qualidade para matérias consolidadas.
Checa contagem de palavras, citação de fontes e plágio.
"""

import logging
import re
from difflib import SequenceMatcher

from config_consolidado import (
    MIN_SYNTHESIS_WORDS, MAX_PLAGIARISM_RATIO,
    MIN_SOURCES_PER_TOPIC,
)

logger = logging.getLogger("motor_consolidado")


def _count_words(html_text: str) -> int:
    """Conta palavras no texto, removendo tags HTML."""
    plain = re.sub(r"<[^>]+>", " ", html_text)
    words = plain.split()
    return len(words)


def validate_word_count(content: str, min_words: int = MIN_SYNTHESIS_WORDS) -> bool:
    """Verifica se o conteúdo tem o mínimo de palavras."""
    count = _count_words(content)
    if count < min_words:
        logger.warning("Conteúdo com apenas %d palavras (mínimo: %d)", count, min_words)
        return False
    return True


def validate_source_citations(content: str, sources: list[dict], min_sources: int = MIN_SOURCES_PER_TOPIC) -> bool:
    """Verifica se o texto cita ao menos N fontes diferentes por nome."""
    content_lower = content.lower()
    cited = set()
    for src in sources:
        portal = src.get("portal_name", "")
        if portal and portal.lower() in content_lower:
            cited.add(portal)
    
    if len(cited) < min_sources:
        logger.warning(
            "Apenas %d fontes citadas no texto (mínimo: %d). Citadas: %s",
            len(cited), min_sources, cited,
        )
        return False
    return True


def validate_no_plagiarism(content: str, sources: list[dict], max_ratio: float = MAX_PLAGIARISM_RATIO) -> bool:
    """
    Verifica que nenhuma fonte única contribui > max_ratio do texto final.
    Usa SequenceMatcher para medir sobreposição.
    """
    # Limpar HTML do conteúdo consolidado
    clean_content = re.sub(r"<[^>]+>", " ", content).lower()
    clean_content = re.sub(r"\s+", " ", clean_content).strip()

    if not clean_content:
        return True

    for src in sources:
        src_text = src.get("conteudo", "")
        if not src_text:
            continue
        clean_src = re.sub(r"\s+", " ", src_text.lower()).strip()
        
        # SequenceMatcher em textos grandes: usar amostragem
        if len(clean_content) > 3000:
            # Comparar blocos de 1000 chars
            max_r = 0.0
            for start in range(0, min(len(clean_content), 5000), 1000):
                chunk = clean_content[start:start+1000]
                r = SequenceMatcher(None, chunk, clean_src[:3000]).ratio()
                max_r = max(max_r, r)
            ratio = max_r
        else:
            ratio = SequenceMatcher(None, clean_content, clean_src[:5000]).ratio()

        if ratio > max_ratio:
            logger.warning(
                "Possível plágio: %.1f%% de sobreposição com %s (máx: %.0f%%)",
                ratio * 100, src.get("portal_name", "?"), max_ratio * 100,
            )
            return False

    return True


def validate_has_blockquote(content: str) -> bool:
    """Verifica se há ao menos uma citação direta (blockquote)."""
    if "<blockquote" in content.lower():
        return True
    logger.info("Sem blockquote no conteúdo (recomendado, não obrigatório)")
    return True  # Não bloqueia, só avisa


def validate_article(article: dict, sources: list[dict]) -> tuple[bool, list[str]]:
    """
    Executa todas as validações no artigo consolidado.
    Retorna (passou, [lista_de_erros]).
    """
    errors = []
    content = article.get("conteudo", "")

    if not validate_word_count(content):
        errors.append(f"Conteúdo abaixo do mínimo de {MIN_SYNTHESIS_WORDS} palavras ({_count_words(content)} encontradas)")

    if not validate_source_citations(content, sources):
        cited = {s["portal_name"] for s in sources if s.get("portal_name", "").lower() in content.lower()}
        errors.append(f"Apenas {len(cited)} fontes citadas no texto (mínimo: {MIN_SOURCES_PER_TOPIC})")

    if not validate_no_plagiarism(content, sources):
        errors.append(f"Possível plágio: sobreposição > {MAX_PLAGIARISM_RATIO*100:.0f}% com fonte única")

    validate_has_blockquote(content)

    passed = len(errors) == 0
    if passed:
        logger.info("Validação OK: %d palavras, fontes citadas, sem plágio", _count_words(content))
    else:
        logger.warning("Validação FALHOU: %s", "; ".join(errors))

    return passed, errors
