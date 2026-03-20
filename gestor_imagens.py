# -*- coding: utf-8 -*-

import requests

from bs4 import BeautifulSoup

import re

from urllib.parse import urljoin



def raspar_imagem_original(url_noticia):

    if not url_noticia: return None

        

    print(f"[ARTE] Procurando fotografia em: {url_noticia}")

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    

    try:

        resposta = requests.get(url_noticia, headers=headers, timeout=15)

        if resposta.status_code == 200:

            sopa = BeautifulSoup(resposta.content, 'html.parser')

            

            # TENTATIVA 1: Metatag universal

            meta_img = sopa.find("meta", property="og:image") or sopa.find("meta", attrs={"name": "twitter:image"})

            if meta_img and meta_img.get("content"):

                link_img = urljoin(url_noticia, meta_img["content"])

                if not re.search(r'(logo|icon|avatar|favicon)', link_img, re.IGNORECASE):

                    img_resp = requests.get(link_img, headers=headers, timeout=10)

                    if img_resp.status_code == 200 and len(img_resp.content) > 10000:

                        print("[ARTE] Foto capturada via Metatag!")

                        return img_resp.content

            

            # TENTATIVA 2: Busca profunda focada no Governo

            print("[ARTE] Metatag falhou. Vasculhando corpo do texto...")

            

            # USO DOS PARENTESES PARA EVITAR ERRO DE SINTAXE NAS QUEBRAS DE LINHA

            article = (

                sopa.find('div', property='rnews:articleBody') or

                sopa.find('div', itemprop='articleBody') or

                sopa.find('div', id='parent-fieldname-text') or

                sopa.find('div', class_=re.compile(r'(item-page|conteudo|document-body)')) or

                sopa.find('article') or 

                sopa.find('main') or 

                sopa

            )

                      

            for img in article.find_all('img'):

                src = img.get('src') or img.get('data-src')

                if src and not src.startswith('data:image'):

                    src = urljoin(url_noticia, src)

                    if not re.search(r'(logo|icon|avatar|favicon|spinner|banner)', src, re.IGNORECASE):

                        img_resp = requests.get(src, headers=headers, timeout=10)

                        if img_resp.status_code == 200 and len(img_resp.content) > 15000:

                            print("[ARTE] Foto real encontrada no corpo do texto!")

                            return img_resp.content

                            

    except Exception as e:

        print(f"[ARTE AVISO] Falha no scraping da imagem: {e}")

        

    print("[ARTE] Nenhuma foto valida encontrada.")

    return None
