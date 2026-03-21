
# -*- coding: utf-8 -*-

"""
ROTEADOR UNIVERSAL MULTI-IA - Brasileira.news

Delega para llm_router.call_llm() que gerencia 41 modelos em 7 providers
com fallback automático e distribuição de carga.

Mantém a interface roteador_ia_texto(system_prompt, user_prompt) para
compatibilidade com motor_scrapers.py, motor_mestre.py e agente_newspaper.py.
"""

import json
import sys
import os

# Adicionar motor_rss ao path para importar llm_router
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "motor_rss"))
import llm_router


def roteador_ia_texto(system_prompt, user_prompt):
    """
    Reescreve conteúdo via llm_router com cascata de 41 modelos.
    Usa TIER_PREMIUM (Tier 1) para obter máxima qualidade editorial.
    Retorna JSON string limpo ou None se todos falharem.
    """
    user_prompt_json = user_prompt + "\n\nRetorne OBRIGATORIAMENTE APENAS um JSON valido puro."

    try:
        result, provider_used = llm_router.call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt_json,
            tier=llm_router.TIER_PREMIUM,
        )

        if not result:
            print("[ERRO FATAL IA] llm_router retornou resultado vazio!")
            return None

        print(f"[ROTEADOR IA] Sucesso via {provider_used}")

        # Limpar markdown JSON se necessário
        texto_limpo = result.replace('```json', '').replace('```', '').strip()

        # Validar JSON
        json.loads(texto_limpo)

        return texto_limpo

    except json.JSONDecodeError as e:
        print(f"[-X-] JSON inválido do LLM: {str(e)[:80]}")
        return None
    except Exception as e:
        print(f"[ERRO FATAL IA] Todos os motores falharam: {str(e)[:80]}")
        return None


def roteador_ia_imagem(prompt_imagem):
    """
    [DESATIVADO] Geração de imagens por IA está permanentemente desativada.
    O pipeline de imagens usa curador_imagens_unificado.py com fontes reais.
    """
    return None
