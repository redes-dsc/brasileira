
#!/usr/bin/env python3

"""

Motor Scrapers v2 (Raia 2) — brasileira.news

Pipeline de scraping direto para sites sem RSS.

Reutiliza módulos da Raia 1: config, db, llm_router, wp_publisher, image_handler.

"""



import fcntl

import json

import logging

import os

import re

import signal

import sys

import time

from concurrent.futures import ThreadPoolExecutor, as_completed

from datetime import datetime, timedelta, timezone

from pathlib import Path

from urllib.parse import urljoin, urlparse

from urllib.robotparser import RobotFileParser



import chardet

import feedparser

import requests

from bs4 import BeautifulSoup



_RAIA1_DIR = Path("/home/bitnami/motor_rss")

if _RAIA1_DIR.exists():

    sys.path.insert(0, str(_RAIA1_DIR))



import config

import db

import image_handler

import llm_router

import wp_publisher

import detector_estrategia

import extrator_conteudo



def setup_logging():

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = config.LOG_DIR / f"motor_scrapers_{datetime.now().strftime('%Y-%m-%d')}.log"

    formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")

    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)

    console_handler.setFormatter(formatter)

    lgr = logging.getLogger("motor_scrapers")

    lgr.setLevel(logging.INFO)

    if not lgr.handlers:

        lgr.addHandler(file_handler)

        lgr.addHandler(console_handler)

    return lgr



logger = setup_logging()



SCRAPERS_FILE = Path(__file__).resolve().parent / "scrapers.json"

MAX_ARTICLES_PER_SOURCE = 5

MAX_ARTICLES_PER_CYCLE = 20

SCORE_MIN = 40

SCORE_GOV_BONUS = 10

REQUEST_TIMEOUT = 30

MAX_WORKERS = 5

DOMAIN_DELAY_MIN = 2.0

DOMAIN_DELAY_MAX = 5.0



_DEFAULT_HEADERS = {

    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",

    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",

    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",

    "Accept-Encoding": "gzip, deflate",

    "DNT": "1",

}



_FALLBACK_SELECTORS = [

    ("article h2 a", "article h3 a"),

    (".noticias h2 a", ".noticias h3 a"),

    (".lista-noticias a", ".lista-noticias h2"),

    ("main h2 a", "main h3 a"),

    ('[class*="noticia"] a', '[class*="news"] a'),

]



_running = True



def _signal_handler(signum, frame):

    global _running

    logger.info("Sinal %s recebido. Encerrando após ciclo atual...", signum)

    _running = False



signal.signal(signal.SIGTERM, _signal_handler)

signal.signal(signal.SIGINT, _signal_handler)



_blocked_domains: dict[str, float] = {}



def _is_domain_blocked(domain):

    if domain in _blocked_domains:

        if time.time() < _blocked_domains[domain]:

            return True

        del _blocked_domains[domain]

    return False



def _block_domain(domain, hours=1.0):

    _blocked_domains[domain] = time.time() + (hours * 3600)

    logger.warning("Domínio %s bloqueado por %.0fh", domain, hours)



_robots_cache: dict = {}



def _check_robots(url):

    parsed = urlparse(url)

    base = f"{parsed.scheme}://{parsed.netloc}"

    if base not in _robots_cache:

        rp = RobotFileParser()

        try:

            rp.set_url(f"{base}/robots.txt")

            rp.read()

            _robots_cache[base] = rp

        except Exception:

            _robots_cache[base] = RobotFileParser()

    rp = _robots_cache[base]

    allowed = rp.can_fetch(_DEFAULT_HEADERS["User-Agent"], url)

    if not allowed:

        logger.debug("Bloqueado por robots.txt: %s", url[:80])

    return allowed



def load_scrapers():

    try:

        with open(SCRAPERS_FILE, "r", encoding="utf-8") as f:

            data = json.load(f)

        fontes = [s for s in data.get("scrapers", []) if s.get("ativo", True)]

        logger.info("Carregadas %d fontes ativas de %s", len(fontes), SCRAPERS_FILE)

        return fontes

    except Exception as e:

        logger.error("Erro ao carregar scrapers.json: %s", e)

        return []



