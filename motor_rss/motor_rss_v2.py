
#!/usr/bin/env python3

"""

Motor RSS v2 — brasileira.news

Pipeline automatizado de coleta, reescrita e publicação de notícias.

"""



import fcntl

import json

import logging

import os

import signal

import sys

import time

from datetime import datetime, timedelta, timezone
from pathlib import Path



import feedparser

import requests

from bs4 import BeautifulSoup



import config

import db

import image_handler

import llm_router

import wp_publisher



FEEDS_POR_CICLO = 60



def setup_logging():

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = config.LOG_DIR / f"rss_{datetime.now().strftime('%Y-%m-%d')}.log"

    formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")

    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)

    console_handler.setFormatter(formatter)

    logger = logging.getLogger("motor_rss")

    logger.setLevel(logging.INFO)

    if not logger.handlers:

        logger.addHandler(file_handler)

        logger.addHandler(console_handler)

    return logger



logger = setup_logging()

_running = True



def _signal_handler(signum, frame):

    global _running

    logger.info("Sinal %s recebido. Encerrando após ciclo atual...", signum)

    _running = False



signal.signal(signal.SIGTERM, _signal_handler)

signal.signal(signal.SIGINT, _signal_handler)



def load_feeds():

    try:

        with open(config.FEEDS_FILE, "r", encoding="utf-8") as f:

            data = json.load(f)

        feeds = [fd for fd in data.get("feeds", []) if fd.get("ativo", True)]

        logger.info("Carregados %d feeds ativos de %s", len(feeds), config.FEEDS_FILE)

        return feeds

    except Exception as e:

        logger.error("Erro ao carregar feeds.json: %s", e)

        return []



def selecionar_feeds_ciclo(feeds):

    total = len(feeds)

    if total <= FEEDS_POR_CICLO:

        return feeds

    num_blocos = max(1, total // FEEDS_POR_CICLO)

    bloco = (datetime.now().hour * 2 + datetime.now().minute // 30) % num_blocos

    inicio = bloco * FEEDS_POR_CICLO

    selecionados = feeds[inicio: inicio + FEEDS_POR_CICLO]

    logger.info("Bloco %d/%d — feeds %d a %d de %d total", bloco+1, num_blocos, inicio, inicio+len(selecionados), total)

    return selecionados



def fetch_feed_entries(feed, cutoff):

    url = feed["url"]

    nome = feed["nome"]

    tema = feed.get("tema", "geral")

    try:

        parsed = feedparser.parse(url)

        if parsed.bozo and not parsed.entries:

            logger.warning("Feed com erro (%s): %s", nome, parsed.bozo_exception)

            return []

        entries = []

        for entry in parsed.entries:

            published = entry.get("published_parsed") or entry.get("updated_parsed")

            entry_date = datetime(*published[:6], tzinfo=timezone.utc) if published else datetime.now(timezone.utc)

            if entry_date < cutoff:

                continue

            link = entry.get("link", "")

            title = entry.get("title", "").strip()

            if not link or not title:

                continue

            summary = entry.get("summary", entry.get("description", ""))

            entries.append({"title": title, "link": link, "summary": summary, "date": entry_date, "feed_name": nome, "feed_tema": tema})

        logger.info("Feed %s: %d entradas recentes", nome, len(entries))

        return entries

    except Exception as e:

        logger.warning("Erro ao processar feed %s: %s", nome, e)

        return []



def extract_full_content(url):

    try:

        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

        resp = requests.get(url, headers=headers, timeout=config.HTTP_TIMEOUT)

        resp.raise_for_status()

        resp.encoding = resp.apparent_encoding or "utf-8"

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup.find_all(["script", "style", "nav", "footer", "aside", "iframe"]):

            tag.decompose()

        for selector in ["article", '[class*="article-body"]', '[class*="post-content"]', '[class*="entry-content"]', '[class*="texto"]', "main"]:

            element = soup.select_one(selector)

            if element:

                text = element.get_text(separator="\n", strip=True)

                if len(text) > 200:

                    return text[:8000]

        body = soup.find("body")

        if body:

            return body.get_text(separator="\n", strip=True)[:8000]

        return ""

    except Exception as e:

        logger.warning("Erro ao extrair conteúdo de %s: %s", url[:80], e)

        return ""



def extract_html_content(url):

    try:

        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

        resp = requests.get(url, headers=headers, timeout=config.HTTP_TIMEOUT)

        resp.raise_for_status()

        return resp.text

    except Exception as e:

        logger.debug("Erro ao buscar HTML de %s: %s", url[:80], e)

        return ""



def calculate_relevance(entry):

    score = 50.0

    score *= {"governo": 1.2, "imprensa": 1.0}.get(entry.get("feed_tema", "geral"), 1.0)

    if len(entry.get("title", "")) > 40:

        score *= 1.1

    entry_date = entry.get("date")

    if entry_date:

        hours_ago = (datetime.now(timezone.utc) - entry_date).total_seconds() / 3600

        if hours_ago < 3: score *= 1.3

        elif hours_ago < 6: score *= 1.2

        elif hours_ago < 12: score *= 1.1

    return round(min(score, 100.0), 3)



def deduplicate_entries(entries):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path("/home/bitnami")))
    from deduplicador_unificado import link_ja_processado

    unique = []
    seen_urls = set()
    for entry in entries:
        url = entry["link"]
        if url in seen_urls or link_ja_processado(url, entry["title"]):
            continue
        seen_urls.add(url)
        unique.append(entry)
    return unique

