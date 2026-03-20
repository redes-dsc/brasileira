
# -*- coding: utf-8 -*-

"""

MOTOR MESTRE (O MAESTRO) - Brasileira.news

Orquestra os sub-mÃ³dulos e processa os feeds inteligentemente.

"""

import sys

import time

import re

import json

import feedparser

from datetime import datetime, timedelta



from catalogo_fontes import CATALOGO_FONTES

from gestor_cache import carregar_cache, salvar_no_cache

from extrator_conteudo import extrair_texto_completo

from roteador_ia import roteador_ia_texto

from gestor_wp import obter_autor_id_exato, publicar_no_wordpress

from regras_editoriais import obter_diretrizes_redacao

from regras_seo import obter_diretrizes_seo

from regras_arte import obter_diretrizes_arte



def redigir_noticia_completa(noticia_bruta):

    print(f"\n[LEITURA PROFUNDA] Extracao de: {noticia_bruta['link']}")

    texto_full = extrair_texto_completo(noticia_bruta['link'])

    

    tamanho_fonte = len(texto_full)

    

    if tamanho_fonte < 400: 

        print("[AVISO] Extrator detectou texto curto ou bloqueado. Adaptando para nota jornalÃ­stica.")

        if tamanho_fonte < 150: texto_full = noticia_bruta['resumo']

        instrucao_tamanho = "O material base Ã© muito curto. Redija uma NOTA jornalÃ­stica direta e objetiva. NÃO alongue artificialmente o texto."

        instrucao_aspas = "3. CITAÃÃES: Como o texto base Ã© apenas um resumo, **NÃO USE ASPAS e NÃO INVENTE declaraÃ§Ãµes em nenhuma hipÃ³tese**."

    else:

        instrucao_tamanho = "O material base Ã© rico e extenso. VocÃª DEVE produzir uma REPORTAGEM COMPLETA, longa e aprofundada. Explore todas as nuances e o contexto apresentados."

        instrucao_aspas = "3. CITAÃÃES (CRÃTICO E RIGOROSO): Ã OBRIGATÃRIO buscar no texto e utilizar as aspas diretas originais (quando disponÃ­veis). Envolva-as em tags HTML `<blockquote>`. NUNCA invente uma fala fictÃ­cia."

        

    print(f"[REDACAO SENIOR] Material base possui {tamanho_fonte} caracteres.")

    

    system_prompt = f"""VocÃª Ã© o Editor-Chefe SÃªnior do portal Brasileira.news. 

Sua funÃ§Ã£o Ã© transformar feeds brutos em peÃ§as jornalÃ­sticas impecÃ¡veis, ricas e profundas, sempre em formato JSON.



í ½íº¨ REGRA DE OURO (TOLERÃNCIA ZERO PARA ALUCINAÃÃO):

- Ã ESTRITAMENTE PROIBIDO inventar fatos, dados, estatÃ­sticas, nomes ou acontecimentos.

- Atue APENAS como um reescritor/tradutor/editor de excelÃªncia do texto fornecido.

- Toda a informaÃ§Ã£o deve ter origem Ãºnica e exclusiva no texto original submetido.

    

=== REGRAS DIRETRIZES DE REDAÃÃO ===

{obter_diretrizes_redacao()}



=== DIRETRIZES DE SEO E FORMATACAO ===

{obter_diretrizes_seo()}



=== DIRETRIZES DE ARTE E IMAGENS ===

{obter_diretrizes_arte()}

"""



    user_prompt = f"""INSTRUÃÃES OBRIGATÃRIAS PARA ESTA PAUTA:

1. IDIOMA: PortuguÃªs do Brasil. Se o texto estiver em outro idioma, atue como repÃ³rter internacional e traduza o contexto com precisÃ£o.

2. PROFUNDIDADE: {instrucao_tamanho}

{instrucao_aspas}

4. ESTRUTURA: NÃ£o use "bullet points". Desenvolva parÃ¡grafos bem escritos com narrativa fluida.



CrÃ©dito obrigatÃ³rio no final da matÃ©ria: Fonte original: {noticia_bruta['link']}



=== TEXTO BRUTO OBTIDO DO VEÃCULO ({noticia_bruta['veiculo']}) ===

{texto_full}

"""

    

    texto_saida = roteador_ia_texto(system_prompt, user_prompt)

    if not texto_saida: return None

        

    try:

        dados_finais = json.loads(texto_saida)

        dados_finais["_link_original"] = noticia_bruta['link'] 

        return dados_finais

    except json.JSONDecodeError as e:

        print(f"[ERRO JSON] A IA nao devolveu um JSON valido: {e}")

        return None



def executar_ciclo(caderno):

    if caderno not in CATALOGO_FONTES: 

        return print(f"[ERRO] Caderno '{caderno}' inexistente no dicionario.")

    

    print(f"=== INICIANDO REDAÃÃO: {caderno.upper()} ===")

    agora = datetime.now()

    limite_dias = timedelta(days=7) 

    from deduplicador_unificado import link_ja_processado, registrar_processamento
    links_processados = carregar_cache()
    
    for fonte in CATALOGO_FONTES[caderno]:
        print(f"\n[RSS] Analisando Feed: {fonte['nome']}")
        try:
            feed = feedparser.parse(fonte['url'])
            noticias_selecionadas = 0
            for entry in feed.entries:
                if noticias_selecionadas >= 2: break 
                
                # Deduplicação unificada
                if link_ja_processado(entry.link, entry.title):
                    print(f"  -> [DEDUPLICADOR] Ignorando (já processado): {entry.title[:30]}...")
                    continue

                

                if hasattr(entry, 'published_parsed') and entry.published_parsed:

                    data_pub = datetime.fromtimestamp(time.mktime(entry.published_parsed))

                    if agora - data_pub > limite_dias:

                        print(f"  -> [DATA] Ignorando materia antiga ({data_pub.strftime('%d/%m/%Y')}): {entry.title[:30]}...")

                        continue

                

                noticia_bruta = {

                    "veiculo": fonte['nome'],

                    "titulo": entry.title,

                    "resumo": re.sub('<[^<]+?>', '', entry.description),

                    "link": entry.link,

                    "cat_id": fonte['cat_id'] 

                }

                

                autor_id = obter_autor_id_exato(fonte['nome'])

                materia_final = redigir_noticia_completa(noticia_bruta)

                

                if materia_final:
                    post_id = publicar_no_wordpress(materia_final, autor_id, noticia_bruta['cat_id'], fonte['nome'])
                    if post_id:
                        registrar_processamento(entry.link, post_id=post_id, feed_name=f"mestre_{caderno}")
                        noticias_selecionadas += 1

                    

        except Exception as e:

            print(f"[ERRO] Falha ao ler feed da fonte {fonte['nome']}: {e}")



if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("Uso correto: python3 motor_mestre.py [nome_da_gaveta]")

    else:

        executar_ciclo(sys.argv[1].lower())