def _fetch_with_retry(url, retries=3, timeout=REQUEST_TIMEOUT):

    for attempt in range(retries):

        try:

            import cloudscraper
            scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
            resp = scraper.get(url, headers=_DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)

            if resp.status_code in (429, 503):

                domain = urlparse(url).netloc

                _block_domain(domain)

                return None

            if resp.status_code < 400:

                return resp

            logger.warning("HTTP %d em %s (tentativa %d/%d)", resp.status_code, url[:80], attempt+1, retries)

        except Exception as e:

            logger.warning("Erro de rede em %s (tentativa %d/%d): %s | Tipo: %s", url[:80], attempt+1, retries, e, type(e).__name__)

        if attempt < retries - 1:

            time.sleep(2 ** (attempt + 1))

    return None



def _decode_response(resp):

    raw = resp.content

    detected = chardet.detect(raw)

    encoding = detected.get("encoding", "utf-8") or "utf-8"

    return raw.decode(encoding, errors="replace")



def _extrair_links_html(fonte, html):

    soup = BeautifulSoup(html, "html.parser")

    url_base = fonte.get("url_noticias", fonte.get("url_home", ""))

    artigos = []

    seletor_lista = fonte.get("seletor_lista", "")

    seletor_titulo = fonte.get("seletor_titulo", "")

    seletor_link = fonte.get("seletor_link", "")

    items = []

    if seletor_lista:

        for sel in seletor_lista.split(","):

            sel = sel.strip()

            if sel:

                items = soup.select(sel)

                if items:

                    break

    if not items:

        for fallback_pair in _FALLBACK_SELECTORS:

            for sel in fallback_pair:

                items = soup.select(sel)

                if items:

                    logger.info("[FALLBACK] fonte=%s usando seletor '%s'", fonte.get("nome","?"), sel)

                    break

            if items:

                break

    if not items:

        logger.warning("Nenhum item encontrado para %s", fonte.get("nome","?"))

        return []

    for item in items[:20]:

        link_el = None

        titulo = ""

        url = ""

        if seletor_link:

            for sel in seletor_link.split(","):

                sel = sel.strip()

                if sel:

                    link_el = item.select_one(sel)

                    if link_el:

                        break

        if not link_el:

            link_el = item if item.name == "a" else item.find("a")

        if not link_el:

            continue

        url = link_el.get("href", "")

        if not url:

            continue

        url = urljoin(url_base, url)

        parsed_url = urlparse(url)

        if not parsed_url.scheme or not parsed_url.netloc:

            continue

        if seletor_titulo:

            for sel in seletor_titulo.split(","):

                sel = sel.strip()

                if sel:

                    titulo_el = item.select_one(sel)

                    if titulo_el:

                        titulo = titulo_el.get_text(strip=True)

                        break

        if not titulo:

            titulo = link_el.get_text(strip=True)

        if not titulo or len(titulo) < 10:

            continue

        data = ""

        seletor_data = fonte.get("seletor_data", "")

        if seletor_data:

            for sel in seletor_data.split(","):

                sel = sel.strip()

                if sel:

                    data_el = item.select_one(sel)

                    if data_el:

                        data = data_el.get("datetime","") or data_el.get_text(strip=True)

                        break

        imagem = ""

        seletor_imagem = fonte.get("seletor_imagem", "")

        if seletor_imagem:

            for sel in seletor_imagem.split(","):

                sel = sel.strip()

                if sel:

                    img_el = item.select_one(sel)

                    if img_el:

                        imagem = img_el.get("src","") or img_el.get("data-src","")

                        if imagem:

                            imagem = urljoin(url_base, imagem)

                        break

        artigos.append({"titulo": titulo, "url": url, "data": data, "imagem": imagem, "fonte_nome": fonte.get("nome",""), "grupo": fonte.get("grupo","")})

    return artigos




