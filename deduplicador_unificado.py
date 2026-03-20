# -*- coding: utf-8 -*-
"""
DEDUPLICADOR UNIFICADO - Brasileira.news

Interface central para verificar se um link já foi processado/publicado,
consultando tanto o cache local (historico_links.txt) quanto o MariaDB (rss_control).
"""

import os
import sys
from pathlib import Path

# Adicionar paths necessários
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "motor_rss"))

try:
    from gestor_cache import carregar_cache, salvar_no_cache
except ImportError:
    # Fallback minimalista se gestor_cache não estiver acessível
    def carregar_cache(): return set()
    def salvar_no_cache(url): pass

try:
    import db
    HAS_DB = True
except ImportError:
    HAS_DB = False

def link_ja_processado(url, titulo=""):
    """
    Verifica se o link já foi processado em qualquer um dos sistemas.
    """
    # 1. Verificar Cache em Texto (Motor Mestre clássico)
    cache_texto = carregar_cache()
    if url in cache_texto:
        return True

    # 2. Verificar MariaDB (Motor RSS v2 e novos sistemas)
    if HAS_DB:
        try:
            if db.post_exists(url, titulo):
                return True
        except Exception:
            pass

    return False

def registrar_processamento(url, post_id=None, feed_name="unificado", llm_used=""):
    """
    Registra que um link foi processado em ambos os sistemas.
    """
    # Salvar no cache de texto
    salvar_no_cache(url)

    # Registrar no MariaDB se tivermos a conexão e o post_id
    if HAS_DB and post_id:
        try:
            db.register_published(post_id, url, feed_name, llm_used)
        except Exception:
            pass
