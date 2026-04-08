#!/usr/bin/env python3
"""
Módulo de busca de imagens - Unsplash

Tier 11 no pipeline de busca de imagens (último recurso).
Busca imagens no Unsplash via API.
Licença: Unsplash License (livre para uso)
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Configurações
_UNSPLASH_ACCESS_KEY = None
UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"
TIMEOUT = 10
MAX_RESULTS = 10
LICENSE = "Unsplash License (livre para uso)"


def search(query: str, **kwargs) -> list[dict]:
    """
    Busca imagens no Unsplash.
    
    Args:
        query: Termo de busca
        **kwargs: Argumentos adicionais
            - orientation: 'landscape', 'portrait', 'squarish' (default: 'landscape')
            - color: filtro de cor (opcional)
    
    Returns:
        Lista de resultados com imagens do Unsplash
    """
    global _UNSPLASH_ACCESS_KEY
    if _UNSPLASH_ACCESS_KEY is None:
        _UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
    if not _UNSPLASH_ACCESS_KEY:
        logger.warning("[unsplash] UNSPLASH_ACCESS_KEY não configurada")
        return []
    
    if not query or not query.strip():
        return []
    
    orientation = kwargs.get("orientation", "landscape")
    
    results = []
    
    try:
        logger.info(f"[unsplash] Buscando: {query}")
        
        headers = {
            "Authorization": f"Client-ID {_UNSPLASH_ACCESS_KEY}"
        }
        
        params = {
            "query": query,
            "per_page": MAX_RESULTS,
            "orientation": orientation,
        }
        
        resp = requests.get(
            UNSPLASH_API_URL,
            params=params,
            headers=headers,
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        
        photos = data.get("results", [])
        
        for idx, photo in enumerate(photos):
            # Preferir imagens de boa resolução (regular = ~1080px)
            urls = photo.get("urls", {})
            img_url = urls.get("regular") or urls.get("full") or urls.get("raw", "")
            
            if not img_url:
                continue
            
            user = photo.get("user", {})
            photographer = user.get("name", "")
            photographer_username = user.get("username", "")
            
            links = photo.get("links", {})
            photo_url = links.get("html", "")
            
            alt_text = photo.get("alt_description", "")
            description = photo.get("description", "") or alt_text
            
            # Score baseado na posição (mais relevantes primeiro)
            score = 0.6 - (idx * 0.02)
            
            results.append({
                "url": img_url,
                "source": "unsplash",
                "author": f"{photographer} via Unsplash" if photographer else "Unsplash",
                "license": LICENSE,
                "description": description[:200] if description else alt_text,
                "score": max(0.35, score),
                "page_url": photo_url,
                "unsplash_id": photo.get("id"),
                "photographer_username": photographer_username,
                # Unsplash requer atribuição com link
                "attribution": f"Foto por {photographer} no Unsplash" if photographer else "Foto via Unsplash",
            })
        
        logger.info(f"[unsplash] Encontrados {len(results)} resultados")
        
    except requests.exceptions.Timeout:
        logger.warning("[unsplash] Timeout")
    except requests.exceptions.RequestException as e:
        logger.error(f"[unsplash] Erro de requisição: {e}")
    except Exception as e:
        logger.error(f"[unsplash] Erro inesperado: {e}")
    
    return results