def _extrair_links_nextjs(fonte, html):

    next_data = detector_estrategia.detectar_next_data(html)

    if not next_data:

        logger.info("[FALLBACK] %s: __NEXT_DATA__ nao encontrado, usando HTML", fonte.get("nome","?"))

        return _extrair_links_html(fonte, html)

    artigos = []

    url_base = fonte.get("url_home", "")

    def _buscar(obj, depth=0):

        if depth > 10:

            return

        if isinstance(obj, dict):

            tem_titulo = any(k in obj for k in ("title","titulo","headline","name"))

            tem_url = any(k in obj for k in ("url","href","link","slug","path"))

            if tem_titulo and tem_url:

                titulo = obj.get("title") or obj.get("titulo") or obj.get("headline") or obj.get("name") or ""

                url = obj.get("url") or obj.get("href") or obj.get("link") or ""

                slug = obj.get("slug") or obj.get("path") or ""

                if not url and slug:

                    url = urljoin(url_base, slug)

                elif url and not url.startswith("http"):

                    url = urljoin(url_base, url)

                if titulo and url and len(str(titulo)) >= 10:

                    artigos.append({"titulo": str(titulo), "url": url, "data": str(obj.get("date", obj.get("publishedAt",""))), "imagem": str(obj.get("image", obj.get("thumbnail",""))), "fonte_nome": fonte.get("nome",""), "grupo": fonte.get("grupo","")})

            for val in obj.values():

                _buscar(val, depth+1)

        elif isinstance(obj, list):

            for item in obj:

                _buscar(item, depth+1)

    try:

        _buscar(next_data.get("props", {}))

    except Exception as e:

        logger.warning("Erro ao parsear __NEXT_DATA__ de %s: %s", fonte.get("nome","?"), e)

    return artigos or _extrair_links_html(fonte, html)





def _extrair_links_api_json(fonte, metadata):

    api_url = metadata.get("url_api","") or fonte.get("url_noticias","")

    resp = _fetch_with_retry(api_url)

    if not resp:

        return []

    artigos = []

    url_base = fonte.get("url_home","")

    try:

        data = resp.json()

        items = data if isinstance(data, list) else data.get("items", data.get("results", data.get("posts",[])))

        if not isinstance(items, list):

            return []

        for item in items[:20]:

            if not isinstance(item, dict):

                continue

            titulo = item.get("title",{}).get("rendered","") if isinstance(item.get("title"),dict) else str(item.get("title", item.get("titulo", item.get("headline",""))))

            url = str(item.get("link", item.get("url", item.get("href",""))))

            slug = str(item.get("slug",""))

            if not url and slug:

                url = urljoin(url_base, slug)

            if not titulo or not url or len(titulo) < 10:

                continue

            imagem = ""

            if isinstance(item.get("_embedded"), dict):

                media = item["_embedded"].get("wp:featuredmedia",[])

                if media and isinstance(media[0], dict):

                    imagem = media[0].get("source_url","")

            artigos.append({"titulo": titulo, "url": url, "data": str(item.get("date", item.get("published",""))), "imagem": imagem, "fonte_nome": fonte.get("nome",""), "grupo": fonte.get("grupo","")})

    except Exception as e:

        logger.warning("Erro ao parsear API JSON de %s: %s", fonte.get("nome","?"), e)

    return artigos





def _extrair_links_feed(fonte, metadata):

    feed_url = metadata.get("url_feed","") or fonte.get("url_noticias","")

    try:

        parsed = feedparser.parse(feed_url)

        if not parsed.entries:

            return []

        artigos = []

        for entry in parsed.entries[:20]:

            titulo = entry.get("title","").strip()

            url = entry.get("link","")

            if not titulo or not url:

                continue

            artigos.append({"titulo": titulo, "url": url, "data": str(entry.get("published", entry.get("updated",""))), "imagem": "", "fonte_nome": fonte.get("nome",""), "grupo": fonte.get("grupo","")})

        return artigos

    except Exception as e:

        logger.warning("Erro ao parsear feed de %s: %s", fonte.get("nome","?"), e)

        return []





def _extrair_links_sitemap(fonte, metadata):

    sitemap_url = metadata.get("url_sitemap","") or urljoin(fonte.get("url_home",""), "/sitemap.xml")

    resp = _fetch_with_retry(sitemap_url)

    if not resp:

        return []

    artigos = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    try:

        soup = BeautifulSoup(_decode_response(resp), "xml")

        for url_tag in soup.find_all("url"):

            loc = url_tag.find("loc")

            if not loc:

                continue

            url = loc.get_text(strip=True)

            lastmod = url_tag.find("lastmod")

            if lastmod:

                try:

                    lm = lastmod.get_text(strip=True)

                    dt = datetime.fromisoformat(lm.replace("Z","+00:00")) if "T" in lm else datetime.strptime(lm,"%Y-%m-%d").replace(tzinfo=timezone.utc)

                    if dt < cutoff:

                        continue

                except ValueError:

                    pass

            path = urlparse(url).path.lower()

            if any(p in path for p in ("/noticias/","/noticia/","/news/","/comunicacao/","/imprensa/")):

                artigos.append({"titulo":"", "url": url, "data": lastmod.get_text(strip=True) if lastmod else "", "imagem":"", "fonte_nome": fonte.get("nome",""), "grupo": fonte.get("grupo","")})

    except Exception as e:

        logger.warning("Erro ao parsear sitemap de %s: %s", fonte.get("nome","?"), e)

    return artigos[:20]




