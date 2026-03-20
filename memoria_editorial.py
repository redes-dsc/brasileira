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

def _text_to_embedding(text: str) -> list[float]:
    """
    Gera embedding lightweight via TF-IDF simplificado (sem dependência externa).
    Vetor de 64 dimensões normalizado para cosseno rápido.
    """
    import hashlib, math
    text = text.lower().strip()
    words = text.split()
    vec = [0.0] * 64
    for word in words:
        # Hash determinístico da palavra → posição no vetor
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        idx = h % 64
        vec[idx] += 1.0
    # Normalizar L2
    norm = math.sqrt(sum(v*v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosseno entre dois vetores normalizados."""
    return sum(x*y for x, y in zip(a, b))

def registrar_imagem(url, titulo="", media_id=None, fonte_tier=""):
    """Registra uma imagem publicada no catálogo com embedding do título."""
    entries = _load_image_catalog()
    embedding = _text_to_embedding(titulo) if titulo else []
    entries.append({
        "url": url,
        "titulo": titulo,
        "media_id": media_id,
        "fonte_tier": fonte_tier,
        "embedding": embedding,
        "timestamp": datetime.now().isoformat(),
    })
    _save_image_catalog(entries)

def imagem_ja_usada(url, horas=72):
    """Verifica se uma imagem já foi usada nas últimas N horas."""
    if not url:
        return False
    entries = _load_image_catalog()
    cutoff = datetime.now() - timedelta(hours=horas)
    
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

def buscar_imagem_similar(titulo: str, limite_similaridade: float = 0.7, horas: int = 168) -> dict | None:
    """
    Busca no catálogo uma imagem publicada com título similar (via embedding).
    Retorna a entrada do catálogo mais similar ou None.
    Útil para reusar imagens de notícias do mesmo tema.
    """
    if not titulo:
        return None
    
    entries = _load_image_catalog()
    if not entries:
        return None
    
    cutoff = datetime.now() - timedelta(hours=horas)
    query_emb = _text_to_embedding(titulo)
    
    melhor_score = 0.0
    melhor_entry = None
    
    for entry in reversed(entries):
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts < cutoff:
                break
            entry_emb = entry.get("embedding", [])
            if not entry_emb or len(entry_emb) != 64:
                continue
            score = _cosine_similarity(query_emb, entry_emb)
            if score > melhor_score and score >= limite_similaridade:
                melhor_score = score
                melhor_entry = entry
        except Exception:
            continue
    
    if melhor_entry:
        print(f"[CATALOGO_IMG] Imagem similar encontrada (score={melhor_score:.2f}): {melhor_entry.get('titulo', '')[:50]}")
    
    return melhor_entry

