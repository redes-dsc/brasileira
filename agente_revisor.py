
# -*- coding: utf-8 -*-

"""

SUPER AGENTE REVISOR - Brasileira.news

Audita e corrige ativamente categorias, autores e falhas de redacao.

AGORA COM DETECCAO DINAMICA DE AUTORIA (A prova de erros).

"""

import requests

import json

import os

import re

import time

from config_geral import WP_URL, AUTH_HEADERS

from config_categorias import *



ARQUIVO_AUDITORIA = "controle_auditoria.json"



MAPA_UNIFICADO_AUTORES = {

    "agenciabrasil.ebc": 12, "radioagencianacional.ebc": 12, "ebc.com.br": 12,

    "camara.leg.br": 48, "senado.leg.br": 48,

    "gov.br/agricultura": 14, "gov.br/mcti": 16, "gov.br/cultura": 18, "gov.br/defesa": 44,

    "gov.br/mec": 23, "gov.br/fazenda": 26, "gov.br/gestao": 27, "gov.br/igualdaderacial": 28,

    "gov.br/justica": 30, "gov.br/mpa": 34, "gov.br/previdencia": 38, "gov.br/saude": 40,

    "gov.br/cidades": 15, "gov.br/mcom": 17, "gov.br/mulheres": 33, "gov.br/mre": 39,

    "gov.br/mme": 32, "gov.br/portos": 36, "gov.br/mda": 19, "gov.br/mds": 20, 

    "gov.br/mdic": 21, "gov.br/memp": 24, "gov.br/esportes": 25, "gov.br/mma": 31, 

    "gov.br/planejamento": 35, "gov.br/trabalho": 41, "gov.br/turismo": 43, 

    "gov.br/mdh": 22, "gov.br/povosindigenas": 37, "gov.br/transportes": 42,

    "stf.jus": 52, "stj.jus": 52, "cnj.jus": 52, "csjt.jus": 56, "cjf.jus": 57, 

    "mpf.mp": 58, "mpt.mp": 60, "agenciabrasilia": 124, "agenciapara": 131, 

    "agenciaac": 118, "agenciars": 140, "alagoas.al": 119, "agenciaminas": 128, 

    "aen.pr": 135, "ansabrasil": 154, "lusa.pt": 158, "angop.ao": 159, "inforpress.cv": 160

}



def carregar_controle():

    if os.path.exists(ARQUIVO_AUDITORIA):

        with open(ARQUIVO_AUDITORIA, "r", encoding="utf-8") as f: 

            return json.load(f)

    return {}



def salvar_controle(dados):

    with open(ARQUIVO_AUDITORIA, "w", encoding="utf-8") as f:

        json.dump(dados, f, indent=4, ensure_ascii=False)



def extrair_url_original(conteudo):

    m = re.search(r'<!-- URL_ORIGINAL:\s*(http[^ \n>]+)', conteudo)

    if m: return m.group(1).strip()

    links_html = re.findall(r'href=[\'"](https?://[^\'"]+)', conteudo)

    for link in reversed(links_html):

        l_low = link.lower()

        if "brasileira.news" not in l_low and "instagram.com" not in l_low and "twitter.com" not in l_low and "facebook.com" not in l_low and "youtube.com" not in l_low:

            return link.strip()

    urls_soltas = re.findall(r'(https?://[^\s<"\']+)', conteudo)

    for url in reversed(urls_soltas):

        u_low = url.lower()

        if "brasileira.news" not in u_low and not u_low.endswith(('.jpg', '.pdf', '.png')):

            return url.strip()

    return "Desconhecida"