def coletar_links_fonte(fonte):

    nome = fonte.get("nome","desconhecido")

    url_noticias = fonte.get("url_noticias", fonte.get("url_home",""))

    domain = urlparse(url_noticias).netloc

    if _is_domain_blocked(domain):

        logger.info("Dominio %s bloqueado. Pulando %s.", domain, nome)

        return []

    if not _check_robots(url_noticias):

        logger.info("Bloqueado por robots.txt: %s", nome)

        return []

    estrategia, metadata = detector_estrategia.detectar_estrategia(fonte)

    logger.info("Fonte %s: estrategia %s", nome, estrategia)

    artigos = []

    if estrategia == "C":

        artigos = _extrair_links_api_json(fonte, metadata)

    elif estrategia == "D":

        artigos = _extrair_links_feed(fonte, metadata)

    elif estrategia == "E":

        artigos = _extrair_links_sitemap(fonte, metadata)

    else:

        resp = _fetch_with_retry(url_noticias)

        if not resp:

            logger.warning("Falha ao acessar %s (%s)", nome, url_noticias[:80])

            return []

        html = _decode_response(resp)

        artigos = _extrair_links_nextjs(fonte, html) if estrategia == "B" else _extrair_links_html(fonte, html)

    artigos = artigos[:MAX_ARTICLES_PER_SOURCE]

    logger.info("Fonte %s: %d links coletados", nome, len(artigos))

    return artigos





_KEYWORDS = ["governo","presidente","ministro","congresso","senado","camara","stf","economia","inflacao","pib","saude","educacao","tecnologia","meio ambiente","reforma","lei","decreto","eleicao","seguranca","investimento","mercado"]

_GRUPO_PESOS = {"governo":1.3,"reguladores":1.2,"legislativo":1.2,"judiciario":1.1,"nicho":1.0,"internacional":0.9}



def calcular_relevancia(artigo):

    score = 50.0

    titulo = artigo.get("titulo","").lower()

    grupo = artigo.get("grupo","")

    score *= _GRUPO_PESOS.get(grupo, 1.0)

    if grupo in ("governo","reguladores","legislativo","judiciario"):

        score += SCORE_GOV_BONUS

    score += min(sum(1 for kw in _KEYWORDS if kw in titulo) * 3, 15)

    if len(titulo) < 30:

        score *= 0.8

    peso = artigo.get("peso", 3)

    if peso >= 5: score *= 1.2

    elif peso >= 4: score *= 1.1

    elif peso <= 1: score *= 0.8

    return round(min(score, 100), 2)





def _normalizar_url(url):

    parsed = urlparse(url)

    host = parsed.netloc.lower().replace("www.","")

    path = parsed.path.rstrip("/")

    return f"{parsed.scheme}://{host}{path}"





def deduplicar_artigos(artigos):

    published_urls = db.get_published_urls_last_24h()

    published_normalized = {_normalizar_url(u) for u in published_urls}

    unique = []

    seen_urls = set()

    for artigo in artigos:

        url = artigo["url"]

        titulo = artigo.get("titulo","")

        url_norm = _normalizar_url(url)

        if url_norm in seen_urls or url_norm in published_normalized or url in published_urls:

            continue

        if titulo and db.post_exists(url, titulo):

            continue

        seen_urls.add(url_norm)

        unique.append(artigo)

    logger.info("Deduplicacao: %d artigos -> %d unicos", len(artigos), len(unique))

    return unique





