# -*- coding: utf-8 -*-

"""

MOTOR DE REDACAO MULTI-AGENTE - Brasileira.news

Arquitetura Modular: Alto Volume, Agrupamento Seletivo e Tagging Institucional vs Comercial.

"""



import feedparser

import requests

import json

import base64

import time

import re

import sys

import random

from openai import OpenAI



# Importar o banco de dados do catalogo mestre

from catalogo_fontes import CATALOGO_FONTES, MAPA_TAGS, ID_REDACAO



# ==========================================

# 1. CREDENCIAIS E CONFIGURACOES

# ==========================================

WP_URL = "https://brasileira.news/wp-json/wp/v2"

WP_USER = "iapublicador"

import os
from dotenv import load_dotenv

load_dotenv()

WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")



# --- PISCINAS DE CHAVES DO USUARIO ---

OPENAI_KEYS = [

    "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",

    "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",

    "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"

]



GROK_KEYS = [

    "xai-L2tfNb2q7Yz1YYOs2iVdUuKbKqsKIdtzOWjTC5VwrYgXROw1bTQxFHzRucwxiEfAgRUVBilVB4XbE521",

    "xai-o0YD4KYxMOywJsRKQ6myfWdEYljHpJ4EQbNWsYrvqWG5HJANKUWwCvZGr0HvJdcp2pcWyUsUvzI9X16e",

    "xai-ZoK92vQJKIwRLEI7pP3k0r0PMVH9QR7fUJwMz8umCHLQIrDYXMGb7gWYfpGlbrAqYo6kQckuyuYIbUtj"

]



GEMINI_KEYS = [

    "AIzaSyBo0KOZ0loKdZdkwDzoN7K9uRPPfRXwWEc",

    "AIzaSyCfxG4dJdxfyCshqPv-5Rt9L_ak39nhJwY",

    "AIzaSyAl1q2e9KfpmPZTIMlIxGdRF12kluNO-Q8"

]



# ==========================================

# 2. MOTOR GEMINI (VIA REST API PURA) - Para Triagem

# ==========================================

def chamar_gemini_rest(prompt, modelo="gemini-1.5-flash"):

    global GEMINI_KEYS

    tentativas = 0

    

    while tentativas < len(GEMINI_KEYS):

        chave_atual = GEMINI_KEYS[0]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={chave_atual}"

        headers = {'Content-Type': 'application/json'}

        payload = {

            "contents": [{"parts": [{"text": prompt}]}],

            "generationConfig": {"temperature": 0.1}

        }

        

        try:

            res = requests.post(url, headers=headers, json=payload, timeout=20)

            if res.status_code == 200:

                dados = res.json()

                return dados['candidates'][0]['content']['parts'][0]['text']

            else:

                GEMINI_KEYS.append(GEMINI_KEYS.pop(0))

                tentativas += 1

                time.sleep(2)

        except Exception as e:

            print(f"[ERRO API] Falha na comunicacao com Gemini: {e}")

            GEMINI_KEYS.append(GEMINI_KEYS.pop(0))

            tentativas += 1

            time.sleep(2)

            

    return None



# ==========================================

# 3. TRIAGEM (GEMINI VIA REST C/ FALLBACK OPENAI)

# ==========================================

def avaliar_relevancia(titulo, veiculo):

    global OPENAI_KEYS

    prompt = f"De 0 a 10, qual a relevancia jornalistica nacional/internacional desta noticia: '{titulo}' (Fonte: {veiculo}). Responda APENAS com o numero numerico."

    

    resposta_gemini = chamar_gemini_rest(prompt, "gemini-1.5-flash")

    if resposta_gemini:

        try:

            return int(re.search(r'\d+', resposta_gemini).group())

        except:

            pass

            

    tentativas_gpt = 0

    while tentativas_gpt < len(OPENAI_KEYS):

        try:

            cliente = OpenAI(api_key=OPENAI_KEYS[0])

            res = cliente.chat.completions.create(

                model="gpt-4.1-mini",

                messages=[{"role": "user", "content": prompt}],

                temperature=0.1

            )

            return int(re.search(r'\d+', res.choices[0].message.content).group())

        except Exception:

            OPENAI_KEYS.append(OPENAI_KEYS.pop(0))

            tentativas_gpt += 1

            time.sleep(1)

            

    return 5



# ==========================================

# 4. AGRUPAMENTO (MAXIMIZANDO VOLUME E CLASSIFICACAO CLARA)

# ==========================================