def adivinhar_categoria(url, titulo, conteudo):

    url_l = url.lower(); tit = titulo.lower()

    

    if "ge.globo" in url_l or "lance" in url_l or "espn" in url_l or "esporte" in url_l or "futebol" in url_l: return CAT_ESPORTES

    if "tecmundo" in url_l or "canaltech" in url_l or "tecnoblog" in url_l: return CAT_TECNOLOGIA

    if "omelete" in url_l or "famosos" in url_l or "entretenimento" in url_l or "quem.globo" in url_l: return CAT_ENTRETENIMENTO

    if "economia" in url_l or "fazenda" in url_l or "infomoney" in url_l or "valor" in url_l: return CAT_ECONOMIA

    if "saude" in url_l or "ans.gov" in url_l: return CAT_SAUDE

    if "meio-ambiente" in url_l or "clima" in url_l or "wwf" in url_l or "ibama" in url_l: return CAT_MEIO_AMBIENTE

    if "justica" in url_l or "stf" in url_l or "stj" in url_l or "trt" in url_l or "tst" in url_l or "cnj" in url_l or "mpf" in url_l: return CAT_JUSTICA

    if "educacao" in url_l or "mec" in url_l or "capes" in url_l: return CAT_EDUCACAO

    if "internacional" in url_l or "reuters" in url_l or "aljazeera" in url_l or "bbc" in url_l or "rtp.pt" in url_l: return CAT_INTERNACIONAL

    

    if any(w in tit for w in ["futebol", "campeonato", "nba", "atleta", "olimpiada", "brasileirao", "libertadores", "gols", "copa"]): return CAT_ESPORTES

    if any(w in tit for w in ["tecnologia", "inteligencia artificial", "smartphone", "apple", "google", "microsoft", "app", "hacker", "ia"]): return CAT_TECNOLOGIA

    if any(w in tit for w in ["dolar", "bolsa", "mercado", "inflacao", "pib", "taxa selic", "imposto", "receita federal", "bc", "banco central"]): return CAT_ECONOMIA

    if any(w in tit for w in ["stf", "stj", "policia federal", "prisao", "juiz", "tribunal", "ministerio publico", "condenado", "justica"]): return CAT_JUSTICA

    if any(w in tit for w in ["hospital", "paciente", "vacina", "covid", "doenca", "saude", "medico", "sus", "ans"]): return CAT_SAUDE

    if any(w in tit for w in ["filme", "serie", "novela", "ator", "atriz", "cinema", "musica", "show", "cantor"]): return CAT_ENTRETENIMENTO

    if any(w in tit for w in ["desmatamento", "amazonia", "clima", "aquecimento global", "meio ambiente", "sustentabilidade", "ibama"]): return CAT_MEIO_AMBIENTE

    if any(w in tit for w in ["escola", "universidade", "aluno", "professor", "enem", "faculdade"]): return CAT_EDUCACAO

    

    if "agenciabrasil" in url_l or "camara.leg" in url_l or "senado" in url_l: return CAT_POLITICA

    return CAT_POLITICA



def diagnosticar_e_corrigir(url_orig, cat_atual, autor_atual, titulo, conteudo, id_oficial_redacao):

    url_l = url_orig.lower()

    correcoes = {}

    alertas = []

    

    try: autor_atual_int = int(autor_atual)

    except: autor_atual_int = 0

    cat_atual_ints = [int(c) for c in cat_atual] if isinstance(cat_atual, list) else []



    # 1. CORRECAO DE AUTORIA (Usando o ID oficial descoberto online)

    autor_correto = id_oficial_redacao

    for chave, id_autor in MAPA_UNIFICADO_AUTORES.items():

        if chave in url_l:

            autor_correto = id_autor

            break

            

    if autor_atual_int != autor_correto:

        correcoes['author'] = autor_correto

        

    # 2. CORRECAO DE CATEGORIAS

    cat_correta = adivinhar_categoria(url_orig, titulo, conteudo)

    lista_sug = cat_correta if isinstance(cat_correta, list) else [cat_correta]
    
    # Substituir apenas se estiver vazio ou categorizado em 'Uncategorized' (1)
    if not cat_atual_ints or (len(cat_atual_ints) == 1 and 1 in cat_atual_ints):
        correcoes['categories'] = lista_sug



    # 3. CORRECAO EDITORIAL NO TEXTO

    conteudo_novo = conteudo

    alterou_conteudo = False

    

    if url_orig != "Desconhecida":

        tem_link_visivel = "href=" in conteudo_novo.lower()

        tem_fonte_texto = "fonte" in conteudo_novo.lower()

        if not tem_link_visivel and not tem_fonte_texto:

            credito = f"\n<hr>\n<p><em><strong>Fonte original:</strong> <a href='{url_orig}' target='_blank' rel='noopener noreferrer'>Acessar materia</a></em></p>"

            conteudo_novo += credito

            alterou_conteudo = True

            

    if len(conteudo_novo) > 1500 and "blockquote" not in conteudo_novo:

        alertas.append("Aviso Interno: Texto longo sem aspas.")

        

    if alterou_conteudo:

        correcoes['content'] = conteudo_novo



    return correcoes, alertas



