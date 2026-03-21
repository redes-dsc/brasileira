
# -*- coding: utf-8 -*-

import requests

from config_geral import WP_URL, AUTH_HEADERS



def listar_autores():

    print("\n=== TENTATIVA 1: MODO ADMINISTRADOR ===")

    res1 = requests.get(f"{WP_URL}/users?per_page=100&context=edit", headers=AUTH_HEADERS)

    

    if res1.status_code == 200 and len(res1.json()) > 0:

        usuarios = res1.json()

        print(f"✅ SUCESSO! O seu robo agora tem permissao maxima.")

        print(f"Total encontrado: {len(usuarios)} autores\n")

        for u in usuarios:

            print(f"ID: {u['id']:<4} | Nome: {u['name']:<25} | Slug: {u['slug']}")

        return

        

    print("❌ Falhou. O WP escondeu a lista (Usuario sem permissao de Administrador).")

    

    print("\n=== TENTATIVA 2: MODO PUBLICO (Apenas autores com posts) ===")

    res2 = requests.get(f"{WP_URL}/users?per_page=100", headers=AUTH_HEADERS)

    

    if res2.status_code == 200 and len(res2.json()) > 0:

        usuarios = res2.json()

        print(f"⚠️ AVISO: Mostrando apenas quem ja tem posts publicados.")

        print(f"Total encontrado: {len(usuarios)} autores\n")

        for u in usuarios:

            print(f"ID: {u['id']:<4} | Nome: {u['name']:<25} | Slug: {u['slug']}")

    else:

        print("❌ 0 autores encontrados tambem no modo publico.")



if __name__ == "__main__":

    listar_autores()

