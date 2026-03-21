
# -*- coding: utf-8 -*-

"""

ROTEADOR UNIVERSAL MULTI-IA - Brasileira.news

Gerencia a comunicação com OpenAI, Anthropic, xAI, Gemini e Perplexity com fallback automático.

"""

import json

import time

import requests

from openai import OpenAI

from config_chaves import POOL_CHAVES



def roteador_ia_texto(system_prompt, user_prompt):

    TEMPERATURA = 0.3 

    

    for tentativa, config in enumerate(POOL_CHAVES):

        tipo = config["tipo"]

        chave = config["chave"]

        print(f"[ROTEADOR IA] Tentativa {tentativa + 1}/{len(POOL_CHAVES)} via {tipo.upper()}...")

        

        try:

            texto_saida = ""

            if tipo in ["openai", "grok", "perplexity"]:

                base_url = None

                modelo = "gpt-4.1"

                if tipo == "grok":

                    base_url = "https://api.x.ai/v1"

                    modelo = "grok-4.20-0309-non-reasoning"

                elif tipo == "perplexity":

                    base_url = "https://api.perplexity.ai"

                    modelo = "llama-3.1-sonar-large-128k-chat"



                cliente = OpenAI(api_key=chave, base_url=base_url)

                kwargs = dict(
                    model=modelo, 
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt + "\n\nRetorne OBRIGATORIAMENTE um JSON valido."}
                    ], 
                    temperature=TEMPERATURA, timeout=60
                )
                # response_format só para OpenAI (bug 9.4)
                if tipo == "openai":
                    kwargs["response_format"] = {"type": "json_object"}
                
                res = cliente.chat.completions.create(**kwargs)

                texto_saida = res.choices[0].message.content

                

            elif tipo == "anthropic":

                headers = {"x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"}

                payload = {

                    "model": "claude-sonnet-4-6",

                    "system": system_prompt,

                    "max_tokens": 4000,

                    "temperature": TEMPERATURA,

                    "messages": [{"role": "user", "content": user_prompt + "\n\nRetorne OBRIGATORIAMENTE APENAS um JSON valido puro."}]

                }

                res = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)

                res.raise_for_status()

                texto_saida = res.json()['content'][0]['text']

                

            elif tipo == "gemini":

                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={chave}"

                payload = {

                    "systemInstruction": {"parts": [{"text": system_prompt}]},

                    "contents": [{"parts":[{"text": user_prompt + "\n\nRetorne OBRIGATORIAMENTE APENAS um JSON valido puro."}]}],

                    "generationConfig": {"temperature": TEMPERATURA}

                }

                res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=60)

                res.raise_for_status()

                texto_saida = res.json()['candidates'][0]['content']['parts'][0]['text']



            texto_limpo = texto_saida.replace('```json', '').replace('```', '').strip()

            json.loads(texto_limpo) 

            return texto_limpo

            

        except Exception as e:

            print(f"[-X-] Erro no motor {tipo.upper()}: {str(e)[:80]}...")

            if tentativa < len(POOL_CHAVES) - 1:

                print("      -> Roteando para a proxima empresa em 2 segundos...")

                time.sleep(2)

            else:

                print("[ERRO FATAL IA] Todos os motores e chaves falharam!")

                return None



def roteador_ia_imagem(prompt_imagem):
    """
    [DESATIVADO] Geração de imagens por IA está permanentemente desativada.
    O pipeline de imagens usa curador_imagens_unificado.py com fontes reais.
    """
    return None