def process_article(entry, categories):

    title = entry["title"]

    link = entry["link"]

    feed_name = entry["feed_name"]

    logger.info("─── Processando: %s ───", title[:70])

    content = extract_full_content(link)

    if not content or len(content) < 100:

        content = entry.get("summary", "")

        if not content or len(content) < 50:

            logger.warning("Conteúdo insuficiente para: %s", title[:60])

            return False

    article_tier = llm_router.classify_tier(
        source=feed_name,
        feed_tema=entry.get("feed_tema", ""),
        content_length=len(content),
        score=entry.get("score", 50.0),
    )

    article_data, llm_used = llm_router.generate_article(title=title, content=content, source=feed_name, categories=categories, url=link, tier=article_tier)

    if not article_data:

        logger.warning("Todos LLMs falharam para: %s", title[:60])

        return False

    generated_content = article_data.get("conteudo", "")

    if len(generated_content.split()) < config.MIN_CONTENT_WORDS:

        logger.warning("Conteúdo muito curto: %s", title[:60])

        return False

    html_content = extract_html_content(link)

    keywords = " ".join(article_data.get("tags", [])[:3])

    # Verificar se fonte é oficial (EBC, Gov.br, Senado, etc.)
    # Se for, o Tier 1 do curador vai puxar a foto direto do HTML — sem gerar queries.
    sys.path.insert(0, str(Path("/home/bitnami")))
    from curador_imagens_unificado import is_official_source
    source_is_official = is_official_source(link)

    explicit_gov = ""
    explicit_commons = ""
    explicit_block_stock = None

    if source_is_official:
        logger.info("[IMAGEM] Fonte oficial (%s). Tier 1 puxará foto da matéria.", link[:60])
    else:
        # Verificar se o LLM principal foi um modelo PREMIUM (capaz de atuar como Editor de Foto)
        _premium_models = ("gpt-4o", "sonnet", "claude", "2.5-pro", "grok-4")
        llm_is_premium = any(m in llm_used.lower() for m in _premium_models) if llm_used else False

        if llm_is_premium and article_data.get("imagem_busca_gov"):
            # LLM premium já fez o trabalho — confiar nos campos
            explicit_gov = article_data.get("imagem_busca_gov", "")
            explicit_commons = article_data.get("imagem_busca_commons", "")
            explicit_block_stock = article_data.get("block_stock_images")
            logger.info("[IMAGEM] LLM premium (%s) — confiando: gov='%s'", llm_used, explicit_gov)
        else:
            # LLM standard (Flash etc.) ou campos ausentes — SEMPRE chamar Editor Premium
            logger.info("[IMAGEM] LLM standard (%s). Chamando Editor de Fotografia premium...", llm_used)
            photo_prompt = (
                f"Você é o Editor de Fotografia do portal Brasileira.News.\n"
                f"Para PESSOAS: busque nome + status jornalístico (preso, ministro, réu). Nunca detalhes de cena.\n"
                f"Para LOCAIS/EVENTOS sem pessoa: busque o nome do local.\n\n"
                f"Título: {article_data.get('titulo', title)}\n"
                f"Categoria: {article_data.get('categoria', '')}\n"
                f"Excerpt: {article_data.get('excerpt', '')}\n"
                f"Tags: {', '.join(article_data.get('tags', []))}\n\n"
                f"Retorne APENAS JSON com:\n"
                f"imagem_busca_gov: nome da pessoa (+ status) ou nome do local. Máx 3 palavras.\n"
                f"imagem_busca_commons: nome formal/enciclopédico para Wikimedia\n"
                f"block_stock_images: true se factual, false se abstrato"
            )
            try:
                photo_result, photo_provider = llm_router.call_llm(
                    system_prompt="Você é um editor de fotografia jornalística experiente. Responda apenas em JSON válido.",
                    user_prompt=photo_prompt,
                    tier=llm_router.TIER_PHOTO_EDITOR,
                    parse_json=True,
                )
                if photo_result and isinstance(photo_result, dict):
                    explicit_gov = photo_result.get("imagem_busca_gov", "")
                    explicit_commons = photo_result.get("imagem_busca_commons", "")
                    explicit_block_stock = photo_result.get("block_stock_images", True)
                    logger.info("[IMAGEM] Editor Foto (%s): gov='%s'", photo_provider, explicit_gov)
            except Exception as e:
                logger.warning("[IMAGEM] Falha Editor Foto: %s", e)

    media_result = image_handler.get_featured_image(
        html_content=html_content,
        source_url=link,
        title=article_data.get("titulo", title),
        keywords=keywords,
        explicit_gov_query=explicit_gov,
        explicit_commons_query=explicit_commons,
        explicit_block_stock=explicit_block_stock
    )

    media_id = media_result[0] if isinstance(media_result, tuple) else media_result

    if not media_id:

        logger.warning("Sem imagem para: %s — publicando sem featured image", title[:60])

    post_id = wp_publisher.publish_post(

        title=article_data["titulo"],

        content=generated_content,

        excerpt=article_data.get("excerpt", ""),

        category_name=article_data.get("categoria", "Brasil"),

        tag_names=article_data.get("tags", []),

        featured_media=media_id,

        seo_title=article_data.get("seo_title", ""),

        seo_description=article_data.get("seo_description", ""),

        push_notification=article_data.get("push_notification", ""),

        prompt_imagem=article_data.get("prompt_imagem", ""),

        legenda_imagem=article_data.get("legenda_imagem", ""),

    )

    if not post_id:

        logger.error("Falha ao publicar no WP: %s", title[:60])

        return False

    db.register_published(post_id, link, feed_name, llm_used)

    logger.info("PUBLICADO | post_id=%d | LLM=%s | %s", post_id, llm_used, article_data["titulo"][:60])

    return True



