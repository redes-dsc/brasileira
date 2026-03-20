
# -*- coding: utf-8 -*-

import requests, os, time

from config_geral import WP_URL, AUTH_HEADERS

URL_DEFAULT = "https://brasileira.news/wp-content/uploads/sites/7/2026/02/imagem-brasileira.png"

def obter_id():

    res = requests.get(f"{WP_URL}/media?search=imagem-brasileira", headers=AUTH_HEADERS)

    if res.status_code == 200 and len(res.json())>0: return res.json()[0]['id']

    upd = requests.post(f"{WP_URL}/media", headers={**AUTH_HEADERS, 'Content-Disposition': 'attachment; filename="imagem-default.png"', 'Content-Type': 'image/png'}, data=requests.get(URL_DEFAULT).content)

    return upd.json()['id']

def eh_ia(m_id):

    res = requests.get(f"{WP_URL}/media/{m_id}", headers=AUTH_HEADERS)

    if res.status_code != 200: return False

    m = res.json()

    t = (str(m.get('title',{}).get('rendered','')) + str(m.get('caption',{}).get('rendered','')) + str(m.get('alt_text','')) + str(m.get('source_url',''))).lower()

    return any(g in t for g in ["inteligência artificial", "inteligencia artificial", "dall-e", "editorial news photography", "no text"])

id_def = obter_id()

pag = 1; cor = 0

while True:

    posts = requests.get(f"{WP_URL}/posts?per_page=50&page={pag}", headers=AUTH_HEADERS).json()

    if not posts or type(posts) is dict: break

    for p in posts:

        m_id = p.get('featured_media', 0)

        if m_id != 0 and m_id != id_def and eh_ia(m_id):

            print(f"Trocando IA: {p['title']['rendered'][:40]}...")

            if requests.post(f"{WP_URL}/posts/{p['id']}", json={"featured_media": id_def}, headers=AUTH_HEADERS).status_code == 200: cor+=1

    pag += 1

print(f"Feito! {cor} capas substituidas.")