def agrupar_noticias(noticias_brutas):

    global OPENAI_KEYS

    print(f"[AGRUPAMENTO] A analisar {len(noticias_brutas)} manchetes (tentando gpt-4.1-mini)...")

    

    # Agora passamos o "tipo" de fonte explicitamente para a IA nao ter de adivinhar

    catalogo = json.dumps([{"id": n["id"], "titulo": n["titulo"], "veiculo": n["veiculo"], "tipo_fonte": n["tipo_fonte"]} for n in noticias_brutas], ensure_ascii=False)

    

    prompt = f"""Atue como Editor-Chefe. O seu objetivo principal e MAXIMIZAR O VOLUME de publicacoes.

    Analise a lista de artigos fornecida, prestando MUITA ATENCAO ao campo 'tipo_fonte', e siga estas regras:

    

    1. FONTES 'COMERCIAL/IMPRENSA': Agrupe estas noticias APENAS se falarem exatamente sobre o mesmo evento.

    2. FONTES 'OFICIAL/GOVERNO': Crie uma pauta EXCLUSIVA para cada uma. Elas sao despachos, editais ou dados publicos que NAO DEVEM ser misturados, a menos que sejam 100% identicos. 

    3. REGRA DE SOBREVIVENCIA: NENHUMA noticia da lista pode ser descartada. Toda noticia enviada (seja oficial ou comercial) DEVE retornar formando um grupo (mesmo que o grupo tenha apenas 1 ID).

    

    Retorne APENAS um objeto JSON valido neste formato ESTRITO: 

    {{"grupos": [ {{"tema": "Resumo do fato", "ids": ["id1", "id2"]}}, {{"tema": "Despacho Institucional (Isolado)", "ids": ["id3"]}} ]}}

    Dados: {catalogo}"""

    

    tentativas = 0

    while tentativas < len(OPENAI_KEYS):

        try:

            cliente = OpenAI(api_key=OPENAI_KEYS[0])

            res = cliente.chat.completions.create(

                model="gpt-4.1-mini", 

                messages=[{"role": "user", "content": prompt}], 

                response_format={"type": "json_object"}

            )

            

            texto_saida = res.choices[0].message.content.strip()

            marcador = chr(96) * 3

            if texto_saida.startswith(marcador + "json"): texto_saida = texto_saida[7:]

            elif texto_saida.startswith(marcador): texto_saida = texto_saida[3:]

            if texto_saida.endswith(marcador): texto_saida = texto_saida[:-3]

            

            dados = json.loads(texto_saida.strip())

            

            if "grupos" in dados: 

                print(f"[AGRUPAMENTO] Sucesso! Foram formadas {len(dados['grupos'])} pautas/materias exclusivas.")

                return dados["grupos"]

            else: 

                print("[AGRUPAMENTO] A IA retornou JSON mas sem a chave 'grupos'.")

                return []

        except Exception as e:

            print(f"[ERRO OpenAI Agrupamento] Chave falhou (Erro de Autenticacao/Saldo). Tentando proxima chave...")

            OPENAI_KEYS.append(OPENAI_KEYS.pop(0))

            tentativas += 1

            time.sleep(2)

            

    print("[AVISO] Todas chaves OpenAI falharam. Tentando agrupamento de resgate com Gemini...")

    resposta_gemini = chamar_gemini_rest(prompt + "\nIMPORTANT: RETURN ONLY VALID JSON WITHOUT MARKDOWN FORMATTING.", "gemini-1.5-flash")

    

    if resposta_gemini:

        try:

            texto_limpo = resposta_gemini.strip()

            marcador = chr(96) * 3

            if texto_limpo.startswith(marcador + "json"): texto_limpo = texto_limpo[7:]

            elif texto_limpo.startswith(marcador): texto_limpo = texto_limpo[3:]

            if texto_limpo.endswith(marcador): texto_limpo = texto_limpo[:-3]

            

            dados = json.loads(texto_limpo.strip())

            if "grupos" in dados: 

                print(f"[SUCESSO] Gemini formou {len(dados['grupos'])} pautas/materias!")

                return dados["grupos"]

        except Exception as e:

            print(f"[ERRO Gemini Agrupamento] Falha ao ler o formato JSON: {e}")

            

    return []



# ==========================================

# 5. REDACAO JORNALISTICA (GROK PRIMARIO)

# ==========================================

