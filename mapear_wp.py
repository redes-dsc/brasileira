
# -*- coding: utf-8 -*-

"""

MAPEADOR DE IDS DO WORDPRESS - Brasileira.news

Extrai a lista exata de Autores e Categorias para configurarmos o sistema.

"""

import requests

from config_geral import WP_URL, AUTH_HEADERS



def listar_dados_wp():

    print("=== MAPEAMENTO DE CATEGORIAS ===")

    res_cat = requests.get(f"{WP_URL}/categories?per_page=100", headers=AUTH_HEADERS)

    if res_cat.status_code == 200:

        for c in res_cat.json():

            print(f"ID: {c['id']:<4} | Nome: {c['name']}")

    else:

        print("Erro ao buscar categorias.")



    print("\n=== MAPEAMENTO DE AUTORES / USUARIOS ===")

    res_user = requests.get(f"{WP_URL}/users?per_page=100&context=edit", headers=AUTH_HEADERS)

    if res_user.status_code == 200:

        for u in res_user.json():

            # Trocada a variável "Nome Exibição" por algo sem acento para evitar erros no terminal

            print(f"ID: {u['id']:<4} | Nome: {u['name']:<20} | Slug: {u['slug']}")

    else:

        print("Erro ao buscar usuarios.")



if __name__ == "__main__":

    listar_dados_wp()

