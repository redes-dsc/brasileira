"""
Deduplicação e atualização de matérias consolidadas.
Verifica se o tema já foi coberto e decide entre criar novo ou atualizar existente.
"""

import logging
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import requests
import config
import db
from config_consolidado import (
    DEDUP_WINDOW_HOURS, THEME_COOLDOWN_HOURS,
    FEED_NAME_CONSOLIDADA,
)

logger = logging.getLogger("motor_consolidado")


def _normalize_for_comparison(title: str) -> str:
    """Normaliza título para comparação de similaridade."""
    title = re.sub(r"<[^>]+>", "", title)
    title = re.sub(r"[^\w\s]", " ", title.lower())
    return re.sub(r"\s+", " ", title).strip()


def check_recent_coverage(topic_title: str, hours: int = DEDUP_WINDOW_HOURS) -> dict | None:
    """
    Verifica se o Brasileira.News já tem post sobre o mesmo tema
    nas últimas N horas. Busca por similaridade de título.
    Retorna o post existente ou None.
    """
    normalized_topic = _normalize_for_comparison(topic_title)

    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT ID, post_title, post_date, post_status
                FROM {db._t('posts')}
                WHERE post_status IN ('publish', 'draft')
                  AND post_date >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                  AND post_type = 'post'
                ORDER BY post_date DESC
                LIMIT 200
                """,
                (hours,),
            )
            posts = cursor.fetchall()
            cursor.close()

        for post in posts:
            post_title = _normalize_for_comparison(post.get("post_title", ""))
            similarity = SequenceMatcher(None, normalized_topic, post_title).ratio()
            if similarity >= 0.80:  # threshold mais alto para evitar falsos positivos
                logger.info(
                    "Cobertura existente encontrada (sim=%.2f): '%s' vs '%s'",
                    similarity, topic_title[:50], post.get("post_title", "")[:50],
                )
                return {
                    "post_id": post["ID"],
                    "title": post["post_title"],
                    "date": post["post_date"],
                    "similarity": similarity,
                }

    except Exception as e:
        logger.error("Erro ao verificar cobertura existente: %s", e)

    return None


def check_recent_synthesis(topic_title: str, hours: int = THEME_COOLDOWN_HOURS) -> bool:
    """
    Verifica se este tema já foi sintetizado
    nas últimas N horas (tabela rss_control).
    """
    normalized_topic = _normalize_for_comparison(topic_title)

    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT rc.source_url, p.post_title
                FROM {db._t('rss_control')} rc
                JOIN {db._t('posts')} p ON rc.post_id = p.ID
                WHERE rc.feed_name = %s
                  AND rc.published_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                """,
                (FEED_NAME_CONSOLIDADA, hours),
            )
            rows = cursor.fetchall()
            cursor.close()

        for row in rows:
            post_title = _normalize_for_comparison(row.get("post_title", ""))
            if SequenceMatcher(None, normalized_topic, post_title).ratio() >= 0.50:
                logger.info(
                    "Tema já sintetizado nas últimas %dh: %s",
                    hours, row.get("post_title", "")[:60],
                )
                return True

    except Exception as e:
        logger.error("Erro ao verificar sínteses recentes: %s", e)

    return False


def update_existing_post(post_id: int, new_content: str, new_sources: list[str]) -> bool:
    """
    Atualiza post existente via WP REST API (PATCH).
    Adiciona nota de atualização no início.
    """

    now = datetime.now().strftime("%H:%M")
    sources_str = ", ".join(new_sources[:3])
    update_note = (
        f'<p><em><strong>Atualizado às {now}</strong> com informações de {sources_str}.</em></p>\n\n'
    )

    updated_content = update_note + new_content

    try:
        resp = requests.post(
            f"{config.WP_API_BASE}/posts/{post_id}",
            auth=(config.WP_USER, config.WP_APP_PASS),
            json={"content": updated_content},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            logger.info("Post %d atualizado com sucesso", post_id)
            return True
        else:
            logger.warning(
                "Falha ao atualizar post %d (HTTP %d): %s",
                post_id, resp.status_code, resp.text[:200],
            )
    except Exception as e:
        logger.error("Erro ao atualizar post %d: %s", post_id, e)

    return False