def processar_artigo(artigo, categories):

    url = artigo["url"]

    titulo_original = artigo.get("titulo","")

    fonte_nome = artigo.get("fonte_nome","")

    logger.info("--- Processando: %s ---", titulo_original[:70])

    logger.info("Fonte: %s | URL: %s", fonte_nome, url[:80])

    conteudo_data = extrator_conteudo.extrair_conteudo_completo(url)

    if not conteudo_data:

        logger.warning("Conteudo insuficiente para: %s", titulo_original[:60])

        return False

    titulo = conteudo_data.get("titulo","") or titulo_original

    conteudo = conteudo_data.get("conteudo","")

    if len(conteudo.split()) < 150:

        logger.warning("Conteudo muito curto (%d palavras): %s", len(conteudo.split()), titulo[:60])

        return False

    article_data, llm_used = llm_router.generate_article(

        title=titulo, content=conteudo, source=fonte_nome, categories=categories, url=url

    )

    if not article_data:

        logger.warning("LLM falhou para: %s", titulo[:60])

        return False

    generated_content = article_data.get("conteudo","")

    if len(generated_content.split()) < config.MIN_CONTENT_WORDS:

        logger.warning("Conteudo gerado muito curto: %s", titulo[:60])

        return False

    html_bruto = extrator_conteudo.extrair_html_bruto(url)

    keywords = " ".join(article_data.get("tags",[])[:3])

    # Pipeline de imagem unificado — mesmo padrão para todas as raias
    sys.path.insert(0, str(Path("/home/bitnami")))
    from curador_imagens_unificado import is_official_source
    source_is_official = is_official_source(url)

    explicit_gov = ""
    explicit_commons = ""
    explicit_block_stock = None

    if source_is_official:
        logger.info("[IMAGEM] Fonte oficial (%s). Tier 1 puxará foto da matéria.", url[:60])
    else:
        # Verificar se o LLM principal foi PREMIUM
        _premium_models = ("gpt-4o", "sonnet", "claude", "2.5-pro", "grok-3")
        llm_is_premium = any(m in llm_used.lower() for m in _premium_models) if llm_used else False

        if llm_is_premium and article_data.get("imagem_busca_gov"):
            explicit_gov = article_data.get("imagem_busca_gov", "")
            explicit_commons = article_data.get("imagem_busca_commons", "")
            explicit_block_stock = article_data.get("block_stock_images")
            logger.info("[IMAGEM] LLM premium (%s) — confiando: gov='%s'", llm_used, explicit_gov)
        else:
            # LLM standard (Flash etc.) — SEMPRE chamar Editor Premium
            logger.info("[IMAGEM] LLM standard (%s). Chamando Editor Foto premium...", llm_used)
            photo_prompt = (
                f"Você é o Editor de Fotografia do portal Brasileira.News.\n"
                f"Para PESSOAS: busque nome + status jornalístico (preso, ministro, réu). Nunca detalhes de cena.\n"
                f"Para LOCAIS/EVENTOS sem pessoa: busque o nome do local.\n\n"
                f"Título: {article_data.get('titulo', titulo)}\n"
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
                    system_prompt="Você é um editor de fotografia jornalística. JSON válido apenas.",
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
        html_content=html_bruto,
        source_url=url,
        title=article_data.get("titulo", titulo),
        keywords=keywords,
        explicit_gov_query=explicit_gov,
        explicit_commons_query=explicit_commons,
        explicit_block_stock=explicit_block_stock
    )

    media_id = media_result[0] if isinstance(media_result, tuple) else media_result

    if not media_id:

        logger.warning("Sem imagem para: %s — publicando sem featured image", titulo[:60])

    post_id = wp_publisher.publish_post(

        title=article_data["titulo"],

        content=generated_content,

        excerpt=article_data.get("excerpt",""),

        category_name=article_data.get("categoria","Brasil"),

        tag_names=article_data.get("tags",[]),

        featured_media=media_id,

        seo_title=article_data.get("seo_title",""),

        seo_description=article_data.get("seo_description",""),

        push_notification=article_data.get("push_notification",""),

        prompt_imagem=article_data.get("prompt_imagem",""),

        legenda_imagem=article_data.get("legenda_imagem",""),

    )

    if not post_id:

        logger.error("Falha ao publicar: %s", titulo[:60])

        return False

    db.register_published(post_id, url, f"scraper:{fonte_nome}", llm_used)

    logger.info("PUBLICADO | post_id=%d | LLM=%s | %s", post_id, llm_used, article_data["titulo"][:60])

    return True




