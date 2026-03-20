
# -*- coding: utf-8 -*-

"""

EXTRATOR DE CONTEÚDO PROFUNDO - Brasileira.news

Raspa o texto original das páginas ignorando lixo, anúncios e bloqueios.

"""

import requests

import re

from bs4 import BeautifulSoup



def extrair_texto_completo(url):

    """Extrai o corpo da notícia e aplica o Filtro Anti-CVV e Anti-Lixo."""

    try:

        headers = {

            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',

            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'

        }

        res = requests.get(url, headers=headers, timeout=20)

        soup = BeautifulSoup(res.content, 'html.parser')

        

        for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'form', 'iframe', 'figure']): 

            tag.decompose()

        

        article = (

            soup.find(attrs={"property": "rnews:articleBody"}) or

            soup.find(attrs={"itemprop": "articleBody"}) or

            soup.find('div', id='content-core') or

            soup.find('div', id='parent-fieldname-text') or

            soup.find('div', class_=re.compile(r'(item-page|conteudo-materia|post-content|texto-materia|article-content)', re.I)) or

            soup.find('article') or 

            soup.find('main') or 

            soup

        )

                  

        paragrafos = article.find_all(['p', 'h2', 'h3', 'blockquote'])

        

        textos_limpos = []

        for p in paragrafos:

            texto_p = p.get_text().strip()

            if len(texto_p) > 20 and "Centro de Valorização da Vida" not in texto_p and "telefone 188" not in texto_p:

                textos_limpos.append(texto_p)

                

        texto = "\n\n".join(textos_limpos)

        return texto[:25000] 

    except Exception as e:

        print(f"[EXTRACAO AVISO] Falha ao extrair texto de {url}: {e}")

        return ""

