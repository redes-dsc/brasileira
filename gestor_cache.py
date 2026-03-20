
# -*- coding: utf-8 -*-

"""

GESTOR DE CACHE - Brasileira.news

Impede a publicação duplicada de notícias já processadas.

"""

import os



ARQUIVO_CACHE = "historico_links.txt"



def carregar_cache():

    """Carrega os links já processados para a memória."""

    try:

        with open(ARQUIVO_CACHE, "r", encoding="utf-8") as f:

            return set(linha.strip() for linha in f if linha.strip())

    except FileNotFoundError:

        return set()



def salvar_no_cache(url):

    """Salva um novo link processado no histórico."""

    with open(ARQUIVO_CACHE, "a", encoding="utf-8") as f:

        f.write(f"{url}\n")