def run_cycle():

    cycle_start = time.time()

    logger.info("=" * 60)

    logger.info("INICIO DO CICLO RAIA 2 — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    logger.info("=" * 60)

    fontes = load_scrapers()

    if not fontes:

        logger.error("Nenhuma fonte disponivel. Abortando ciclo.")

        return

    all_artigos = []

    domain_last_request = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        futures = {}

        for fonte in fontes:

            if not _running:

                break

            domain = urlparse(fonte.get("url_noticias", fonte.get("url_home",""))).netloc

            last = domain_last_request.get(domain, 0)

            elapsed = time.time() - last

            if elapsed < DOMAIN_DELAY_MIN:

                time.sleep(DOMAIN_DELAY_MIN - elapsed)

            future = executor.submit(coletar_links_fonte, fonte)

            futures[future] = fonte

            domain_last_request[domain] = time.time()

        for future in as_completed(futures):

            fonte = futures[future]

            try:

                artigos = future.result()

                for a in artigos:

                    a["peso"] = fonte.get("peso", 3)

                all_artigos.extend(artigos)

            except Exception as e:

                logger.error("Erro ao coletar %s: %s", fonte.get("nome","?"), e, exc_info=True)

    logger.info("Total de artigos coletados: %d", len(all_artigos))

    if not all_artigos:

        logger.info("Nenhum artigo encontrado. Ciclo encerrado.")

        return

    unique_artigos = deduplicar_artigos(all_artigos)

    if not unique_artigos:

        logger.info("Todos os artigos ja foram publicados. Ciclo encerrado.")

        return

    for artigo in unique_artigos:

        artigo["score"] = calcular_relevancia(artigo)

    artigos_relevantes = [a for a in unique_artigos if a["score"] >= SCORE_MIN]

    logger.info("Apos filtro (>=%d): %d artigos", SCORE_MIN, len(artigos_relevantes))

    if not artigos_relevantes:

        logger.info("Nenhum artigo com relevancia suficiente. Ciclo encerrado.")

        return

    artigos_relevantes.sort(key=lambda x: x["score"], reverse=True)

    selected = artigos_relevantes[:MAX_ARTICLES_PER_CYCLE]

    logger.info("Selecionados %d artigos (de %d disponiveis)", len(selected), len(artigos_relevantes))

    published_count = 0

    failed_count = 0

    for i, artigo in enumerate(selected, 1):

        if not _running:

            logger.info("Parada solicitada. Encerrando processamento.")

            break

        logger.info("--- Artigo %d/%d (score=%.2f) ---", i, len(selected), artigo["score"])

        try:

            domain = urlparse(artigo["url"]).netloc

            last = domain_last_request.get(domain, 0)

            if time.time() - last < DOMAIN_DELAY_MIN:

                time.sleep(DOMAIN_DELAY_MIN + 1.5)

            domain_last_request[domain] = time.time()

            success = processar_artigo(artigo, config.VALID_CATEGORIES)

            if success: published_count += 1

            else: failed_count += 1

        except Exception as e:

            logger.error("Erro inesperado: %s", e, exc_info=True)

            failed_count += 1

        if i < len(selected):

            time.sleep(config.WP_POST_DELAY)

    elapsed = time.time() - cycle_start

    logger.info("=" * 60)

    logger.info("FIM DO CICLO RAIA 2 — Publicados: %d | Falhas: %d | Tempo: %.0fs", published_count, failed_count, elapsed)

    logger.info("=" * 60)





LOCK_FILE = Path(__file__).resolve().parent / "motor_scrapers_v2.lock"
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
        logger.warning("Outra instância do Motor Scrapers v2 já está em execução. Saindo.")
        sys.exit(0)

    logger.info("Motor Scrapers v2 (Raia 2) — brasileira.news — Iniciando...")

    logger.info("Fontes: %s", SCRAPERS_FILE)

    logger.info("Max artigos/fonte: %d | Max artigos/ciclo: %d", MAX_ARTICLES_PER_SOURCE, MAX_ARTICLES_PER_CYCLE)

    try:

        db.ensure_control_table()

    except Exception as e:

        logger.error("Erro ao verificar tabela de controle: %s", e)

    try:

        run_cycle()

    except Exception as e:

        logger.error("Erro fatal no ciclo: %s", e, exc_info=True)

    release_lock()
    logger.info("Motor Scrapers v2 encerrado.")





if __name__ == "__main__":

    main()

