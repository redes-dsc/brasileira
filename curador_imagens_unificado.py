#!/usr/bin/env python3
"""
Curador de Imagens Unificado - Brasileira.news

Responsável por obter a melhor imagem possível para cada matéria, seguindo
uma hierarquia (TIERS) rigorosa para garantir direitos autorais e qualidade.

TIER 1: Raspagem direta do HTML da fonte oficial (og:image / img).
TIER 2: Bancos de imagens governamentais via HTML (Agência Brasil, etc).
TIER 3A: Flickr (contas governamentais).
TIER 3B: Wikimedia Commons.
TIER 3C: Google Custom Search API (buscando apenas em sites .gov.br ou configurados).
TIER 4: Stock APIs gratuitas (Unsplash, Pexels, Pixabay, Freepik).
TIER 5: Imagem placeholder padrão (brasileira.news genérica).
"""

import logging
import os
import re
import struct
import json
import random
import time
from urllib.parse import urlparse, quote_plus, urljoin
from typing import Optional, Tuple
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Carregar .env do diretório raiz
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path, override=True)

# Configurações do projeto
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "motor_rss"))
import config

logger = logging.getLogger("curador_imagens")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Configurações de API (Carregadas do ambiente ou config)
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", getattr(config, "UNSPLASH_ACCESS_KEY", ""))
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
FREEPIK_API_KEY = os.getenv("FREEPIK_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
GOOGLE_API_KEY_CSE = os.getenv("GOOGLE_API_KEY_CSE", "")
FLICKR_API_KEY = os.getenv("FLICKR_API_KEY", "")

# Domínios Oficiais (Tier 1 & 2)
OFFICIAL_DOMAINS = ["gov.br", "leg.br", "jus.br", "mp.br", "def.br", "ebc.com.br", "agenciabrasil.ebc.com.br"]

# Placeholder fallback (Tier 5)
PLACEHOLDER_IMAGE_URL = os.getenv("PLACEHOLDER_IMAGE_URL", "https://brasileira.news/wp-content/uploads/2023/10/placeholder-brasileiranews.jpg")

# =====================================================================
# FUNÇÕES UTILITÁRIAS
# =====================================================================

def is_official_source(url: str) -> bool:
    """Verifica se a URL pertence a um domínio oficial governamental."""
    if not url: return False
    domain = urlparse(url).netloc.lower()
    return any(domain.endswith("." + d) or domain == d for d in OFFICIAL_DOMAINS)

def _get_image_dimensions_from_headers(url: str) -> tuple[int, int] | None:
    try:
        resp = requests.get(url, headers={"Range": "bytes=0-1024"}, timeout=config.HTTP_TIMEOUT, stream=True)
        data = resp.content
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            return struct.unpack(">I", data[16:20])[0], struct.unpack(">I", data[20:24])[0]
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 8:
                if data[i] != 0xFF: break
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    return struct.unpack(">H", data[i + 7 : i + 9])[0], struct.unpack(">H", data[i + 5 : i + 7])[0]
                length = struct.unpack(">H", data[i + 2 : i + 4])[0]
                i += 2 + length
    except Exception:
        pass
    return None

def is_valid_image_url(url: str) -> bool:
    """Valida se URL é de imagem adequada para notícia (não genérica/tema)."""
    if not url: return False
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    url_lower = url.lower()
    
    # Verificar extensão
    ext = path_lower.rsplit(".", 1)[-1] if "." in path_lower else ""
    if ext not in ("jpg", "jpeg", "png", "webp"): return False
    
    # Padrões a ignorar (logos, ícones, imagens de tema genéricas)
    skip_patterns = [
        "logo", "icon", "favicon", "avatar", "emoji", "1x1", "pixel",
        "transparencia", "compartilhamento", "/theme", "/themes/",
        "/assets/images/", "placeholder", "default-image", "no-image",
        "social-share", "og-image", "twitter-card", "facebook-share",
        "banner-default", "header-bg", "footer", "sidebar", "widget",
        "spinner", "loading", "btn-", "button", "arrow", "chevron",
        "background", "pattern", "texture", "gradient",
    ]
    if any(p in url_lower for p in skip_patterns): return False
    
    # Verificar se é um arquivo de notícia real (geralmente tem data ou ID no path)
    # Aceitar URLs com padrões de conteúdo dinâmico
    content_patterns = [
        "/files/", "/uploads/", "/media/", "/images/", "/fotos/",
        "/noticia", "/materia", "/artigo", "/post/", "/news/",
        r"\d{4}", r"\d{2,}",  # Anos ou IDs numéricos
    ]
    has_content_pattern = any(p in path_lower for p in content_patterns[:6])
    
    # Verificar dimensões da imagem
    dims = _get_image_dimensions_from_headers(url)
    if dims:
        w, h = dims
        if w < config.MIN_IMAGE_WIDTH or h < config.MIN_IMAGE_HEIGHT:
            return False
        # Imagens muito pequenas ou quadradas demais (provavelmente ícones)
        if w < 200 and h < 200:
            return False
    
    return True


# =====================================================================
# TIER 1: RASPAGEM DIRETA HTML
# =====================================================================

def tier1_scrape_html(html_content: str, source_url: str = "") -> str | None:
    """Busca og:image ou a primeira <img> válida no HTML."""
    if not html_content: return None
    
    # 1. Tentar extrair do BeautifulSoup se og:image estiver presente.
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            url = og_img.get("content")
            if url.startswith("/"):
                # Resolver URL relativa
                parsed = urlparse(source_url)
                url = f"{parsed.scheme}://{parsed.netloc}{url}"
            if is_valid_image_url(url):
                logger.info(f"[TIER 1] Imagem encontrada via og:image: {url}")
                return url
        
        # 2. Tentar buscar tags <img>
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                if src.startswith("/"):
                    parsed = urlparse(source_url)
                    src = f"{parsed.scheme}://{parsed.netloc}{src}"
                if is_valid_image_url(src):
                    logger.info(f"[TIER 1] Imagem encontrada via tag img: {src}")
                    return src
    except Exception as e:
        logger.warning(f"Erro no BeautifulSoup (TIER 1): {e}")

    # Fallback para regex
    og_pattern = re.compile(r"""<meta[^>]+property=['"]og:image['"][^>]+content=['"]([^'"]+)['"]""", re.I)
    match = og_pattern.search(html_content)
    if match and is_valid_image_url(match.group(1)):
        return match.group(1)
        
    return None

# =====================================================================
# TIER 2: BANCOS GOVERNAMENTAIS (AGÊNCIA BRASIL, SENADO, CÂMARA)
# =====================================================================

def tier2_government_banks(keywords: str) -> str | None:
    """
    Busca em bancos governamentais utilizando a API robusta do Google Custom Search 
    restrita aos domínios oficiais (.gov.br, .leg.br, .jus.br, .ebc.com.br).
    Isso substitui o falho webscraping em HTML e blinda matematicamente o Motor contra
    as "Latest News" injetadas nas buscas vazias do governo.
    """
    if not GOOGLE_API_KEY_CSE or not GOOGLE_CSE_ID:
        # Se não houver chave do Google, falha silenciosamente e repassa para TIERs 3
        return None
    
    if not keywords:
        return None
        
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        # Adicionar os filtros implacáveis de portais do governo à sua query
        gov_query = f"{keywords} site:gov.br OR site:leg.br OR site:jus.br OR site:ebc.com.br"
        
        params = {
            "q": gov_query,
            "cx": GOOGLE_CSE_ID,
            "key": GOOGLE_API_KEY_CSE,
            "searchType": "image",
            "num": 3,
            "imgSize": "large"
        }
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("items", []):
                img_url = item.get("link")
                if is_valid_image_url(img_url):
                    logger.info(f"[TIER 2] Imagem limpa extraída via CSE Governamental: {img_url}")
                    return img_url
                    
        logger.debug("[TIER 2] CSE: Sem matches visuais estritos nos domínios do governo.")
    except Exception as e:
        logger.warning(f"[TIER 2] Erro na API do CSE Governamental: {e}")
        
    return None

# =====================================================================
# TIER 3: FLICKR, WIKIMEDIA, GOOGLE CSE
# =====================================================================

# Contas Flickr governamentais brasileiras conhecidas
FLICKR_GOV_USERS = [
    "paborboleta",       # Palácio do Planalto
    "senaborboleta",     # Senado Federal
    "camaborboleta",     # Câmara dos Deputados
    "agaborboleta",      # Agência Brasil
    "govbr",             # Portal Gov.br
    "staborboleta",      # STF
]

def tier3a_flickr_gov(keywords: str) -> str | None:
    """
    Busca em contas Flickr do governo brasileiro usando a API pública.
    Retorna URL da imagem se encontrada.
    """
    if not keywords:
        return None
    
    # Se não tiver API key, usa busca via RSS/feed público
    if not FLICKR_API_KEY:
        return _flickr_fallback_search(keywords)
    
    try:
        # Busca via Flickr API oficial
        params = {
            "method": "flickr.photos.search",
            "api_key": FLICKR_API_KEY,
            "text": keywords,
            "license": "1,2,3,4,5,6,7,9,10",  # Licenças CC e Gov
            "sort": "relevance",
            "per_page": 5,
            "format": "json",
            "nojsoncallback": 1,
            "extras": "url_l,url_m,url_o,owner_name,license",
            "content_type": 1,  # Apenas fotos
            "media": "photos",
        }
        
        # Filtrar por usuários governamentais se possível
        for gov_user in FLICKR_GOV_USERS[:3]:
            params["user_id"] = gov_user
            try:
                resp = requests.get(
                    "https://api.flickr.com/services/rest/",
                    params=params,
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    photos = data.get("photos", {}).get("photo", [])
                    for photo in photos:
                        img_url = photo.get("url_l") or photo.get("url_m") or photo.get("url_o")
                        if img_url and is_valid_image_url(img_url):
                            logger.info(f"[TIER 3A] Imagem Flickr Gov encontrada: {img_url}")
                            return img_url
            except Exception:
                continue
        
        # Busca geral com filtro de licença Creative Commons
        del params["user_id"]
        resp = requests.get(
            "https://api.flickr.com/services/rest/",
            params=params,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            photos = data.get("photos", {}).get("photo", [])
            for photo in photos:
                img_url = photo.get("url_l") or photo.get("url_m") or photo.get("url_o")
                if img_url and is_valid_image_url(img_url):
                    logger.info(f"[TIER 3A] Imagem Flickr CC encontrada: {img_url}")
                    return img_url
                    
    except Exception as e:
        logger.warning(f"[TIER 3A] Erro Flickr API: {e}")
    
    return None

def _flickr_fallback_search(keywords: str) -> str | None:
    """Busca no Flickr via RSS público quando não há API key."""
    try:
        # URL de busca pública do Flickr
        search_url = f"https://www.flickr.com/search/?text={quote_plus(keywords)}&license=2%2C3%2C4%2C5%2C6%2C9"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; BrasileiraNewsBot/1.0)",
            "Accept": "text/html",
        }
        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Buscar imagens nos resultados
            for img in soup.find_all("img", class_=re.compile(r"photo")):
                src = img.get("src")
                if src and "static.flickr" in src:
                    # Converter para tamanho grande
                    large_url = re.sub(r"_[smtq]\.(jpg|png)$", r"_b.\1", src)
                    if is_valid_image_url(large_url):
                        logger.info(f"[TIER 3A] Imagem Flickr via scraping: {large_url}")
                        return large_url
    except Exception as e:
        logger.warning(f"[TIER 3A] Erro Flickr fallback: {e}")
    return None

def tier3b_wikimedia(keywords: str) -> str | None:
    """Busca na Wikipedia/Wikimedia Commons API."""
    if not keywords:
        return None
    
    headers = {
        "User-Agent": "BrasileiraNewsBot/1.0 (https://brasileira.news; contact@brasileira.news)"
    }
    
    try:
        # Passo 1: Buscar arquivos de imagem
        search_url = "https://commons.wikimedia.org/w/api.php"
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": keywords,
            "srnamespace": "6",  # File namespace
            "srlimit": 5,
        }
        search_res = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        if search_res.status_code != 200:
            return None
        
        search_data = search_res.json()
        results = search_data.get("query", {}).get("search", [])
        
        for result in results:
            title = result.get("title", "")
            if not title:
                continue
            
            # Verificar se é uma imagem válida (não SVG, etc)
            if not any(ext in title.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                continue
            
            # Passo 2: Obter URL da imagem
            info_params = {
                "action": "query",
                "format": "json",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|size",
            }
            info_res = requests.get(search_url, params=info_params, headers=headers, timeout=10)
            if info_res.status_code != 200:
                continue
            
            info_data = info_res.json()
            pages = info_data.get("query", {}).get("pages", {})
            
            for page_id, page_info in pages.items():
                imageinfo = page_info.get("imageinfo", [{}])[0]
                img_url = imageinfo.get("url")
                width = imageinfo.get("width", 0)
                height = imageinfo.get("height", 0)
                
                # Verificar tamanho mínimo
                if width >= 400 and height >= 300 and img_url:
                    logger.info(f"[TIER 3B] Imagem encontrada no Wikimedia: {img_url}")
                    return img_url
                    
    except Exception as e:
        logger.warning(f"[TIER 3B] Erro Wikimedia: {e}")
    
    return None

def tier3c_google_cse(keywords: str) -> str | None:
    """Busca via Google Custom Search API, filtrado para .gov.br se configurado."""
    if not GOOGLE_API_KEY_CSE or not GOOGLE_CSE_ID:
        return None
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": keywords,
            "cx": GOOGLE_CSE_ID,
            "key": GOOGLE_API_KEY_CSE,
            "searchType": "image",
            "num": 3,
            "imgSize": "large"
        }
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("items", []):
                img_url = item.get("link")
                if is_valid_image_url(img_url):
                    logger.info(f"[TIER 3C] Imagem Google CSE encontrada: {img_url}")
                    return img_url
    except Exception as e:
        logger.warning(f"[TIER 3C] Erro Google CSE: {e}")
    return None