def executar_auditoria_continua():

    print("\n=======================================================")

    print("[*] SUPER AGENTE REVISOR INICIADO")

    print("=======================================================\n")

    

    print("[*] Contactando a API do WordPress para obter o ID oficial da Redacao...")

    res_me = requests.get(f"{WP_URL}/users/me", headers=AUTH_HEADERS)

    if res_me.status_code == 200:

        id_oficial_redacao = res_me.json().get('id')

        nome_redacao = res_me.json().get('name')

        print(f"   [OK] Conta confirmada: {nome_redacao} (ID: {id_oficial_redacao})\n")

    else:

        print("   [ERRO] Falha ao comunicar com o WP. Abortando seguranca.")

        return

    

    controle = carregar_controle()

    pagina = 1

    total_lidos = 0

    total_corrigidos = 0

    

    while pagina <= 25: # Hard limit para evitar max overhead na API
        res = requests.get(f"{WP_URL}/posts?per_page=50&page={pagina}", headers=AUTH_HEADERS)
        if res.status_code != 200: break

            

        posts = res.json()

        if not posts: break

        

        for post in posts:

            post_id = str(post['id'])

            total_lidos += 1

            

            if post_id in controle and controle[post_id].get("status") == "revisado_e_corrigido":

                continue 

                

            titulo = post.get('title', {}).get('rendered', 'Sem Titulo')

            conteudo = post.get('content', {}).get('rendered', '')

            cat_atual = post.get('categories', [])

            autor_atual = post.get('author')

            

            url_original = extrair_url_original(conteudo)

            

            correcoes, alertas = diagnosticar_e_corrigir(

                url_original, cat_atual, autor_atual, titulo, conteudo, id_oficial_redacao

            )

            

            if correcoes:

                print(f"[+] Lendo: {titulo[:45]}...")

                if 'author' in correcoes: print(f"   -> Forcando Autor para ID {correcoes['author']}")

                if 'categories' in correcoes: print(f"   -> Forcando Categorias para {correcoes['categories']}")

                if 'content' in correcoes: print(f"   -> Injetando link de fonte ausente.")

                

                upd_res = requests.post(f"{WP_URL}/posts/{post_id}", json=correcoes, headers=AUTH_HEADERS)

                if upd_res.status_code == 200:

                    print("   [OK] Materia alterada com sucesso!")

                    total_corrigidos += 1

                else:

                    print(f"   [ERRO] Falha ao alterar: {upd_res.text}")

                    alertas.append("ERRO_AO_ATUALIZAR")

            else:

                if alertas: print(f"[!] {titulo[:45]} | Info: {alertas[0]}")

                else: print(f"[OK] {titulo[:45]} | Perfeito.")

            

            status_final = "revisado_e_corrigido" if not alertas else "revisado_com_alertas"

            

            controle[post_id] = {

                "wp_id": post_id, "titulo": titulo, "url_original": url_original,

                "autor_final": correcoes.get('author', autor_atual),

                "categorias_finais": correcoes.get('categories', cat_atual),

                "alertas_redacao": alertas, "status": status_final,

                "ultima_verificacao": time.strftime("%Y-%m-%d %H:%M:%S")

            }

        # Salva o log apenas uma vez por página para evitar sobrecarga I/O massiva
        salvar_controle(controle)

        pagina += 1

        time.sleep(0.5)

        

    print("\n=======================================================")

    print(f"[*] RELATORIO FINAL: Lidos ({total_lidos}) | Corrigidos ({total_corrigidos})")

    print("=======================================================\n")



if __name__ == "__main__":

    executar_auditoria_continua()

