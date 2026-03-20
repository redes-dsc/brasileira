
# -*- coding: utf-8 -*-

import re



caminho = '/home/bitnami/gestor_wp.py'



with open(caminho, 'r', encoding='utf-8') as f:

    codigo = f.read()



# Limpa tentativas anteriores para evitar duplicacao

codigo = re.sub(r'\s*# --- RASPADOR DE IMAGEM REAL ---.*?# ------------------------------', '', codigo, flags=re.DOTALL)

codigo = re.sub(r'\s*# --- GARANTIA DE IMAGENS.*?# ------------------------------', '', codigo, flags=re.DOTALL)



# A Nova Lei Editorial de Imagens

bloco_garantia = """

    # --- GARANTIA DE IMAGENS (OFICIAL OU PLACEHOLDER) ---

    url_orig = None

    import re

    m_url = re.search(r'<!-- URL_ORIGINAL:\s*(http[^ \n>]+)', dados.get('content', ''))

    if m_url: url_orig = m_url.group(1).strip()



    def obter_id_placeholder(headers):

        try:

            import requests

            from config_geral import WP_URL

            res = requests.get(f"{WP_URL}/media?search=imagem-brasileira", headers=headers)

            if res.status_code == 200 and len(res.json()) > 0:

                return res.json()[0]['id']

        except: pass

        return 0



    id_imagem_final = 0



    if url_orig:

        # 1. RADAR: E uma fonte publica/oficial?

        dominios_oficiais = ['gov.br', 'leg.br', 'jus.br', 'mp.br', 'ebc.com.br', 'agenciabrasil']

        eh_oficial = any(d in url_orig.lower() for d in dominios_oficiais)



        if eh_oficial:

            print(f"   [*] Fonte PUBLICA detectada. Tentando extrair foto real...")

            try:

                id_raspado = buscar_e_subir_imagem_real(url_orig, auth_headers)

                if id_raspado:

                    id_imagem_final = id_raspado

                    print(f"   [OK] Foto oficial capturada! (WP ID: {id_imagem_final})")

                else:

                    print("   [INFO] Sem foto na fonte oficial. Recorrendo ao Placeholder.")

            except Exception:

                print("   [ERRO] Falha na extracao. Recorrendo ao Placeholder.")

        else:

            print("   [*] Fonte NAO-PUBLICA. Bloqueando extracao e aplicando Placeholder direto.")

    else:

        print("   [INFO] URL original desconhecida. Aplicando Placeholder de seguranca.")



    # 2. GARANTIA: Se chegou ate aqui sem foto (por erro ou por regra), crava o Placeholder

    if not id_imagem_final:

        id_imagem_final = obter_id_placeholder(auth_headers)

        if id_imagem_final:

            print(f"   [OK] Imagem Placeholder (imagem-brasileira.png) aplicada com sucesso.")



    if id_imagem_final:

        dados['featured_media'] = id_imagem_final

    # ------------------------------"""



padrao_func = r'(def\s+publicar_no_wordpress\s*\([^)]+\):)'

codigo = re.sub(padrao_func, r'\1\n' + bloco_garantia, codigo)



with open(caminho, 'w', encoding='utf-8') as f:

    f.write(codigo)



print("\n[SUCESSO] Lei de Garantia de Imagens aplicada no nucleo do WordPress!")

print("- Fontes governamentais (.gov.br, .jus.br, agenciabrasil) -> Tenta raspar a foto.")

print("- Se falhar ou for fonte privada -> Usa o Placeholder Brasileiro automaticamente.\n")