def run_cycle():

    cycle_start = time.time()

    logger.info("=" * 60)

    logger.info("INÍCIO DO CICLO — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    logger.info("=" * 60)

    feeds = load_feeds()

    if not feeds:

        logger.error("Nenhum feed disponível. Abortando ciclo.")

        return

    feeds_ciclo = selecionar_feeds_ciclo(feeds)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    all_entries = []

    for feed in feeds_ciclo:

        entries = fetch_feed_entries(feed, cutoff)

        all_entries.extend(entries)

    logger.info("Total de entradas coletadas: %d", len(all_entries))

    if not all_entries:

        logger.info("Nenhuma entrada nova encontrada. Ciclo encerrado.")

        return

    unique_entries = deduplicate_entries(all_entries)

    if not unique_entries:

        logger.info("Todas as entradas já foram publicadas. Ciclo encerrado.")

        return

    for entry in unique_entries:

        entry["score"] = calculate_relevance(entry)

    unique_entries.sort(key=lambda x: x["score"], reverse=True)

    selected = unique_entries[:config.MAX_ARTICLES_PER_CYCLE]

    logger.info("Selecionados %d artigos (de %d disponíveis)", len(selected), len(unique_entries))

    published_count = 0

    failed_count = 0

    for i, entry in enumerate(selected, 1):

        if not _running:

            logger.info("Parada solicitada. Encerrando processamento.")

            break

        logger.info("--- Artigo %d/%d | score=%.1f ---", i, len(selected), entry["score"])

        try:

            success = process_article(entry, config.VALID_CATEGORIES)

            if success:

                published_count += 1

            else:

                failed_count += 1

        except Exception as e:

            logger.error("Erro inesperado ao processar '%s': %s", entry.get("title", "")[:60], e, exc_info=True)

            failed_count += 1

        if i < len(selected):

            time.sleep(config.WP_POST_DELAY)

    elapsed = time.time() - cycle_start

    logger.info("=" * 60)

    logger.info("FIM DO CICLO — Publicados: %d | Falhas: %d | Tempo: %.0fs", published_count, failed_count, elapsed)

    logger.info("=" * 60)



LOCK_FILE = Path(__file__).resolve().parent / "motor_rss_v2.lock"
_lock_fd = None


def acquire_lock():
    """Adquire file lock exclusivo. Retorna True se conseguiu, False se já está rodando."""
    global _lock_fd
    try:
        _lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        return True
    except (IOError, OSError):
        return False


def release_lock():
    """Libera o file lock."""
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass


def main():

    if not acquire_lock():
        logger.warning("Outra instância do Motor RSS v2 já está em execução. Saindo.")
        sys.exit(0)

    logger.info("Motor RSS v2 — brasileira.news — Iniciando...")

    logger.info("Feeds por ciclo: %d | Artigos por ciclo: máx %d", FEEDS_POR_CICLO, config.MAX_ARTICLES_PER_CYCLE)

    try:

        db.ensure_control_table()

    except Exception as e:

        logger.error("Erro ao criar tabela de controle: %s", e)

    try:
        run_cycle()
    except Exception as e:
        logger.error("Erro fatal no ciclo: %s", e, exc_info=True)

    release_lock()
    logger.info("Motor encerrado graciosamente.")



if __name__ == "__main__":

    main()

