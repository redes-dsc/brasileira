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
