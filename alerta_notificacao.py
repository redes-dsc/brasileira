# -*- coding: utf-8 -*-
"""
SISTEMA DE ALERTA E NOTIFICAÇÃO - Brasileira.news

Centraliza o envio de alertas críticos (ALERTA VERMELHO).
Pode ser estendido para Telegram, Slack, E-mail ou Webhooks.
"""

import logging
import os
import requests
from datetime import datetime

logger = logging.getLogger("alerta_brasileira")

# Configurações via ENV
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def enviar_alerta(mensagem, nivel="CRITICAL"):
    """
    Envia um alerta para os canais configurados.
    """
    prefixo = "🚨 [ALERTA VERMELHO]" if nivel == "CRITICAL" else "⚠️ [AVISO]"
    texto_final = f"{prefixo} {datetime.now().strftime('%d/%m %H:%M')}\n\n{mensagem}"
    
    # 1. Log no arquivo do sistema
    logger.error(texto_final)
    print(texto_final)

    # 2. Telegram (se configurado)
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": texto_final,
                "parse_mode": "HTML"
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.warning(f"Falha ao enviar alerta via Telegram: {e}")

    # 3. Registrar em um log de incidentes central
    with open("/home/bitnami/logs/incidentes.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | {nivel} | {mensagem}\n")

if __name__ == "__main__":
    # Teste manual
    enviar_alerta("Teste de sistema de notificação.")
