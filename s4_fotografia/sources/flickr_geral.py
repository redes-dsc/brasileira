#!/usr/bin/env python3
"""
Módulo de busca de imagens - Flickr Geral (CC)

Tier 8 no pipeline de busca de imagens.
Busca geral no Flickr com filtro de licenças Creative Commons.
Não limitado a contas governamentais.
Licença: CC (várias versões)
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Configurações
_FLICKR_API_KEY = None
FLICKR_ENDPOINT = "https://api.flickr.com/services/rest/"
TIMEOUT = 10
MAX_RESULTS = 10

# Licenças CC compatíveis com uso editorial
CC_LICENSES = "4,5,6,7,8,9,10"
# 4=CC BY, 5=CC BY-SA, 6=CC BY-ND, 7=No known copyright,
# 8=US Gov, 9=CC0, 10=Public Domain Mark
# Licenças NC (1,2,3) removidas — risco jurídico para uso editorial

# Mapeamento de ID de licença para nome legível
LICENSE_NAMES = {
    "1": "CC BY-NC-SA",
    "2": "CC BY-NC",
    "3": "CC BY-NC-ND",
    "4": "CC BY",
    "5": "CC BY-SA",
    "6": "CC BY-ND",
    "7": "No known copyright restrictions",
    "8": "US Government Work",
    "9": "CC0",
    "10": "Public Domain",
}


def _get_photo_url(photo: dict) -> Optional[str]:
    """Extrai a melhor URL de imagem disponível."""
    # Prioridade: url_l (large) > url_c (medium 800) > url_o (original)
    url = photo.get("url_l") or photo.get("url_c") or photo.get("url_o")
    
    if not url and photo.get("farm") and photo.get("server") and photo.get("id") and photo.get("secret"):
        # Construir URL manualmente se não vier nas extras
        farm = photo.get("farm")
        server = photo.get("server")
        photo_id = photo.get("id")
        secret = photo.get("secret")
        url = f"https://live.staticflickr.com/{server}/{photo_id}_{secret}_b.jpg"
    
    return url


def _get_license_name(license_id: str) -> str:
    """Retorna nome legível da licença."""
    return LICENSE_NAMES.get(str(license_id), "CC")


def search(query: str, **kwargs) -> list[dict]:
    """
    Busca geral no Flickr com filtro de licenças Creative Commons.
    
    Args:
        query: Termo de busca
        **kwargs: Argumentos adicionais (ignorados)
    
    Returns:
        Lista de resultados com imagens CC
    """
    global _FLICKR_API_KEY
    if _FLICKR_API_KEY is None:
        _FLICKR_API_KEY = os.getenv("_FLICKR_API_KEY", "")
    global _FLICKR_API_KEY
    if _FLICKR_API_KEY is None:
        _FLICKR_API_KEY = os.getenv("_FLICKR_API_KEY", "")
    if not _FLICKR_API_KEY:
        logger.warning("[flickr_geral] _FLICKR_API_KEY não configurada")
        return []
    
    if not query or not query.strip():
        return []
    
    results = []
    
    try:
        logger.info(f"[flickr_geral] Buscando: {query}")
        
        params = {
            "method": "flickr.photos.search",
            "api_key": _FLICKR_API_KEY,
            "text": query,
            "license": CC_LICENSES,
            "sort": "relevance",
            "per_page": MAX_RESULTS,
            "page": 1,
            "extras": "url_l,url_o,url_c,description,owner_name,license",
            "format": "json",
            "nojsoncallback": 1,
            "content_type": 1,  # Apenas fotos
            "media": "photos",
        }
        
        resp = requests.get(FLICKR_ENDPOINT, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("stat") == "fail":
            logger.warning(f"[flickr_geral] Flickr API erro: {data.get('message', 'Unknown')}")
            return []
        
        photos = data.get("photos", {}).get("photo", [])
        
        for idx, photo in enumerate(photos):
            img_url = _get_photo_url(photo)
            
            if not img_url:
                continue
            
            title = photo.get("title", "")
            description = photo.get("description", {})
            if isinstance(description, dict):
                description = description.get("_content", "")
            
            owner = photo.get("ownername", "")
            owner_id = photo.get("owner", "")
            photo_id = photo.get("id", "")
            license_id = photo.get("license", "")
            
            page_url = f"https://www.flickr.com/photos/{owner_id}/{photo_id}"
            license_name = _get_license_name(license_id)
            
            # Compor crédito
            credit = f"{owner} (Flickr/{license_name})" if owner else f"Flickr/{license_name}"
            
            # Score baseado na posição
            score = 0.7 - (idx * 0.02)
            
            results.append({
                "url": img_url,
                "source": "flickr_geral",
                "author": owner or "Flickr",
                "license": license_name,
                "description": description[:200] if description else title,
                "score": max(0.4, score),
                "page_url": page_url,
                "flickr_id": photo_id,
                "credit": credit,
            })
        
        logger.info(f"[flickr_geral] Encontrados {len(results)} resultados")
        
    except requests.exceptions.Timeout:
        logger.warning("[flickr_geral] Timeout")
    except requests.exceptions.RequestException as e:
        logger.error(f"[flickr_geral] Erro de requisição: {e}")
    except Exception as e:
        logger.error(f"[flickr_geral] Erro inesperado: {e}")
    
    return results
