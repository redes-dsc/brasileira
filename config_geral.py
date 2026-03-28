
# -*- coding: utf-8 -*-

"""

CONFIGURAÇÕES GERAIS E GLOBAIS - Brasileira.news

Centraliza credenciais e URLs para fácil manutenção.

"""

import os
import base64
from dotenv import load_dotenv

# Carregar o .env
load_dotenv()

_base = os.getenv("WP_URL", "https://brasileira.news").rstrip('/')
if not _base.endswith("/wp-json/wp/v2"):
    WP_URL = f"{_base}/wp-json/wp/v2"
else:
    WP_URL = _base

WP_USER = os.getenv("WP_USER", "iapublicador")

WP_APP_PASSWORD = os.getenv("WP_APP_PASS")



# Gera o cabeçalho de autenticação usado em todas as requisições ao WordPress

AUTH_HEADERS = {

    'Authorization': f'Basic {base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()}'

}

