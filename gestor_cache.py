
# -*- coding: utf-8 -*-

"""

GESTOR DE CACHE - Brasileira.news

Impede a publicação duplicada de notícias já processadas.

"""

import os
import fcntl

ARQUIVO_CACHE = "/home/bitnami/historico_links.txt"



def carregar_cache():

    """Carrega os links já processados para a memória."""

    try:

        with open(ARQUIVO_CACHE, "r", encoding="utf-8") as f:

            return set(linha.strip() for linha in f if linha.strip())

    except FileNotFoundError:

        return set()



def salvar_no_cache(url):
    """Salva um novo link processado no histórico com rotação e lock seguro (limite 5000)."""
    links = []
    
    if os.path.exists(ARQUIVO_CACHE):
        with open(ARQUIVO_CACHE, "r", encoding="utf-8") as f:
            links = [l.strip() for l in f if l.strip()]
    
    if url not in links:
        links.append(url)
    
    if len(links) > 7000:
        links = links[-5000:]
    
    with open(ARQUIVO_CACHE, "w", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            for link in links:
                f.write(f"{link}\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