def redigir_materia(grupo, noticias_brutas):

    global GROK_KEYS, OPENAI_KEYS, GEMINI_KEYS

    if "ids" not in grupo: return None

        

    noticias_alvo = [n for n in noticias_brutas if n["id"] in grupo["ids"]]

    if not noticias_alvo: return None

    

    textos_fontes = "".join([f"\n- {n['veiculo']} ({n['tipo_fonte']}): {n['titulo']} | {n['resumo']}" for n in noticias_alvo])

    links_credito = "".join([f"<li><a href='{n['link']}' target='_blank' rel='nofollow'>Reportagem via {n['veiculo']}</a></li>" for n in noticias_alvo])

    

    prompt = f"""Aja como Redator-Chefe da Brasileira.news. Escreva uma materia consolidando as fontes abaixo. De credito natural no texto (ex: "Segundo o portal...").

    Crie um prompt em ingles para foto realista. Escolha as Tags adequadas ({MAPA_TAGS}).

    FONTES: {textos_fontes}

    

    Responda APENAS com um JSON valido, sem formatacao markdown, comecando exatamente com {{ e terminando com }}. Formato exigido:

    {{"titulo": "Manchete Limpa", "corpo": "<p>Texto HTML</p>", "prompt_img": "english prompt", "tags_extras": [ID1, ID2]}}"""



    print(f"[REDACAO] Escrevendo pauta '{grupo.get('tema', 'Sem titulo')}'...")

    tentativas_grok = 0

    while tentativas_grok < len(GROK_KEYS):

        try:

            cliente_grok = OpenAI(api_key=GROK_KEYS[0], base_url="https://api.x.ai/v1")

            res = cliente_grok.chat.completions.create(

                model="grok-4-1-fast-non-reasoning",

                messages=[{"role": "user", "content": prompt}],

                temperature=0.3

            )

            

            texto_limpo = res.choices[0].message.content.strip()

            marcador = chr(96) * 3

            if texto_limpo.startswith(marcador + "json"): texto_limpo = texto_limpo[7:]

            elif texto_limpo.startswith(marcador): texto_limpo = texto_limpo[3:]

            if texto_limpo.endswith(marcador): texto_limpo = texto_limpo[:-3]

            

            dados = json.loads(texto_limpo.strip())

            dados["corpo"] += f"<hr><h4>Fontes consultadas:</h4><ul>{links_credito}</ul>"

            return dados

        except Exception as e:

            GROK_KEYS.append(GROK_KEYS.pop(0))

            tentativas_grok += 1

            

    print("[AVISO] Grok indisponivel ou esgotado. Redigindo com OpenAI (GPT-4o)...")

    tentativas_gpt = 0

    while tentativas_gpt < len(OPENAI_KEYS):

        try:

            cliente = OpenAI(api_key=OPENAI_KEYS[0])

            res = cliente.chat.completions.create(model="gpt-4.1", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})

            dados = json.loads(res.choices[0].message.content)

            dados["corpo"] += f"<hr><h4>Fontes consultadas:</h4><ul>{links_credito}</ul>"

            return dados

        except Exception as e:

            OPENAI_KEYS.append(OPENAI_KEYS.pop(0))

            tentativas_gpt += 1

            

    print("[AVISO] OpenAI indisponivel. Redigindo com Gemini (Ultimo Recurso)...")

    resposta_gemini = chamar_gemini_rest(prompt + "\nRETURN ONLY VALID JSON WITHOUT MARKDOWN BLOCKS.", "gemini-1.5-flash")

    if resposta_gemini:

        try:

            texto_limpo = resposta_gemini.strip()

            marcador = chr(96) * 3

            if texto_limpo.startswith(marcador + "json"):

                texto_limpo = texto_limpo[7:]

            elif texto_limpo.startswith(marcador):

                texto_limpo = texto_limpo[3:]

            if texto_limpo.endswith(marcador):

                texto_limpo = texto_limpo[:-3]

                

            dados = json.loads(texto_limpo.strip())

            dados["corpo"] += f"<hr><h4>Fontes consultadas:</h4><ul>{links_credito}</ul>"

            return dados

        except Exception as e:

            pass



    print("[ERRO] Falha Critica: Todos os motores falharam na redacao.")

    return None



# ==========================================

# 6. GERACAO DE IMAGEM E WP

# ==========================================

def gerar_imagem(prompt_imagem):
    return None # [TRAVA EDITORIAL - DALL-E 3 DESATIVADO]


    global OPENAI_KEYS

    print("[IMAGEM] A gerar capa com DALL-E 3...")

    prompt_final = f"Editorial news photography, highly professional, 8k. {prompt_imagem} - No text, no letters, no words."

    tentativas = 0

    while tentativas < len(OPENAI_KEYS):

        try:

            cliente = OpenAI(api_key=OPENAI_KEYS[0])

            res = cliente.images.generate(model="dall-e-3", prompt=prompt_final, size="1024x1024", n=1)

            return requests.get(res.data[0].url).content

        except Exception as e:

            OPENAI_KEYS.append(OPENAI_KEYS.pop(0))

            tentativas += 1

    

    print("[AVISO] DALL-E falhou. A materia sera publicada sem imagem.")

    return None



def enviar_imagem_wp(img_bytes, auth_headers):

    if not img_bytes: return None

    headers = auth_headers.copy()

    headers.update({'Content-Disposition': 'attachment; filename="destaque.jpg"', 'Content-Type': 'image/jpeg'})

    res = requests.post(f"{WP_URL}/media", headers=headers, data=img_bytes)

    return res.json().get('id') if res.status_code == 201 else None



