# -*- coding: utf-8 -*-
"""
MEMÓRIA EDITORIAL - Brasileira.news

Rastreia temas e tópicos publicados para fornecer contexto editorial
entre ciclos. Permite que os agentes saibam o que já foi publicado.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from difflib import SequenceMatcher

MEMORY_FILE = Path("/home/bitnami/memoria_editorial.json")
MAX_ENTRIES = 500
SIMILARITY_THRESHOLD = 0.6

def _load_memory():
    if not MEMORY_FILE.exists():
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_memory(entries):
    try:
        # Manter apenas os mais recentes
        if len(entries) > MAX_ENTRIES:
            entries = entries[-MAX_ENTRIES:]
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[MEMORIA] Erro ao salvar: {e}")

def registrar_publicacao(titulo, categoria, fonte="", post_id=None):
    """Registra que um artigo foi publicado."""
    entries = _load_memory()
    entries.append({
        "titulo": titulo,
        "categoria": categoria,
        "fonte": fonte,
        "post_id": post_id,
        "timestamp": datetime.now().isoformat(),
    })
    _save_memory(entries)

def tema_ja_coberto(titulo, horas=6):
    """Verifica se um tema similar já foi coberto nas últimas N horas."""
    entries = _load_memory()
    cutoff = datetime.now() - timedelta(hours=horas)
    
    for entry in reversed(entries):
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts < cutoff:
                break  # Entradas mais antigas que o cutoff
            
            ratio = SequenceMatcher(None, titulo.lower(), entry["titulo"].lower()).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                return True, entry
        except Exception:
            continue
    
    return False, None

def cobertura_por_categoria(horas=24):
    """Retorna contagem de publicações por categoria nas últimas N horas."""
    entries = _load_memory()
    cutoff = datetime.now() - timedelta(hours=horas)
    contagem = {}
    
    for entry in entries:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= cutoff:
                cat = entry.get("categoria", "sem_categoria")
                contagem[cat] = contagem.get(cat, 0) + 1
        except Exception:
            continue
    
    return contagem

def categorias_com_gap(horas=12, min_cobertura=2):
    """Identifica categorias com pouca ou nenhuma cobertura recente."""
    cobertura = cobertura_por_categoria(horas)
    todas_categorias = [
        "Política", "Economia", "Tecnologia", "Saúde",
        "Internacional", "Esportes", "Meio Ambiente", "Justiça",
        "Cultura", "Sociedade", "Infraestrutura",
    ]
    gaps = []
    for cat in todas_categorias:
        if cobertura.get(cat, 0) < min_cobertura:
            gaps.append((cat, cobertura.get(cat, 0)))
    return gaps

# =====================================================================
# CATÁLOGO DE IMAGENS (Anti-Repetição)
# =====================================================================

IMAGE_CATALOG_FILE = Path("/home/bitnami/catalogo_imagens.json")
MAX_IMAGE_ENTRIES = 1000

def _load_image_catalog():
    if not IMAGE_CATALOG_FILE.exists():
        return []
    try:
        with open(IMAGE_CATALOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_image_catalog(entries):
    try:
        if len(entries) > MAX_IMAGE_ENTRIES:
            entries = entries[-MAX_IMAGE_ENTRIES:]
        with open(IMAGE_CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CATALOGO_IMG] Erro ao salvar: {e}")

def registrar_imagem(url, titulo="", media_id=None, fonte_tier=""):
    """Registra uma imagem publicada no catálogo."""
    entries = _load_image_catalog()
    entries.append({
        "url": url,
        "titulo": titulo,
        "media_id": media_id,
        "fonte_tier": fonte_tier,
        "timestamp": datetime.now().isoformat(),
    })
    _save_image_catalog(entries)

def imagem_ja_usada(url, horas=72):
    """Verifica se uma imagem já foi usada nas últimas N horas."""
    if not url:
        return False
    entries = _load_image_catalog()
    cutoff = datetime.now() - timedelta(hours=horas)
    
    # Normalizar URL (remover query params desnecessários)
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    url_clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    
    for entry in reversed(entries):
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts < cutoff:
                break
            entry_parsed = urlparse(entry.get("url", ""))
            entry_clean = urlunparse((entry_parsed.scheme, entry_parsed.netloc, entry_parsed.path, "", "", ""))
            if url_clean == entry_clean:
                return True
        except Exception:
            continue
    
    return False

