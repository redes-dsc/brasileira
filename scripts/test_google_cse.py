#!/usr/bin/env python3
"""
Script de teste do Google CSE - roda periodicamente para verificar
quando o billing propagar e a API começar a funcionar.
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Adicionar path do projeto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv("/home/bitnami/.env", override=True)

import requests

LOG_FILE = "/home/bitnami/logs/google_cse_test.log"
KEYS_TO_TEST = [
    ("BRA3", os.getenv("GOOGLE_API_KEY_CSE", "")),
    ("Alternativa", "AIzaSyCDB7Nj5-QyH236SfduMGPQCwzKsrV0k7c"),
]
CSE_ID = os.getenv("GOOGLE_CSE_ID", "c0c5e0cf93abf4668")


def log(message: str):
    """Escreve no log com timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def test_key(name: str, api_key: str) -> bool:
    """Testa uma chave de API."""
    if not api_key:
        log(f"  {name}: Chave vazia, pulando")
        return False
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": "Brasil governo",
        "cx": CSE_ID,
        "key": api_key,
        "searchType": "image",
        "num": 1
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            log(f"  ✓ {name}: FUNCIONANDO! {len(items)} imagem(ns)")
            return True
        else:
            error = resp.json().get("error", {})
            code = error.get("code", resp.status_code)
            msg = error.get("message", "")[:60]
            log(f"  ✗ {name}: HTTP {code} - {msg}")
            return False
            
    except Exception as e:
        log(f"  ✗ {name}: Erro - {str(e)[:60]}")
        return False


def main():
    log("=" * 50)
    log("TESTE GOOGLE CSE - Verificação de Propagação")
    log(f"CSE_ID: {CSE_ID}")
    
    any_working = False
    for name, key in KEYS_TO_TEST:
        if test_key(name, key):
            any_working = True
    
    if any_working:
        log(">>> SUCESSO! Google CSE está funcionando!")
        log(">>> Removendo este teste do cron...")
        # Quando funcionar, remove do cron automaticamente
        os.system("crontab -l 2>/dev/null | grep -v 'test_google_cse.py' | crontab -")
        log(">>> Cron removido. Sistema de imagens completo!")
    else:
        log(">>> Ainda aguardando propagação do billing...")
    
    log("")


if __name__ == "__main__":
    main()
