#!/usr/bin/env python3
"""
Motor Consolidado (Raia 3) — Orquestrador principal.
Monitora portais, detecta trending, sintetiza e publica matérias consolidadas.

Uso:
    python3 motor_consolidado.py                  # Ciclo normal
    DRY_RUN=1 python3 motor_consolidado.py        # Sem publicar
    PUBLISH_AS_DRAFT=1 python3 motor_consolidado.py  # Publica como rascunho

Agendamento (crontab):
    0 0,2,4,6,8,10,12,14,16,18,20,22 * * * /home/bitnami/venv/bin/python3 \
        /home/bitnami/motor_consolidado/motor_consolidado.py >> /home/bitnami/logs/raia3_cron.log 2>&1
"""

import fcntl
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# Setup paths antes de qualquer import local
_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(Path("/home/bitnami/motor_rss")))
sys.path.insert(0, str(Path("/home/bitnami/motor_scrapers")))
sys.path.insert(0, str(Path("/home/bitnami")))

from config_consolidado import (
    LOG_FILE, LOG_DIR, MAX_ARTICLES_PER_CYCLE,
    ARTICLE_MIN_INTERVAL_HOURS, DRY_RUN, PUBLISH_AS_DRAFT,
)
import db

# ── Logging ──────────────────────────────────────────────

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("motor_consolidado")

# ── Lock File ────────────────────────────────────────────

LOCK_FILE = _BASE / "motor_consolidado.pid"
_lock_fd = None


def acquire_lock():
    """Adquire lock exclusivo para evitar execução paralela."""
    global _lock_fd
    _lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        return True
    except IOError:
        logger.warning("Outra instância do motor_consolidado já está rodando.")
        return False


def release_lock():
    """Libera o lock."""
    global _lock_fd
    if _lock_fd:
        fcntl.flock(_lock_fd, fcntl.LOCK_UN)
        _lock_fd.close()
        _lock_fd = None
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass


# ── Signal Handling ──────────────────────────────────────

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Sinal %d recebido. Finalizando após o ciclo atual...", signum)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ── Cycle Counter ────────────────────────────────────────

CYCLE_FILE = _BASE / ".cycle_counter"


def _get_cycle_number() -> int:
    """Lê e incrementa o contador de ciclos."""
    try:
        if CYCLE_FILE.exists():
            n = int(CYCLE_FILE.read_text().strip())
        else:
            n = 0
    except (ValueError, OSError):
        n = 0
    n += 1
    CYCLE_FILE.write_text(str(n))
    return n


# ── Pipeline Principal ───────────────────────────────────

def run_cycle():
    """Executa um ciclo completo do motor consolidado."""
    from scraper_homes import scrape_all_portals
    from detector_trending import detect_trending
    from sintetizador import synthesize_article
    from validador import validate_article
    from deduplicador import check_recent_coverage, check_recent_synthesis
    from publicador_consolidado import publish_consolidated

    cycle = _get_cycle_number()
    start_time = time.time()
    articles_published = 0

    logger.info("=" * 60)
    logger.info("RAIA 3 — MOTOR CONSOLIDADO — CICLO %d", cycle)
    logger.info("Horário: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if DRY_RUN:
        logger.info("*** MODO DRY RUN — nada será publicado ***")
    if PUBLISH_AS_DRAFT:
        logger.info("*** MODO DRAFT — posts serão criados como rascunho ***")
    logger.info("=" * 60)

    # Garantir tabela de controle
    try:
        db.ensure_control_table()
    except Exception as e:
        logger.error("Erro ao verificar tabela de controle: %s", e)
        # Continuar mesmo assim

    # ETAPA 1 — Raspar títulos
    logger.info("----- ETAPA 1: Raspagem de títulos -----")
    try:
        all_titles = scrape_all_portals(cycle_number=cycle)
    except Exception as e:
        logger.error("ERRO FATAL na raspagem de títulos: %s", e)
        return 0

    if not all_titles:
        logger.warning("Nenhum título raspado — encerrando ciclo.")
        return 0

    # ETAPA 2 — Detectar trending
    logger.info("----- ETAPA 2: Detecção de trending -----")
    try:
        trending = detect_trending(all_titles)
    except Exception as e:
        logger.error("ERRO na detecção de trending: %s", e)
        return 0

    if not trending:
        logger.info("Nenhum tema trending detectado — encerrando ciclo.")
        return 0

    logger.info("Temas trending encontrados: %d", len(trending))

    # ETAPA 3 — Processar cada tema (max MAX_ARTICLES_PER_CYCLE)
    logger.info("----- ETAPA 3: Síntese e publicação -----")

    for i, topic in enumerate(trending):
        if articles_published >= MAX_ARTICLES_PER_CYCLE:
            logger.info("Limite de %d artigos por ciclo atingido.", MAX_ARTICLES_PER_CYCLE)
            break

        if _shutdown:
            logger.info("Shutdown solicitado — interrompendo processamento.")
            break

        topic_label = topic["topic_label"]
        logger.info(
            "\n--- Tema %d/%d: %s ---",
            i + 1, len(trending), topic_label[:60],
        )
        logger.info("  Fontes: %s | Score: %d", ", ".join(topic["sources"]), topic["score"])

        # 3a. Deduplicação
        existing = check_recent_coverage(topic_label)
        if existing:
            logger.info(
                "Tema já coberto (post #%d, sim=%.2f): %s",
                existing["post_id"], existing["similarity"],
                existing["title"][:50],
            )
            continue

        if check_recent_synthesis(topic_label):
            logger.info("Tema já sintetizado recentemente — pulando.")
            continue

        # 3b. Síntese
        try:
            article, sources = synthesize_article(topic)
        except Exception as e:
            logger.error("Erro na síntese de '%s': %s", topic_label[:50], e)
            continue

        if not article:
            logger.warning("Síntese falhou para '%s' (fontes insuficientes ou LLM error)", topic_label[:50])
            continue

        # 3c. Validação
        passed, errors = validate_article(article, sources)
        if not passed:
            logger.warning(
                "Validação falhou para '%s': %s",
                topic_label[:50], "; ".join(errors),
            )
            # Tentar publicar mesmo com aviso (exceto plágio)
            if any("plágio" in e.lower() for e in errors):
                logger.error("Artigo descartado por plágio: %s", topic_label[:50])
                continue
            logger.info("Publicando com avisos (não-plágio)")

        # 3d. Publicação
        try:
            post_id = publish_consolidated(article, sources)
        except Exception as e:
            logger.error("Erro na publicação de '%s': %s", topic_label[:50], e)
            continue

        if post_id:
            articles_published += 1
            logger.info(
                "✓ Consolidada #%d publicada (post_id=%s): %s",
                articles_published, post_id, article.get("titulo", "?")[:60],
            )

            # Pausa entre publicações
            if articles_published < MAX_ARTICLES_PER_CYCLE:
                time.sleep(5)

    # Resumo do ciclo
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(
        "CICLO %d FINALIZADO em %.1fs | %d matérias publicadas | %d trending detectados",
        cycle, elapsed, articles_published, len(trending),
    )
    logger.info("=" * 60)

    return articles_published


# ── Entry Point ──────────────────────────────────────────

def main():
    """Ponto de entrada principal."""
    logger.info("Motor Consolidado (Raia 3) iniciando...")

    if not acquire_lock():
        sys.exit(1)

    try:
        count = run_cycle()
        logger.info("Motor Consolidado finalizado. Artigos publicados: %d", count)
    except Exception as e:
        logger.critical("ERRO NÃO TRATADO no motor consolidado: %s", e, exc_info=True)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