# =====================================================================
# TIER 4: STOCK APIs
# =====================================================================

def tier4_stock_apis(keywords: str) -> tuple[str | None, str]:
    """Cascata de APIs de Stock para retorno de imagem e crédito."""
    # 1. Unsplash
    if UNSPLASH_ACCESS_KEY:
        try:
            res = requests.get(
                "https://api.unsplash.com/photos/random",
                params={"query": keywords, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
                timeout=10
            )
            if res.status_code == 200:
                data = res.json()
                img_url = data.get("urls", {}).get("regular")
                user = data.get("user", {}).get("name", "Unsplash")
                if is_valid_image_url(img_url):
                    logger.info(f"[TIER 4] Imagem Unsplash encontrada")
                    return img_url, f"Foto por {user} via Unsplash"
        except Exception as e:
            logger.warning(f"[TIER 4] Erro Unsplash: {e}")

    # 2. Pexels
    if PEXELS_API_KEY:
        try:
            res = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": keywords, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": PEXELS_API_KEY},
                timeout=10
            )
            if res.status_code == 200:
                photos = res.json().get("photos", [])
                if photos:
                    img_url = photos[0].get("src", {}).get("large")
                    photographer = photos[0].get("photographer", "Pexels")
                    if is_valid_image_url(img_url):
                        logger.info(f"[TIER 4] Imagem Pexels encontrada")
                        return img_url, f"Foto por {photographer} via Pexels"
        except Exception as e:
            logger.warning(f"[TIER 4] Erro Pexels: {e}")
            
    # 3. Pixabay
    if PIXABAY_API_KEY:
        try:
            res = requests.get(
                "https://pixabay.com/api/",
                params={"key": PIXABAY_API_KEY, "q": keywords, "image_type": "photo", "orientation": "horizontal"},
                timeout=10
            )
            if res.status_code == 200:
                hits = res.json().get("hits", [])
                if hits:
                    img_url = hits[0].get("largeImageURL")
                    user = hits[0].get("user", "Pixabay")
                    if is_valid_image_url(img_url):
                        logger.info(f"[TIER 4] Imagem Pixabay encontrada")
                        return img_url, f"Foto por {user} via Pixabay"
        except Exception as e:
            logger.warning(f"[TIER 4] Erro Pixabay: {e}")

    return None, ""

