# -*- coding: utf-8 -*-
"""
GESTOR DE BUDGET - Brasileira.news

Controla os gastos com APIs de LLM, rastreando o número de chamadas
e bloqueando novas requisições se ultrapassar o limite diário definido.
"""

import json
import os
from datetime import datetime
from pathlib import Path

BUDGET_FILE = Path("/home/bitnami/llm_budget.json")
DAILY_CALL_LIMIT = int(os.getenv("DAILY_LLM_CALL_LIMIT", "2000"))

def _load_budget():
    """Carrega os dados de budget do arquivo JSON."""
    if not BUDGET_FILE.exists():
        return {}
    try:
        with open(BUDGET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_budget(data):
    """Salva os dados de budget no arquivo JSON."""
    try:
        with open(BUDGET_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[BUDGET ERRO] Falha ao salvar: {e}")

def check_budget_ok():
    """
    Verifica se ainda há budget para realizar chamadas hoje.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    data = _load_budget()
    usage = data.get(hoje, {})
    total_calls = usage.get("total_calls", 0)
    
    if total_calls >= DAILY_CALL_LIMIT:
        return False, total_calls
    return True, total_calls

def registrar_chamada(provider_model, tokens_input=0, tokens_output=0):
    """
    Registra uma chamada de LLM para controle de budget.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    data = _load_budget()
    
    if hoje not in data:
        # Limpar dados antigos (manter últimos 30 dias)
        if len(data) > 30:
            datas_ordenadas = sorted(data.keys())
            for d in datas_ordenadas[:-30]:
                data.pop(d)
        data[hoje] = {"total_calls": 0, "providers": {}}
    
    usage = data[hoje]
    usage["total_calls"] += 1
    
    providers = usage["providers"]
    provider_name = provider_model.split(":")[0]
    p_usage = providers.get(provider_name, {"calls": 0, "models": {}})
    p_usage["calls"] += 1
    
    model_name = provider_model.split(":")[1] if ":" in provider_model else "unknown"
    m_usage = p_usage["models"].get(model_name, {"calls": 0})
    m_usage["calls"] += 1
    
    p_usage["models"][model_name] = m_usage
    providers[provider_name] = p_usage
    
    _save_budget(data)
