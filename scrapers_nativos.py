
# -*- coding: utf-8 -*-

"""

MECANISMO DE SCRAPERS NATIVOS E MOLDES UNIVERSAIS - Brasileira.news

"""

import asyncio

import httpx

import re

import json

from bs4 import BeautifulSoup

from urllib.parse import urljoin

import nest_asyncio







HEADERS = {

    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",

    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

}



async def fetch(client: httpx.AsyncClient, url: str) -> str:
    for attempt in range(3):
        try:
            r = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
            if r.status_code in [200, 202]: 
                return r.text
        except Exception:
            if attempt == 2: return ""
            await asyncio.sleep(1)
    return ""



async def scrape_inteligente(client, nome, url_alvo):

    arts = []

    if not url_alvo: return arts

    html = await fetch(client, url_alvo)

    if not html: return arts

    soup = BeautifulSoup(html, "lxml")

    

    seletores = [

        "article a", ".noticia a", ".post a", ".news a", ".item a", 

        ".feed-post-link", ".post-title a", ".entry-title a", ".headline a",

        "h1 a", "h2 a", "h3 a", ".card a", ".chamada a", "a.title"

    ]

    

    vistos = set()

    for seletor in seletores:

        for a in soup.select(seletor):

            t = a.get_text(strip=True)

            h = a.get("href", "")

            if len(t) > 25 and h and not h.startswith("#") and not h.endswith((".jpg", ".pdf")):

                link_completo = urljoin(url_alvo, h)

                bloqueios = ["/autor/", "/tag/", "/category/", "/secao/", "/login", "whatsapp", "facebook", "twitter"]

                if not any(x in link_completo.lower() for x in bloqueios):

                    if link_completo not in vistos:

                        vistos.add(link_completo)

                        arts.append({"titulo": t, "link": link_completo, "veiculo": nome})

    return arts



async def scrape_plone_classico(client, nome, url_alvo):

    arts = []

    html = await fetch(client, url_alvo)

    if not html: return arts

    soup = BeautifulSoup(html, "lxml")

    for item in soup.select("div.conteudo"):

        titulo_tag = item.select_one("h2.titulo a")

        if titulo_tag:

            t = titulo_tag.get_text(strip=True)

            h = titulo_tag.get("href", "")

            if len(t) > 15 and h:

                # Resolve links relativos (Corrige o erro do MCTI e Comunicacoes)

                link_completo = urljoin(url_alvo, h)

                arts.append({"titulo": t, "link": link_completo, "veiculo": nome})

    

    # Plano B: Se o Governo mudou o site, aciona o inteligente automaticamente

    if not arts:

        return await scrape_inteligente(client, nome, url_alvo)

    return arts



async def scrape_plone_tiles(client, nome, url_alvo):

    arts = []

    html = await fetch(client, url_alvo)

    if not html: return arts

    soup = BeautifulSoup(html, "lxml")

    for item in soup.select("article"):

        titulo_tag = item.select_one("h2.tileHeadline a")

        if titulo_tag:

            t = titulo_tag.get_text(strip=True)

            h = titulo_tag.get("href", "")

            if len(t) > 15 and h:

                link_completo = urljoin(url_alvo, h)

                arts.append({"titulo": t, "link": link_completo, "veiculo": nome})

                

    if not arts:

        return await scrape_inteligente(client, nome, url_alvo)

    return arts



async def scrape_r7(client, nome, url_alvo=None):

    arts = []

    html = await fetch(client, "https://noticias.r7.com/")

    if not html: return arts

    for a in BeautifulSoup(html, "lxml").select("a[href*='/noticias/']"):

        t = a.get_text(strip=True); h = a.get("href", "")

        if len(t) > 20 and h.startswith("http") and "/prisma/" not in h: arts.append({"titulo": t, "link": h, "veiculo": nome})

    return arts



async def scrape_omelete(client, nome, url_alvo=None):

    arts = []

    text = await fetch(client, "https://www.omelete.com.br/api/")

    if not text: return arts

    try:

        for item in json.loads(text):

            t = item.get("title", ""); s = item.get("slug", ""); c = item.get("content_type", "")

            if t and s: arts.append({"titulo": t, "link": f"https://www.omelete.com.br/{c}/{s}", "veiculo": nome})

    except: pass

    return arts



async def scrape_tecmundo(client, nome, url_alvo=None):

    arts = []

    html = await fetch(client, "https://www.tecmundo.com.br/")

    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)

    if match:

        try:

            props = json.loads(match.group(1)).get("props", {}).get("pageProps", {})

            for key in ["latestArticles", "highlights", "mostRead"]:

                for item in props.get(key, []):

                    t = item.get("title", ""); s = item.get("slug", "")

                    if t and s: arts.append({"titulo": t, "link": f"https://www.tecmundo.com.br/{s}", "veiculo": nome})

        except: pass

    return arts



MOLDES_DISPONIVEIS = {

    "inteligente": scrape_inteligente,

    "plone_classico": scrape_plone_classico,

    "plone_tiles": scrape_plone_tiles,

    "r7": scrape_r7,

    "omelete": scrape_omelete,

    "tecmundo": scrape_tecmundo

}



def coletar_links_scraper(tipo_molde: str, nome_veiculo: str, url_alvo: str):

    if tipo_molde not in MOLDES_DISPONIVEIS:

        return []

    async def _run():

        async with httpx.AsyncClient() as client:

            func = MOLDES_DISPONIVEIS[tipo_molde]

            resultados = await func(client, nome_veiculo, url_alvo)

            vistos = set()

            unicos = []

            for r in resultados:

                if r['link'] not in vistos:

                    vistos.add(r['link'])

                    unicos.append(r)

            return unicos

    try:
        nest_asyncio.apply()
        if sys.version_info >= (3, 10):
            return asyncio.run(_run())
        else:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_run())
    except Exception as e:
        print(f"[ERRO SCRAPER] Falha ao rodar {tipo_molde} em {url_alvo}: {e}")
        return []