# =====================================================================
# UPLOAD PARA WORDPRESS
# =====================================================================

def upload_to_wordpress(image_url: str, filename: str, alt_text: str = "", caption: str = "") -> int | None:
    """Baixa de `image_url`, aplica SmartCrop (1200x675) com detecção facial e sobe pro WP."""
    try:
        # Anti-repetição: verificar se imagem já foi usada
        try:
            from memoria_editorial import imagem_ja_usada, registrar_imagem
            if imagem_ja_usada(image_url):
                logger.info(f"[Upload] Imagem já usada nas últimas 72h, pulando: {image_url[:80]}")
                return None
        except ImportError:
            pass

        resp = requests.get(image_url, timeout=config.HTTP_TIMEOUT, stream=True)
        if resp.status_code != 200: return None
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        image_data = resp.content
        if len(image_data) < 1000: return None

        # --- CROP 16:9 com detecção facial ---
        try:
            from io import BytesIO
            from PIL import Image
            import numpy as np
            
            img = Image.open(BytesIO(image_data))
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')
            elif img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            
            w, h = img.size
            logger.info(f"[Upload] Imagem original: {w}x{h}, {len(image_data)} bytes")
            
            if w >= 200 and h >= 112:
                target_ratio = 16 / 9
                current_ratio = w / h
                
                # Tentar detecção facial para crop inteligente
                face_center_y = None
                try:
                    import cv2
                    img_array = np.array(img)
                    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                    
                    if len(faces) > 0:
                        # Centralizar no rosto mais proeminente (maior área)
                        largest_face = max(faces, key=lambda f: f[2] * f[3])
                        fx, fy, fw, fh = largest_face
                        face_center_y = fy + fh // 2
                        logger.info(f"[Upload] Rosto detectado em ({fx},{fy},{fw}x{fh})")
                except Exception as e:
                    logger.debug(f"[Upload] OpenCV não disponível ou falhou: {e}")
                
                # Crop com consciência facial
                if current_ratio > target_ratio:
                    # Imagem muito larga → crop horizontal (center)
                    new_w = int(h * target_ratio)
                    left = (w - new_w) // 2
                    img = img.crop((left, 0, left + new_w, h))
                else:
                    # Imagem muito alta → crop vertical (face-aware)
                    new_h = int(w / target_ratio)
                    if face_center_y is not None:
                        # Centralizar no rosto, com limites
                        top = max(0, min(face_center_y - new_h // 2, h - new_h))
                    else:
                        # Fallback: crop no terço superior (mais provável ter o sujeito)
                        top = max(0, (h - new_h) // 3)
                    img = img.crop((0, top, w, top + new_h))
                
                img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            image_data = buffer.getvalue()
            content_type = "image/jpeg"
            logger.info(f"[Upload] Processada: {len(image_data)} bytes (JPEG 1200x675)")
                
        except Exception as e:
            logger.warning(f"Erro no processamento de imagem, usando original: {e}")
        # ---------------------------

        ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
        ext = ext_map.get(content_type, ".jpg")
        base = filename.rsplit(".", 1)[0] if "." in filename else filename
        final_filename = base + ext

        auth = (config.WP_USER, config.WP_APP_PASS)
        headers = {
            "Content-Disposition": f'attachment; filename="{final_filename}"',
            "Content-Type": content_type
        }

        up_resp = requests.post(
            f"{config.WP_API_BASE}/media",
            auth=auth, headers=headers, data=image_data, timeout=30
        )
        if up_resp.status_code in (200, 201):
            media_id = up_resp.json().get("id")
            logger.info(f"Imagem uploaded sucesso: media_id={media_id}")
            
            # Registrar no catálogo anti-repetição
            try:
                from memoria_editorial import registrar_imagem
                registrar_imagem(image_url, titulo=alt_text, media_id=media_id)
            except Exception:
                pass
            
            # Postar meta: alt_text e caption
            meta_payload = {}
            if alt_text: meta_payload["alt_text"] = alt_text[:255]
            if caption: meta_payload["caption"] = caption
            
            if meta_payload:
                requests.post(
                    f"{config.WP_API_BASE}/media/{media_id}",
                    auth=auth, json=meta_payload, timeout=10
                )
            return media_id
        else:
            logger.warning(f"Erro upload WP (HTTP {up_resp.status_code}): {up_resp.text[:100]}")
    except Exception as e:
        logger.warning(f"Upload para WP falhou: {e}")
    return None

# =====================================================================
# GERAÇÃO DE LEGENDA + ALT TEXT via LLM (Assistente de Fotografia)
# =====================================================================

# Créditos formatados por tier de fonte
_CREDIT_TEMPLATES = {
    "tier1_oficial": "Reprodução / {domain}",
    "tier2_gov": "Foto: {domain} / Divulgação",
    "tier3a_flickr": "Foto: {photographer} / Flickr (CC BY)",
    "tier3b_wikimedia": "Imagem sob Licença Creative Commons via Wikimedia Commons",
    "tier3c_cse": "Foto: Reprodução / {domain}",
    "tier4_unsplash": "Foto: {photographer} / Unsplash",
    "tier4_pexels": "Foto: {photographer} / Pexels",
    "tier4_pixabay": "Foto: {photographer} / Pixabay",
    "tier5_placeholder": "Imagem ilustrativa / Brasileira.News",
}

def gerar_legenda_alt_text(titulo: str, fonte_tier: str = "", image_url: str = "") -> tuple[str, str]:
    """
    Gera alt_text descritivo (SEO/acessibilidade) e caption contextualizada via LLM econômico.
    Retorna (alt_text, caption).
    """
    # Tentar LLM econômico para alt text
    alt_text = titulo  # fallback
    try:
        from llm_router import call_llm, TIER_PHOTO_ASSISTANT
        
        prompt = f"""Gere um ALT TEXT descritivo para a imagem de uma notícia.
O alt text deve:
- Descrever a cena provável da imagem (baseado no título da notícia)
- Ser conciso (máximo 120 caracteres)
- Incluir contexto visual útil para acessibilidade
- NÃO repetir o título literalmente

Título da notícia: {titulo}
Fonte da imagem: {fonte_tier}

Responda APENAS com o alt text, sem explicações."""

        result, provider = call_llm(
            "Você é um assistente de fotografia que gera textos descritivos para acessibilidade.",
            prompt,
            tier=TIER_PHOTO_ASSISTANT
        )
        if result and len(result) < 200:
            alt_text = result.strip().strip('"').strip("'")
            logger.info(f"[Alt Text] Gerado via {provider}: {alt_text[:60]}...")
    except Exception as e:
        logger.debug(f"[Alt Text] LLM falhou, usando título: {e}")
    
    # Caption formatada por fonte
    caption = _CREDIT_TEMPLATES.get(fonte_tier, f"Foto: Reprodução")
    
    return alt_text, caption


# =====================================================================
# FUNÇÃO PRINCIPAL
# =====================================================================

def get_best_image_for_post(
    html_content: str = "",
    source_url: str = "",
    title: str = "",
    keywords: str = "",
    force_fallback: bool = False,
    explicit_gov_query: str = "",
    explicit_commons_query: str = "",
    explicit_stock_query: str = "",
    explicit_block_stock: bool | None = None
) -> int | None:
    """
    Tenta obter a featured image percorrendo todos os Tiers.
    Usa queries otimizadas para cada tipo de fonte.
    """
    logger.info(f"Buscando melhor imagem para: {title[:50]}...")
    safe_filename = re.sub(r"[^a-z0-9]+", "-", title.lower().strip())[:50]
    
    # 1. Determina se a fonte é oficial
    is_official = is_official_source(source_url)
    
    # Resolver a categoria antecipadamente para influenciar a busca
    category = "geral"
    _query_generator = None # Initialize _query_generator
    try:
        _query_generator = get_query_generator()
        category = _query_generator._detect_category(title, html_content) if html_content else "geral"
    except Exception:
        pass
    
    # TIER 1: Original Source Scrape (Se for OFICIAL tentamos com prioridade; se comercial, pula obrigatoriamente)
    if not force_fallback and is_official:
        tier1_url = tier1_scrape_html(html_content, source_url)
        if tier1_url:
            domain = urlparse(source_url).netloc
            alt_text, caption = gerar_legenda_alt_text(title, "tier1_oficial", tier1_url)
            caption = caption.format(domain=domain)
            media_id = upload_to_wordpress(tier1_url, safe_filename, alt_text=alt_text, caption=caption)
            if media_id: return media_id

    # Cérebro IA: Gerar as melhores queries de busca OU usar explicitas vindas do Sintetizador
    if explicit_gov_query or explicit_commons_query or explicit_block_stock is not None:
        logger.info("[Curador] Usando queries EXPLICITAS fornecidas pela Redação IA.")
        query_gov = [explicit_gov_query or title[:50]]
        query_commons = [explicit_commons_query or title[:50]]
        query_stock = [explicit_stock_query or "News background"]
        block_stock = explicit_block_stock if explicit_block_stock is not None else False
    else:
        logger.info("[Curador] Nenhuma query explicita fornecida, acionando IA Editor de Fotografia")
        if _query_generator is None:
            _query_generator = get_query_generator()
        tier_queries = _query_generator._generate_ai_queries(title, html_content, category)
        if tier_queries:
            query_gov = tier_queries.get("gov_pt", [title[:50]])
            query_commons = tier_queries.get("commons", [title[:50]])
            query_stock = tier_queries.get("stock_en", ["Brazil news"])
            block_stock = tier_queries.get("block_stock", False)
        else:
            default_queries = _query_generator._build_default_queries(category, _query_generator._extract_key_entities(title, html_content), title)
            query_gov = [default_queries.get("gov_pt", title[:50])]
            query_commons = [default_queries.get("commons", title[:50])]
            query_stock = [default_queries.get("stock_en", "Brazil news")]
            block_stock = False
    
    # Normalizar para listas
    if isinstance(query_gov, str): query_gov = [query_gov]
    if isinstance(query_commons, str): query_commons = [query_commons]
    if isinstance(query_stock, str): query_stock = [query_stock]
    
    logger.info(f"[Queries] GOV: {query_gov}")
    logger.info(f"[Queries] COMMONS: {query_commons}")
    logger.info(f"[Queries] STOCK: {query_stock}")
    logger.info(f"[Queries] BLOCK_STOCK: {block_stock}")

    # TIER 2: Bancos do Governo — tentar cada nível de query
    for q in query_gov:
        tier2_url = tier2_government_banks(q)
        if tier2_url:
            domain = urlparse(tier2_url).netloc
            alt_text, caption = gerar_legenda_alt_text(title, "tier2_gov", tier2_url)
            caption = caption.format(domain=domain, photographer="")
            media_id = upload_to_wordpress(tier2_url, safe_filename, alt_text=alt_text, caption=caption)
            if media_id: return media_id
        logger.debug(f"[TIER 2] Nenhum resultado para: {q}")

    # TIER 3C: Google CSE Imagens Abertas — tentar cada nível
    for q in query_gov:
        tier3c_url = tier3c_google_cse(q)
        if tier3c_url:
            domain = urlparse(tier3c_url).netloc
            alt_text, caption = gerar_legenda_alt_text(title, "tier3c_cse", tier3c_url)
            caption = caption.format(domain=domain, photographer="")
            media_id = upload_to_wordpress(tier3c_url, safe_filename, alt_text=alt_text, caption=caption)
            if media_id: return media_id
        logger.debug(f"[TIER 3C] Nenhum resultado para: {q}")

    # TIER 3A: Flickr Governamental/Institucional — tentar cada nível
    for q in query_gov:
        tier3a_url = tier3a_flickr_gov(q)
        if tier3a_url:
            alt_text, caption = gerar_legenda_alt_text(title, "tier3a_flickr", tier3a_url)
            caption = caption.format(domain="Flickr", photographer="Autor")
            media_id = upload_to_wordpress(tier3a_url, safe_filename, alt_text=alt_text, caption=caption)
            if media_id: return media_id
        logger.debug(f"[TIER 3A] Nenhum resultado para: {q}")

    # TIER 3B: Wikimedia/Wikipedia — tentar cada nível
    for q in query_commons:
        tier3b_url = tier3b_wikimedia(q)
        if tier3b_url:
            alt_text, caption = gerar_legenda_alt_text(title, "tier3b_wikimedia", tier3b_url)
            media_id = upload_to_wordpress(tier3b_url, safe_filename, alt_text=alt_text, caption=caption)
            if media_id: return media_id
        logger.debug(f"[TIER 3B] Nenhum resultado para: {q}")

    # TIER 4: Stock API (Unsplash/Pexels) - GATILHO CAUTELAR
    category_blocks = ["politica", "justica", "esportes", "celebridades"]
    if category in category_blocks or block_stock:
        logger.info(f"[TIER 4] Stock bloqueado para a categoria '{category}' ou pela flag BLOCK_STOCK={block_stock}.")
    else:
        for q in query_stock:
            tier4_url, tier4_credit = tier4_stock_apis(q)
            if tier4_url:
                # tier4_credit já contém "Foto por X via Unsplash/Pexels"
                alt_text, _ = gerar_legenda_alt_text(title, "tier4_unsplash", tier4_url)
                media_id = upload_to_wordpress(tier4_url, safe_filename, alt_text=alt_text, caption=tier4_credit)
                if media_id: return media_id
            logger.debug(f"[TIER 4] Nenhum resultado para: {q}")

    # TIER 5: Placeholder TIER
    logger.info("Todos os Tiers falharam. Usando imagem placeholder de fallback.")
    media_id = upload_to_wordpress(PLACEHOLDER_IMAGE_URL, f"fallback-{safe_filename}", alt_text="Imagem de Notícia")
    return media_id


# =====================================================================
# CLASSE SINGLETON PARA COMPATIBILIDADE
# =====================================================================

class CuradorImagensUnificado:
    """
    Classe wrapper singleton para compatibilidade com sistemas existentes.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_featured_image(
        self,
        html_content: str = "",
        source_url: str = "",
        title: str = "",
        keywords: str = "",
        explicit_gov_query: str = "",
        explicit_commons_query: str = "",
        explicit_stock_query: str = "",
        explicit_block_stock: bool | None = None
    ) -> Tuple[Optional[int], str]:
        """
        Interface principal para obter imagem.
        Retorna (media_id, caption) ou (None, "").
        """
        media_id = get_best_image_for_post(
            html_content=html_content,
            source_url=source_url,
            title=title,
            keywords=keywords,
            explicit_gov_query=explicit_gov_query,
            explicit_commons_query=explicit_commons_query,
            explicit_stock_query=explicit_stock_query,
            explicit_block_stock=explicit_block_stock
        )
        
        if media_id:
            caption = self._generate_caption(source_url, title)
            return media_id, caption
        return None, ""
    
    def _generate_caption(self, source_url: str, title: str) -> str:
        """Gera legenda baseada na fonte."""
        if is_official_source(source_url):
            domain = urlparse(source_url).netloc
            return f"Reprodução / {domain}"
        return "Imagem ilustrativa"
    
    def _url_valida(self, url: str) -> bool:
        """Valida URL de imagem."""
        return is_valid_image_url(url)
    
    def curar_imagem(
        self,
        html_content: str = "",
        source_url: str = "",
        title: str = "",
        keywords: str = ""
    ) -> Tuple[Optional[int], str]:
        """Alias para get_featured_image."""
        return self.get_featured_image(html_content, source_url, title, keywords)


# Singleton instance
_curador_instance = None

def get_curador() -> CuradorImagensUnificado:
    """Retorna instância singleton do curador."""
    global _curador_instance
    if _curador_instance is None:
        _curador_instance = CuradorImagensUnificado()
    return _curador_instance


# =====================================================================
# FUNÇÕES DE COMPATIBILIDADE RETROATIVA (motor_rss/image_handler.py)
# =====================================================================

def get_featured_image(
    html_content: str = "",
    source_url: str = "",
    title: str = "",
    keywords: str = ""
) -> Tuple[Optional[int], str]:
    """
    Função de compatibilidade para sistemas existentes.
    Retorna (media_id, caption).
    """
    return get_curador().get_featured_image(html_content, source_url, title, keywords)


def search_unsplash(query: str) -> Optional[str]:
    """
    Busca imagem no Unsplash (compatibilidade).
    Retorna URL da imagem ou None.
    """
    if not UNSPLASH_ACCESS_KEY:
        logger.warning("[Compat] Unsplash API key não configurada")
        return None
    
    try:
        res = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": query, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10
        )
        if res.status_code == 200:
            data = res.json()
            return data.get("urls", {}).get("regular")
    except Exception as e:
        logger.warning(f"[Compat] Erro search_unsplash: {e}")
    return None


def extract_image_from_content(html_content: str, source_url: str = "") -> Optional[str]:
    """
    Extrai imagem do conteúdo HTML (compatibilidade).
    Retorna URL da imagem ou None.
    """
    return tier1_scrape_html(html_content, source_url)


# =====================================================================
# GERAÇÃO DE KEYWORDS COM IA - SISTEMA AVANÇADO MULTI-TIER
# =====================================================================

class ImageQueryGenerator:
    """
    Gerador inteligente de queries para busca de imagens.
    Analisa o conteúdo da notícia em profundidade e gera queries otimizadas
    para cada tipo de fonte (governamental, Wikimedia, stock photos).
    """
    
    def __init__(self):
        self.gemini_key = getattr(config, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        
        # Mapeamento de categorias para contextos visuais
        self.visual_contexts = {
            "politica": ["Congresso Nacional", "Palácio do Planalto", "plenário", "votação", "sessão", "Brasília", "parlamentar"],
            "economia": ["Banco Central", "mercado financeiro", "bolsa valores", "gráfico economia", "moeda real", "notas dinheiro"],
            "saude": ["hospital", "atendimento médico", "vacina", "SUS", "ministério saúde", "equipamento médico"],
            "educacao": ["escola", "universidade", "sala aula", "estudantes", "MEC", "livros educação"],
            "seguranca": ["polícia federal", "viatura policial", "operação policial", "segurança pública", "prisão"],
            "meio_ambiente": ["floresta amazônica", "desmatamento", "IBAMA", "preservação ambiental", "natureza Brasil"],
            "tecnologia": ["tecnologia digital", "computador", "inovação", "data center", "startup"],
            "agricultura": ["plantação", "colheita", "agricultura", "fazenda", "agronegócio", "tratores"],
            "infraestrutura": ["obras", "construção", "rodovia", "ponte", "infraestrutura"],
            "justica": ["tribunal", "STF", "justiça", "martelo juiz", "toga", "fórum"],
            "esportes": ["estádio futebol", "partida futebol", "torcida", "jogadores campo", "troféu campeonato"],
            "celebridades": ["tapete vermelho", "show de música", "gravação televisão", "evento celebridades"],
        }
    
    def _detect_category(self, title: str, content: str) -> str:
        """Detecta a categoria principal da notícia."""
        text = (title + " " + content).lower()
        
        category_keywords = {
            "politica": ["governo", "presidente", "ministro", "congresso", "senado", "câmara", "deputado", "senador", "lei", "pec", "votação", "planalto"],
            "economia": ["economia", "selic", "juros", "banco central", "inflação", "pib", "mercado", "bolsa", "dólar", "real", "copom"],
            "saude": ["saúde", "hospital", "médico", "vacina", "sus", "anvisa", "doença", "tratamento", "pandemia"],
            "educacao": ["educação", "escola", "universidade", "mec", "enem", "estudante", "professor", "ensino"],
            "seguranca": ["polícia", "pf", "operação", "prisão", "crime", "segurança", "investigação", "tráfico", "drogas"],
            "meio_ambiente": ["ambiente", "amazônia", "desmatamento", "ibama", "clima", "floresta", "sustentável"],
            "tecnologia": ["tecnologia", "digital", "internet", "aplicativo", "startup", "inovação", "inteligência artificial"],
            "agricultura": ["agricultura", "agro", "safra", "colheita", "plantação", "fazenda", "soja", "milho", "gado"],
            "infraestrutura": ["infraestrutura", "obra", "rodovia", "ferrovia", "aeroporto", "porto", "construção"],
            "justica": ["justiça", "stf", "tribunal", "juiz", "processo", "julgamento", "recurso", "sentença"],
            "esportes": ["futebol", "jogo", "partida", "campeonato", "estádio", "torcida", "time", "clube", "jogador", "técnico", "gol", "tênis", "basquete", "vôlei", "olimpíadas"],
            "celebridades": ["ator", "atriz", "cantor", "famoso", "celebridade", "novela", "filme", "série", "televisão", "show"],
        }
        
        scores = {}
        for category, keywords in category_keywords.items():
            scores[category] = sum(1 for kw in keywords if kw in text)
        
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return "geral"
    
    def _extract_key_entities(self, title: str, content: str) -> dict:
        """Extrai entidades-chave do texto."""
        text = title + " " + content
        
        entities = {
            "instituicoes": [],
            "lugares": [],
            "eventos": [],
            "objetos": [],
        }
        
        # Instituições brasileiras
        inst_patterns = [
            r"(Banco Central|BC|Copom)",
            r"(Senado Federal|Senado)",
            r"(Câmara dos Deputados|Câmara)",
            r"(Congresso Nacional)",
            r"(Supremo Tribunal Federal|STF)",
            r"(Polícia Federal|PF)",
            r"(Ministério (?:da |de |do )?[\w\s]+)",
            r"(Palácio do Planalto|Planalto)",
            r"(IBGE|INSS|IBAMA|ANVISA|ANS|ANEEL|ANATEL)",
            r"(Petrobras|BNDES|Caixa|Banco do Brasil)",
        ]
        
        for pattern in inst_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities["instituicoes"].extend(matches[:2])
        
        # Lugares
        lugares = re.findall(
            r"(?:em |no |na |de |do |da )(Brasília|São Paulo|Rio de Janeiro|Belo Horizonte|Salvador|Fortaleza|Recife|Porto Alegre|Curitiba|Manaus|Belém|Amazônia)",
            text, re.IGNORECASE
        )
        entities["lugares"] = list(set(lugares))[:2]
        
        # Eventos/ações
        eventos = re.findall(
            r"(votação|sessão|reunião|operação|leilão|audiência|cerimônia|sanção|promulgação|julgamento|decisão)",
            text.lower()
        )
        entities["eventos"] = list(set(eventos))[:2]
        
        return entities
    
    def generate_queries(self, title: str, content: str) -> dict:
        """
        Gera queries otimizadas para cada tipo de TIER.
        
        Returns:
            dict com keys: 'gov_pt' (TIER 1-2), 'commons' (TIER 3), 'stock_en' (TIER 4)
        """
        # Limpar HTML
        clean_content = re.sub(r'<[^>]+>', ' ', content) if content else ""
        clean_content = re.sub(r'\s+', ' ', clean_content).strip()[:2500]
        
        category = self._detect_category(title, clean_content)
        entities = self._extract_key_entities(title, clean_content)
        
        # Query padrão baseada em entidades
        default_queries = self._build_default_queries(category, entities, title)
        
        # Se tiver Gemini, usar IA para refinar
        if self.gemini_key:
            ai_queries = self._generate_ai_queries(title, clean_content, category)
            if ai_queries:
                return ai_queries
        
        return default_queries
    
    def _build_default_queries(self, category: str, entities: dict, title: str) -> dict:
        """Constrói queries padrão baseadas em entidades extraídas."""
        
        # Query para fontes governamentais (português)
        gov_parts = []
        if entities["instituicoes"]:
            gov_parts.append(entities["instituicoes"][0])
        if entities["lugares"]:
            gov_parts.append(entities["lugares"][0])
        if entities["eventos"]:
            gov_parts.append(entities["eventos"][0])
        if not gov_parts and category in self.visual_contexts:
            gov_parts = self.visual_contexts[category][:2]
        
        gov_query = " ".join(gov_parts) if gov_parts else title[:50]
        
        # Query para Wikimedia/Commons (mais descritiva)
        commons_parts = []
        if entities["instituicoes"]:
            commons_parts.append(entities["instituicoes"][0])
        if entities["lugares"]:
            commons_parts.append(entities["lugares"][0])
        commons_parts.append("Brasil")
        commons_query = " ".join(commons_parts)
        
        # Query para stock photos (inglês)
        stock_translations = {
            "politica": "Brazil congress politics government Brasilia",
            "economia": "Brazil economy finance central bank money",
            "saude": "Brazil healthcare hospital medical",
            "educacao": "Brazil education school university",
            "seguranca": "Brazil police federal operation security",
            "meio_ambiente": "Brazil Amazon forest environment nature",
            "tecnologia": "Brazil technology digital innovation",
            "agricultura": "Brazil agriculture farm harvest crops",
            "infraestrutura": "Brazil infrastructure construction road",
            "justica": "Brazil court justice law tribunal",
            "esportes": "Brazil sports soccer match stadium",
            "celebridades": "Brazil entertainment celebrity television",
            "geral": "Brazil news current events",
        }
        stock_query = stock_translations.get(category, "Brazil news")
        
        return {
            "gov_pt": gov_query,
            "commons": commons_query,
            "stock_en": stock_query,
        }
    
    def _generate_ai_queries(self, title: str, content: str, category: str) -> dict | None:
        """Usa Gemini para gerar queries otimizadas com 3 níveis de especificidade."""
        
        prompt = f"""Você é o Editor de Fotografia Chefe de um portal de notícias do Brasil.

EXTRAIA AS ENTIDADES VISUAIS PRINCIPAIS da notícia para buscar fotos em bancos de imagens.
Gere queries em 3 NÍVEIS DE ESPECIFICIDADE para cada tier, do mais preciso ao mais genérico.
Isso permite encontrar a melhor imagem possível: se a busca mais específica falhar, tentamos a média, depois a genérica.

EXEMPLO REAL: Notícia "Lula faz declaração contra medida tomada pelo BC"
- QUERY_GOV_1: "Lula" AND "Banco Central" (foto do evento específico)
- QUERY_GOV_2: "Lula" (foto do presidente em qualquer contexto)
- QUERY_GOV_3: "Banco Central" OR "Brasília" (foto institucional genérica)

REGRAS:
- NUNCA use ações/sentimentos ("discurso", "conflito", "celebrando") — zera resultados
- Use nomes curtos e populares ("Lula", não "Luiz Inácio Lula da Silva")
- Use aspas e operadores booleanos (AND, OR)

NOTÍCIA PARA ILUSTRAR:
Título: {title}
Conteúdo: {content[:1500]}
Categoria detectada: {category}

TAREFA: Gerar queries escaladas + flag.

1. **QUERY_GOV** (3 níveis — Google Imagens + Flickr, em português):
   - _1: Combinação específica das entidades principais
   - _2: Entidade principal isolada
   - _3: Contexto institucional/geográfico genérico

2. **QUERY_COMMONS** (3 níveis — Wikimedia Commons):
   - _1: Nome específico da pessoa/instituição/local
   - _2: Instituição ou local relacionado
   - _3: Categoria temática genérica

3. **QUERY_STOCK** (3 níveis — Unsplash/Pexels em INGLÊS):
   - _1: Conceito específico
   - _2: Conceito médio
   - _3: Conceito muito genérico

4. **BLOCK_STOCK**: TRUE se precisa de foto real (pessoas, clubes, instituições); FALSE se pode ser genérica.

Responda APENAS no formato:
QUERY_GOV_1: [query]
QUERY_GOV_2: [query]
QUERY_GOV_3: [query]
QUERY_COMMONS_1: [query]
QUERY_COMMONS_2: [query]
QUERY_COMMONS_3: [query]
QUERY_STOCK_1: [query]
QUERY_STOCK_2: [query]
QUERY_STOCK_3: [query]
BLOCK_STOCK: [TRUE ou FALSE]"""

        try:
            from llm_router import call_llm, TIER_PHOTO_EDITOR
            
            system_prompt = "Você é o Editor de Fotografia Chefe de um portal jornalístico. Responda APENAS no formato solicitado, sem explicações adicionais."
            text, provider = call_llm(system_prompt, prompt, tier=TIER_PHOTO_EDITOR)
            
            if not text:
                logger.warning("[AI Queries] call_llm retornou None")
                return None
            
            logger.info(f"[AI Queries] Provider: {provider}")
                
            queries = {}
            
            # Parse 3 levels for each tier
            for tier_key, output_key in [("QUERY_GOV", "gov_pt"), ("QUERY_COMMONS", "commons"), ("QUERY_STOCK", "stock_en")]:
                levels = []
                for level in range(1, 4):
                    match = re.search(rf"{tier_key}_{level}:\s*(.+?)(?:\n|$)", text)
                    if match:
                        levels.append(self._clean_query(match.group(1)))
                if levels:
                    queries[output_key] = levels
                
            # Fallback: parse old single-query format for backward compat
            if not queries:
                for key, pattern in [("gov_pt", "QUERY_GOV"), ("commons", "QUERY_COMMONS"), ("stock_en", "QUERY_STOCK")]:
                    match = re.search(rf"{pattern}:\s*(.+?)(?:\n|$)", text)
                    if match:
                        queries[key] = [self._clean_query(match.group(1))]
            
            block_stock_match = re.search(r"BLOCK_STOCK:\s*(TRUE|FALSE)", text, re.I)
            queries["block_stock"] = block_stock_match.group(1).upper() == "TRUE" if block_stock_match else False
            
            if len(queries) >= 2:
                for key in ["gov_pt", "commons", "stock_en"]:
                    vals = queries.get(key, [])
                    logger.info(f"[AI Queries] {key}: {vals}")
                logger.info(f"[AI Queries] block_stock: {queries.get('block_stock', False)}")
                return queries
                    
        except Exception as e:
            logger.warning(f"[AI Queries] Erro: {e}")
        
        return None
    
    def _clean_query(self, query: str) -> str:
        """Limpa uma query de busca preservando aspas e operadores booleanos."""
        query = re.sub(r'[\[\]\*\#\']', '', query)
        query = re.sub(r'\s+', ' ', query).strip()
        return query


# Instância global do gerador
_query_generator = None

def get_query_generator() -> ImageQueryGenerator:
    """Retorna instância singleton do gerador de queries."""
    global _query_generator
    if _query_generator is None:
        _query_generator = ImageQueryGenerator()
    return _query_generator


def generate_search_keywords(title: str, content: str = "", use_ai: bool = True) -> str:
    """
    Função de compatibilidade - retorna query principal para uso geral.
    Para queries específicas por TIER, use get_query_generator().generate_queries()
    """
    generator = get_query_generator()
    queries = generator.generate_queries(title, content)
    
    # Retorna a query governamental como padrão (mais usada nos TIERs iniciais)
    return queries.get("gov_pt", title[:50])


def generate_tier_queries(title: str, content: str = "") -> dict:
    """
    Gera queries otimizadas para cada TIER.
    
    Returns:
        dict com keys: 'gov_pt' (TIER 1-2), 'commons' (TIER 3), 'stock_en' (TIER 4)
    """
    generator = get_query_generator()
    return generator.generate_queries(title, content)


if __name__ == "__main__":
    # Teste rápido de execução
    print("Módulo Curador de Imagens Unificado (TIER 1-5)")
    print(f"  - Unsplash key: {'OK' if UNSPLASH_ACCESS_KEY else 'MISSING'}")
    print(f"  - Pexels key: {'OK' if PEXELS_API_KEY else 'MISSING'}")
    print(f"  - Pixabay key: {'OK' if PIXABAY_API_KEY else 'MISSING'}")
    print(f"  - Google CSE: {'OK' if GOOGLE_CSE_ID and GOOGLE_API_KEY_CSE else 'MISSING'}")
    print(f"  - Flickr key: {'OK' if FLICKR_API_KEY else 'USING FALLBACK'}")
