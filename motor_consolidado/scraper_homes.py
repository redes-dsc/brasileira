"""
Scraper de títulos das homepages e seções de últimas notícias.
Raspa TIER 1, TIER 2 e Mais Lidas dos principais portais brasileiros.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config_consolidado import (
    TIER1_PORTALS, TIER2_PORTALS, MAIS_LIDAS_PORTALS,
)

logger = logging.getLogger("motor_consolidado")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "DNT": "1",
}

_TIMEOUT = 20
_MIN_TITLE_LEN = 15  # ignora títulos curtos demais


def _fetch_page(url: str) -> str:
    """Faz download da página com tratamento de encoding."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except requests.RequestException as e:
        logger.warning("Erro ao buscar %s: %s", url[:80], e)
        return ""


def _clean_title(title: str) -> str:
    """Limpa e normaliza texto de título."""
    title = re.sub(r"\s+", " ", title).strip()
    # Remover prefixos de coluna/editoria
    title = re.sub(r"^(AO VIVO|URGENTE|EXCLUSIVO|VÍDEO|PODCAST)\s*[:\-–|]\s*", "", title, flags=re.IGNORECASE)
    return title


def _extract_titles_with_selectors(soup: BeautifulSoup, selectors: list[str], base_url: str) -> list[dict]:
    """Extrai títulos usando lista de seletores CSS, retorna ao primeiro sucesso."""
    results = []
    seen_urls = set()

    for selector in selectors:
        elements = soup.select(selector)
        if not elements:
            continue

        for el in elements:
            # Se o seletor já termina em 'a', el é o próprio link
            if el.name == "a":
                link_el = el
            else:
                link_el = el.find("a")

            if link_el:
                href = link_el.get("href", "")
                title = link_el.get_text(strip=True)
            else:
                title = el.get_text(strip=True)
                href = ""

            title = _clean_title(title)
            if not title or len(title) < _MIN_TITLE_LEN:
                continue

            # Resolver URL relativa
            if href and not href.startswith("http"):
                href = urljoin(base_url, href)

            # Deduplicar por URL
            if href and href in seen_urls:
                continue
            if href:
                seen_urls.add(href)

            results.append({"title": title, "url": href})

        # Se encontrou resultados com este seletor, não precisa tentar os demais
        if results:
            break

    return results


def _fallback_generic_extraction(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extração genérica usando h1/h2/h3 com links — último recurso."""
    results = []
    seen_urls = set()

    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        link = tag.find("a") or tag.find_parent("a")
        if not link:
            continue
        href = link.get("href", "")
        
        # Prefere o texto do wrapper heading (ex: <h2><a>texto</a></h2> ou <a><h2>texto</h2></a>)
        title = _clean_title(tag.get_text(strip=True))
        if not title or len(title) < _MIN_TITLE_LEN:
            title = _clean_title(link.get_text(strip=True))
            if not title or len(title) < _MIN_TITLE_LEN:
                continue
                
        if href and not href.startswith("http"):
            from urllib.parse import urljoin
            href = urljoin(base_url, href)
        if href and href in seen_urls:
            continue
        if href:
            seen_urls.add(href)
        results.append({"title": title, "url": href})

    return results


def scrape_portal_titles(portal: dict, section: str = "ultimas") -> list[dict]:
    """
    Raspa títulos de um portal específico.
    Retorna lista de {title, url, portal_name, section, is_manchete}.
    """
    # Força a leitura da Capa (home_url) como prioridade 1 para capturar a edição principal
    url = portal.get("home_url") or portal.get("url") or portal.get("ultimas_url")
    rss_url = portal.get("rss_url")
    selectors = portal.get("selectors", [])
    portal_name = portal["name"]

    raw_titles = []
    
    # Tentativa via RSS feed (preferencial se configurado)
    if rss_url:
        try:
            import feedparser
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                if hasattr(entry, "title") and hasattr(entry, "link"):
                    title = _clean_title(entry.title)
                    if title and len(title) >= _MIN_TITLE_LEN:
                        raw_titles.append({"title": title, "url": entry.link})
            if raw_titles:
                logger.info("RSS extraído para %s: %d títulos", portal_name, len(raw_titles))
        except Exception as e:
            logger.warning("Falha ao ler RSS de %s: %s", portal_name, e)

    # Fallback para HTML scraping
    if not raw_titles:
        html = _fetch_page(url)
        if not html:
            logger.warning("Página vazia para %s (%s)", portal_name, url[:80])
            return []
    
        soup = BeautifulSoup(html, "html.parser")
    
        # Tentar seletores específicos
        raw_titles = _extract_titles_with_selectors(soup, selectors, url)
    
        # Fallback genérico
        if not raw_titles:
            raw_titles = _fallback_generic_extraction(soup, url)
            if raw_titles:
                logger.info("Fallback genérico para %s: %d títulos", portal_name, len(raw_titles))
    # Enriquecer com metadata
    results = []
    
    # O CLUSTERING DEVE FOCAR SÓ NO FILÉ MIGNON: LIMITAR AOS TOP 18 DESTAQUES DA CAPA
    raw_titles = raw_titles[:18]
    
    for i, item in enumerate(raw_titles):
        results.append({
            "title": item["title"],
            "url": item["url"],
            "portal_name": portal_name,
            "section": portal.get("section", section),
            "is_manchete": i < 3,  # primeiros 3 = manchetes
            "is_mais_lida": portal.get("section") == "mais_lidas",
        })

    logger.info("[%s] %d títulos raspados (%s)", portal_name, len(results), section)
    return results


def scrape_all_portals(cycle_number: int = 1) -> list[dict]:
    """
    Raspa títulos de todos os portais conforme o tier e ciclo.
    TIER 1 + MAIS_LIDAS: todo ciclo
    TIER 2: ciclos pares
    """
    all_titles = []

    # TIER 1 — sempre
    for portal in TIER1_PORTALS:
        titles = scrape_portal_titles(portal, section="tier1")
        all_titles.extend(titles)

    # MAIS LIDAS — sempre
    for portal in MAIS_LIDAS_PORTALS:
        titles = scrape_portal_titles(portal, section="mais_lidas")
        all_titles.extend(titles)

    # TIER 2 — ciclos pares
    if cycle_number % 2 == 0:
        for portal in TIER2_PORTALS:
            titles = scrape_portal_titles(portal, section="tier2")
            all_titles.extend(titles)
        logger.info("TIER 2 incluído (ciclo %d)", cycle_number)

    logger.info("Total de títulos raspados: %d", len(all_titles))
    return all_titles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    titles = scrape_all_portals(cycle_number=1)
    print(f"\nTotal: {len(titles)} títulos raspados\n")
    for t in titles[:20]:
        print(f"  [{t['portal_name']}] {t['title'][:70]}")
