
# -*- coding: utf-8 -*-

"""

GESTOR WORDPRESS - Brasileira.news

Lida com categorias em formato de lista (Macro + Subcategoria).

"""

import requests

from datetime import datetime

from config_geral import WP_URL, AUTH_HEADERS

from config_categorias import ID_REDACAO

import sys
from pathlib import Path
sys.path.insert(0, "/home/bitnami")
from curador_imagens_unificado import get_curador



def resolver_autor_estrito(veiculo, url_original):

    veiculo_lower = veiculo.lower()

    url_lower = url_original.lower() if url_original else ""

    

    marcadores_gov = [

        'gov.br', 'jus.br', 'leg.br', 'def.br', 'mp.br', 

        'agencia brasil', 'radioagencia', 'senado', 'camara'

    ]

    

    is_oficial = any(m in url_lower or m in veiculo_lower for m in marcadores_gov)

    if not is_oficial:

        return ID_REDACAO

        

    try:

        termo = "agenciabrasil" if "brasil" in veiculo_lower else veiculo.split()[0]

        if "Min." in veiculo: termo = veiculo.split()[-1]

        

        res_busca = requests.get(f"{WP_URL}/users?search={termo}&context=edit", headers=AUTH_HEADERS)

        if res_busca.status_code == 200 and len(res_busca.json()) > 0:

            return res_busca.json()[0]['id']

    except:

        pass

        

    return ID_REDACAO



def publicar_no_wordpress(dados, autor_id, cat_id, veiculo):

    print(f"[PUBLICADOR] Preparando submissao: '{dados.get('h1_title', 'Sem Titulo')}'...")

    

    url_orig = dados.get('_link_original', '')

    autor_final = resolver_autor_estrito(veiculo, url_orig)

    is_oficial = autor_final != ID_REDACAO

    

    comando_ia = dados.get('prompt_imagem', '').strip()

    

    if 'h1_title' in dados:
        keywords = " ".join(dados.get('tags', [])[:3]) if dados.get('tags') else dados.get('h1_title', '')
        # Tenta pegar a imagem com o unificado
        curador = get_curador()
        img_id, _ = curador.get_featured_image(
            html_content=dados.get('corpo_html', ''),
            source_url=url_orig,
            title=dados.get('h1_title', 'Noticias'),
            keywords=keywords
        )
        
        # Fallback local da IA se o curador unificado não encontrou imagem
        if not img_id:
            img_bytes = None
            if not comando_ia or "USE_ORIGINAL_IMAGE" in comando_ia.upper():
                titulo_base = dados.get('h1_title', 'Noticias')
                comando_ia = f"Imagem editorial, fotorrealista e de alta qualidade representando: '{titulo_base}'. Sem letras."
            
            from roteador_ia import roteador_ia_imagem
            img_bytes = roteador_ia_imagem(comando_ia)

            if img_bytes:
                res_img = requests.post(f"{WP_URL}/media", headers={**AUTH_HEADERS, 'Content-Disposition': 'attachment; filename="capa.jpg"', 'Content-Type': 'image/jpeg'}, data=img_bytes)
                if res_img.status_code == 201: img_id = res_img.json().get('id')
    else:
        img_id = None



    tag_ids = []

    for tag in dados.get('tags', []):

        if len(tag) < 3: continue 

        res_t = requests.post(f"{WP_URL}/tags", headers=AUTH_HEADERS, json={'name': tag})

        if res_t.status_code == 201: tag_ids.append(res_t.json().get('id'))

        elif res_t.status_code == 400:

            busca = requests.get(f"{WP_URL}/tags?search={tag}", headers=AUTH_HEADERS)

            if busca.status_code == 200 and len(busca.json()) > 0: tag_ids.append(busca.json()[0].get('id'))



    corpo_final = dados.get('corpo_html', '')

    

    if url_orig:

        corpo_final += f"\n<!-- URL_ORIGINAL: {url_orig} -->\n<!-- VEICULO: {veiculo} -->"



    if dados.get('push_notification'): corpo_final += f"\n<!-- PUSH: {dados.get('push_notification')} -->"



    # LOGICA DE MULTIPLAS CATEGORIAS

    if isinstance(cat_id, list):

        cat_ids = [int(c) for c in cat_id]

    else:

        try: cat_ids = [int(cat_id)]

        except: cat_ids = [1] 



    payload = {

        'title': dados.get('h1_title'),

        'content': corpo_final,

        'excerpt': dados.get('meta_description', ''),

        'status': 'publish', 

        'date_gmt': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),

        'categories': cat_ids, 

        'tags': tag_ids,

        'author': autor_final

    }

    if img_id: payload['featured_media'] = img_id

        

    res = requests.post(f"{WP_URL}/posts", json=payload, headers=AUTH_HEADERS)

    if res.status_code == 201:
        post_id = res.json().get('id')
        print(f"[OK] Reportagem publicada com sucesso! ID: {post_id}\n")
        return post_id
    else:
        print(f"[ERRO WP] {res.text}\n")
        return None




# --- Funcao injetada automaticamente para o Motor Mestre ---

def obter_autor_id_exato(nome_fonte):

    try:

        from config_categorias import ID_REDACAO, MAPA_AUTORES

        mapa = MAPA_AUTORES

    except ImportError:

        try:

            from config_categorias import ID_REDACAO, MAPA_UNIFICADO_AUTORES

            mapa = MAPA_UNIFICADO_AUTORES

        except ImportError:

            return 2 # Fallback de seguranca

            

    if not nome_fonte: return ID_REDACAO

    

    nome_l = str(nome_fonte).lower()

    for chave, id_autor in mapa.items():

        if chave in nome_l:

            return id_autor

            

    return ID_REDACAO

