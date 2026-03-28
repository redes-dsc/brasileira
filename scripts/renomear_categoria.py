
# -*- coding: utf-8 -*-

"""

SCRIPT PARA RENOMEAR CATEGORIAS NO WORDPRESS

Altera o nome da categoria e atualiza automaticamente todos os posts associados.

"""



import os
import requests
import base64
from dotenv import load_dotenv

# Carregar o .env
load_dotenv()

WP_URL = "https://brasileira.news/wp-json/wp/v2"
WP_USER = "iapublicador"
WP_APP_PASSWORD = os.getenv("WP_APP_PASS")



auth_headers = {

    'Authorization': f'Basic {base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()}',

    'Content-Type': 'application/json'

}



def alterar_nome_categoria(nome_antigo, nome_novo, slug_novo):

    print(f"A procurar a categoria '{nome_antigo}' no WordPress...")

    

    # 1. Procurar a categoria pelo nome antigo

    res_busca = requests.get(f"{WP_URL}/categories?search={nome_antigo}", headers=auth_headers)

    

    if res_busca.status_code != 200:

        print(f"[ERRO] Falha ao aceder à API: {res_busca.text}")

        return



    categorias = res_busca.json()

    categoria_alvo = None

    

    for cat in categorias:

        if cat['name'].lower() == nome_antigo.lower():

            categoria_alvo = cat

            break



    if not categoria_alvo:

        print(f"[AVISO] Não foi encontrada nenhuma categoria com o nome exato '{nome_antigo}'.")

        print("Verifique se já não foi alterada ou se o nome está escrito de forma diferente.")

        return



    cat_id = categoria_alvo['id']

    print(f"[OK] Categoria '{nome_antigo}' encontrada com o ID: {cat_id}.")

    print(f"A alterar para '{nome_novo}'...")



    # 2. Atualizar a categoria com o novo nome e slug

    payload = {

        "name": nome_novo,

        "slug": slug_novo

    }

    

    res_update = requests.post(f"{WP_URL}/categories/{cat_id}", headers=auth_headers, json=payload)

    

    if res_update.status_code == 200:
        print(f"✅ Sucesso! A categoria foi renomeada para '{nome_novo}'.")
        print(f"Todos os posts ja publicados agora refletem a categoria {nome_novo}!")
    else:

        print(f"[ERRO] Falha ao atualizar a categoria: {res_update.text}")



if __name__ == "__main__":

    # Executa a função para trocar Continentes -> Internacional

    alterar_nome_categoria("Continentes", "Internacional", "internacional")

