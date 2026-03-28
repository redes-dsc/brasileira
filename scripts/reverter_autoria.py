
# -*- coding: utf-8 -*-

import requests, re

from config_geral import WP_URL, AUTH_HEADERS



print("\n=== SCRIPT DE EMERGENCIA: DEVOLVER PARA REDACAO ===")



res_me_json = requests.get(f"{WP_URL}/users/me", headers=AUTH_HEADERS).json()
id_redacao = res_me_json.get('id')
nome_redacao = res_me_json.get('name')

print(f"1. A verdadeira Redacao ({nome_redacao} - iapublicador) tem o ID: {id_redacao}")



caminho = '/home/bitnami/config_categorias.py'

try:

    with open(caminho, 'r', encoding='utf-8') as f: cont = f.read()

    with open(caminho, 'w', encoding='utf-8') as f: f.write(re.sub(r'ID_REDACAO\s*=\s*\d+', f'ID_REDACAO = {id_redacao}', cont))

    print("2. Arquivo de configuracao blindado com o ID correto!")

except: pass



id_tiago = 2

res_busca = requests.get(f"{WP_URL}/users?search=tiago", headers=AUTH_HEADERS)

if res_busca.status_code == 200 and len(res_busca.json()) > 0: 

    id_tiago = res_busca.json()[0]['id']



print(f"\n3. INICIANDO TRANSFERENCIA: Tirando do Tiago (ID {id_tiago}) e passando para {nome_redacao} (ID {id_redacao})...")



corrigidos = 0
page = 1
while True:
    res = requests.get(f"{WP_URL}/posts?author={id_tiago}&per_page=50&page={page}", headers=AUTH_HEADERS)
    if res.status_code != 200 or not res.json(): break
    
    posts_data = res.json()
    if not posts_data: break
    
    for p in posts_data:

        print(f"   -> Transferindo: {p['title']['rendered'][:40]}...")

        if requests.post(f"{WP_URL}/posts/{p['id']}", json={'author': id_redacao}, headers=AUTH_HEADERS).status_code == 200: 

            corrigidos += 1



print(f"\n=== FEITO! {corrigidos} materias foram devolvidas para a Redacao Brasileira. ===")

