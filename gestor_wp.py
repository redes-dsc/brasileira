
# -*- coding: utf-8 -*-

"""

GESTOR WORDPRESS - Brasileira.news

Lida com categorias em formato de lista (Macro + Subcategoria).

"""

import requests
import time
import logging
import os
from datetime import datetime, timezone

from config_geral import WP_URL, AUTH_HEADERS

from config_categorias import ID_REDACAO

import sys
from pathlib import Path
sys.path.insert(0, "/home/bitnami")
from curador_imagens_unificado import get_curador

# Configure logger for this module
logger = logging.getLogger(__name__)


def _validate_wp_credentials():
    """Validate that WordPress credentials are configured."""
    wp_user = os.environ.get('WP_USER')
    wp_app_pass = os.environ.get('WP_APP_PASS')
    if not wp_user or not wp_app_pass:
        logger.warning("WP_USER or WP_APP_PASS environment variables not set. API calls may fail.")
        return False
    return True


def _handle_http_error(response, context="API call"):
    """Handle HTTP error responses with proper logging."""
    if response.status_code == 401:
        logger.error(f"{context} failed: 401 Unauthorized - Check WP_USER and WP_APP_PASS credentials")
        return None
    elif response.status_code == 403:
        logger.error(f"{context} failed: 403 Forbidden - User lacks permission for this action")
        return None
    return response



_AUTOR_CACHE = {}

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
        
        if termo in _AUTOR_CACHE:
            return _AUTOR_CACHE[termo]
        
        res_busca = requests.get(f"{WP_URL}/users?search={termo}", headers=AUTH_HEADERS)

        if res_busca.status_code in [401, 403]:
            _handle_http_error(res_busca, f"User search for '{termo}'")
            return ID_REDACAO
        
        if res_busca.status_code == 200:
            try:
                users = res_busca.json()
                if len(users) > 0:
                    user_id = users[0]['id']
                    _AUTOR_CACHE[termo] = user_id
                    return user_id
            except (ValueError, KeyError) as e:
                logger.error(f"Error parsing user search response for '{termo}': {e}")

    except requests.RequestException as e:
        logger.error(f"HTTP request failed during author resolution for '{termo}': {e}")

        

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
        # Curador unificado é a única fonte de imagem — IA generativa desativada
        # Geração de imagens IA desativada — usa curador_imagens_unificado.py
    else:
        img_id = None

    tag_ids = []
    _tag_cache_local = {}  # Cache local para evitar requests duplicados

    for tag in dados.get('tags', []):
        if len(tag) < 2: continue  # Permitir 'IA', '5G', 'TV' (fix bug 7.5)
        
        if tag in _tag_cache_local:
            tag_ids.append(_tag_cache_local[tag])
            continue
        
        try:
            res_t = requests.post(f"{WP_URL}/tags", headers=AUTH_HEADERS, json={'name': tag})
            if res_t.status_code == 201:
                try:
                    tid = res_t.json().get('id')
                    tag_ids.append(tid)
                    _tag_cache_local[tag] = tid
                except (ValueError, KeyError) as e:
                    logger.error(f"Error parsing tag creation response for '{tag}': {e}")
            elif res_t.status_code in [401, 403]:
                _handle_http_error(res_t, f"Tag creation for '{tag}'")
            elif res_t.status_code == 400:
                try:
                    busca = requests.get(f"{WP_URL}/tags?search={tag}", headers=AUTH_HEADERS)
                    if busca.status_code in [401, 403]:
                        _handle_http_error(busca, f"Tag search for '{tag}'")
                    elif busca.status_code == 200:
                        tags_found = busca.json()
                        if len(tags_found) > 0:
                            tid = tags_found[0].get('id')
                            tag_ids.append(tid)
                            _tag_cache_local[tag] = tid
                except (ValueError, KeyError) as e:
                    logger.error(f"Error parsing tag search response for '{tag}': {e}")
                except requests.RequestException as e:
                    logger.error(f"HTTP request failed during tag search for '{tag}': {e}")
        except requests.RequestException as e:
            logger.error(f"HTTP request failed during tag creation for '{tag}': {e}")



    corpo_final = dados.get('corpo_html', '')

    

    if url_orig:

        corpo_final += f"\n<!-- URL_ORIGINAL: {url_orig} -->\n<!-- VEICULO: {veiculo} -->"



    if dados.get('push_notification'): corpo_final += f"\n<!-- PUSH: {dados.get('push_notification')} -->"



    # LOGICA DE MULTIPLAS CATEGORIAS

    if isinstance(cat_id, list):
        cat_ids = [int(c) for c in cat_id if str(c).isdigit()]
    else:
        try:
            cat_ids = [int(cat_id)]
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid category ID '{cat_id}', defaulting to empty list: {e}")
            cat_ids = []



    payload = {

        'title': dados.get('h1_title'),

        'content': corpo_final,

        'excerpt': dados.get('meta_description', ''),

        'status': 'publish', 

        'date_gmt': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),

        'categories': cat_ids, 

        'tags': tag_ids,

        'author': autor_final

    }

    if img_id: payload['featured_media'] = img_id

        

    _validate_wp_credentials()
    
    for attempt in range(3):
        try:
            res = requests.post(f"{WP_URL}/posts", json=payload, headers=AUTH_HEADERS)
            if res.status_code == 201:
                try:
                    post_id = res.json().get('id')
                    print(f"[OK] Reportagem publicada com sucesso! ID: {post_id}\\n")
                    return post_id
                except (ValueError, KeyError) as e:
                    logger.error(f"Error parsing post creation response: {e}")
                    return None
            elif res.status_code == 401:
                logger.error("Post creation failed: 401 Unauthorized - Check WP_USER and WP_APP_PASS credentials")
                print("[ERRO WP] 401 Unauthorized - Credenciais invalidas\\n")
                return None
            elif res.status_code == 403:
                logger.error("Post creation failed: 403 Forbidden - User lacks permission to create posts")
                print("[ERRO WP] 403 Forbidden - Sem permissao\\n")
                return None
            elif res.status_code in [429, 502, 503]:
                print(f"[RETRY] Servidor WP indisponivel ({res.status_code}), aguardando 5s...")
                time.sleep(5)
                continue
            else:
                logger.error(f"Post creation failed with status {res.status_code}: {res.text}")
                print(f"[ERRO WP] {res.text}\\n")
                return None
        except requests.RequestException as e:
            logger.error(f"HTTP request failed during post creation (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(5)
                continue
            return None
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

