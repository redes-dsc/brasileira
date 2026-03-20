# -*- coding: utf-8 -*-

"""

MOTOR DE SCRAPERS (RAIA 2) - Brasileira.news

Orquestra a raspagem, extracao profunda, IA e publicacao para fontes SEM RSS.

"""

import sys

import time

import json

from datetime import datetime



from gestor_cache import carregar_cache, salvar_no_cache

from extrator_conteudo import extrair_texto_completo

from roteador_ia import roteador_ia_texto

from gestor_wp import obter_autor_id_exato, publicar_no_wordpress

from regras_editoriais import obter_diretrizes_redacao

from regras_seo import obter_diretrizes_seo

from regras_arte import obter_diretrizes_arte



from scrapers_nativos import coletar_links_scraper

from catalogo_scrapers import CATALOGO_SCRAPERS



def redigir_noticia_profunda(noticia_bruta):

    print(f"\n[LEITURA PROFUNDA] Extracao de: {noticia_bruta['link']}")

    

    texto_full = extrair_texto_completo(noticia_bruta['link'])

    tamanho_fonte = len(texto_full)

    

    if tamanho_fonte < 400: 

        print("[AVISO] Extrator detectou texto curto. Adaptando para nota.")

        instrucao_tamanho = "Redija uma NOTA jornalistica direta e objetiva."

        instrucao_aspas = "NAO USE ASPAS e NAO INVENTE declaracoes."

    else:

        instrucao_tamanho = "Produza uma REPORTAGEM COMPLETA e aprofundada."

        instrucao_aspas = "E OBRIGATORIO utilizar as aspas diretas originais em <blockquote>."

        

    system_prompt = f"""Voce e o Editor-Chefe Senior do Brasileira.news.

REGRA DE OURO: NAO invente fatos, aspas ou nomes. Aja como reescritor/tradutor.

{obter_diretrizes_redacao()}

{obter_diretrizes_seo()}

{obter_diretrizes_arte()}"""



    user_prompt = f"""INSTRUCOES DA PAUTA:

1. IDIOMA: Portugues do Brasil.

2. PROFUNDIDADE: {instrucao_tamanho}

3. CITACOES: {instrucao_aspas}

Credito obrigatorio no final: Fonte original: {noticia_bruta['link']}



=== TEXTO BRUTO ({noticia_bruta['veiculo']}) ===

{texto_full}"""

    

    texto_saida = roteador_ia_texto(system_prompt, user_prompt)

    if not texto_saida: return None

        

    try:

        dados = json.loads(texto_saida)

        dados["_link_original"] = noticia_bruta['link'] 

        return dados

    except Exception as e:

        print(f"[ERRO JSON FATAL] IA nao devolveu um JSON valido: {e}")

        return None



def executar_ciclo_scraper(gaveta):

    if gaveta not in CATALOGO_SCRAPERS:

        print(f"[ERRO] Gaveta '{gaveta}' nao existe no catalogo_scrapers.py.")

        return

        

    print(f"=== INICIANDO RAIA 2 (SCRAPERS): {gaveta.upper()} ===")

    links_processados = carregar_cache()

    

    for fonte in CATALOGO_SCRAPERS[gaveta]:

        print(f"\n[RAIA 2] Iniciando Scraper: {fonte['nome']}...")

        

        lista_links = coletar_links_scraper(fonte['tipo_molde'], fonte['nome'], fonte['url'])

        noticias_selecionadas = 0

        

        for item in lista_links:

            if noticias_selecionadas >= 2: break

            if item['link'] in links_processados:

                print(f"  -> [CACHE] Ignorando (ja processada): {item['titulo'][:30]}...")

                continue

                

            noticia_bruta = {

                "veiculo": item['veiculo'],

                "link": item['link'],

                "cat_id": fonte['cat_id']

            }

            

            autor_id = obter_autor_id_exato(fonte['nome'])

            materia_pronta = redigir_noticia_profunda(noticia_bruta)

            

            if materia_pronta:

                publicar_no_wordpress(materia_pronta, autor_id, noticia_bruta['cat_id'], fonte['nome'])

                salvar_no_cache(noticia_bruta['link'])

                links_processados.add(noticia_bruta['link'])

                time.sleep(3)

                noticias_selecionadas += 1



if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("Uso correto: python3 motor_scrapers.py [nome_da_gaveta_scraper]")

    else:

        executar_ciclo_scraper(sys.argv[1].lower())
