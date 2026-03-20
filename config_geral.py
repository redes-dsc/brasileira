
# -*- coding: utf-8 -*-

"""

CONFIGURAÇÕES GERAIS E GLOBAIS - Brasileira.news

Centraliza credenciais e URLs para fácil manutenção.

"""

import os
from dotenv import load_dotenv

# Carregar o .env
load_dotenv()

WP_URL = "https://brasileira.news/wp-json/wp/v2"

WP_USER = "iapublicador"

WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")



# Gera o cabeçalho de autenticação usado em todas as requisições ao WordPress

AUTH_HEADERS = {

    'Authorization': f'Basic {base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()}'

}