def publicar_no_wordpress(materia, cat_id):

    print(f"[WORDPRESS] A publicar noticia ao vivo: '{materia['titulo']}'...")

    token = base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()

    auth_headers = {'Authorization': f'Basic {token}'}

    

    id_img = enviar_imagem_wp(gerar_imagem(materia["prompt_img"]), auth_headers)

    todas_categorias = [cat_id] + materia.get("tags_extras", [])

    

    payload = {

        'title': materia['titulo'],

        'content': materia['corpo'],

        'status': 'publish', 

        'categories': todas_categorias,

        'author': ID_REDACAO

    }

    if id_img: payload['featured_media'] = id_img

        

    res = requests.post(f"{WP_URL}/posts", json=payload, headers=auth_headers)

    if res.status_code == 201:

        print("[SUCESSO] Materia publicada com sucesso no site!\n")

    else:

        print(f"[ERRO] Falha no WP: {res.text}\n")



# ==========================================

# FLUXO PRINCIPAL

# ==========================================

def classificar_tipo_fonte(url):

    """Classifica mecanicamente se a fonte e governamental/institucional ou de imprensa comercial baseada na URL."""

    dominio = url.lower()

    # Identificadores publicos tipicos no Brasil

    marcadores_oficiais = ['.gov.br', '.jus.br', '.leg.br', '.mp.br', 'agenciabrasil']

    if any(marcador in dominio for marcador in marcadores_oficiais):

        return "OFICIAL/GOVERNO"

    return "COMERCIAL/IMPRENSA"



def executar_redacao_segura(caderno):

    if caderno not in CATALOGO_FONTES:

        print(f"[ERRO] A gaveta '{caderno}' nao existe no catalogo.")

        print(f"[DICA] Opcoes disponiveis: {', '.join(CATALOGO_FONTES.keys())}")

        return



    fontes_do_caderno = CATALOGO_FONTES[caderno]

    print(f"=== INICIANDO MOTOR (ALTO VOLUME): {caderno.upper()} ({len(fontes_do_caderno)} fontes) ===")

    

    noticias_avaliadas = []

    

    for idx, fonte in enumerate(fontes_do_caderno):

        print(f"Lendo feed: {fonte['nome']}...")

        

        # Etiquetagem explicita da fonte

        tipo = classificar_tipo_fonte(fonte['url'])

        

        try:

            feed = feedparser.parse(fonte['url'])

            # Lendo mais entradas por feed (aumentado de 3 para 5) para gerar mais volume

            for i, entry in enumerate(feed.entries[:5]): 

                nota = avaliar_relevancia(entry.title, fonte['nome'])

                noticias_avaliadas.append({

                    "nota": nota, "id": f"{idx}_{i}", "veiculo": fonte['nome'], 

                    "tipo_fonte": tipo, # <-- A MAGIA ACONTECE AQUI

                    "titulo": entry.title, "resumo": re.sub('<[^<]+?>', '', entry.description), 

                    "link": entry.link, "cat_id": fonte["cat_id"]

                })

            time.sleep(1)

        except Exception:

            pass



    if not noticias_avaliadas: return print("[AVISO] Nenhuma noticia encontrada nos feeds.")

    

    # Ordena as melhores e baixa a nota de corte para 6 (aumentando o volume de captacao)

    noticias_avaliadas.sort(key=lambda x: x['nota'], reverse=True)

    noticias_aprovadas = [n for n in noticias_avaliadas if n['nota'] >= 6]

    

    if not noticias_aprovadas:

        print("[AVISO] Nenhuma noticia nivel 6+. Selecionando o Top 5 do momento...")

        noticias_aprovadas = noticias_avaliadas[:5]

    else:

        # Teto maximo de processamento por ciclo subiu para 15 materias!

        noticias_aprovadas = noticias_aprovadas[:15]



    print(f"[PROCESSAMENTO] {len(noticias_aprovadas)} noticias enviadas para triagem.")

    

    grupos = agrupar_noticias(noticias_aprovadas)

    

    if not grupos:

        print("[AVISO] A IA nao devolveu pautas validas. Encerrando ciclo.")

    

    for grupo in grupos:

        materia = redigir_materia(grupo, noticias_aprovadas)

        if materia:

            ref = next((n for n in noticias_aprovadas if n['id'] in grupo['ids']), None)

            if ref:

                publicar_no_wordpress(materia, ref["cat_id"])

                time.sleep(2)

            

    print(f"=== FIM DO CICLO: {caderno.upper()} ===")



if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("[ERRO] Faltou escolher a gaveta de noticias!")

        print("Exemplo de uso: python3 motor_avancado.py ministerios_autarquias")

    else:

        caderno_escolhido = sys.argv[1].lower()

        executar_redacao_segura(caderno_escolhido)
