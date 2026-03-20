# -*- coding: utf-8 -*-
import os
import sys
import json
import pytest
from pathlib import Path

# Adicionar root ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gestor_cache import carregar_cache, salvar_no_cache, ARQUIVO_CACHE
from deduplicador_unificado import link_ja_processado
from motor_rss.llm_router import classify_tier

def test_classify_tier():
    # Fontes institucionais -> TIER 2
    assert classify_tier(source="Agência Brasil") == 2
    assert classify_tier(source="Senado Federal") == 2
    # Imprensa -> TIER 1
    assert classify_tier(source="G1 - Globo") == 1
    assert classify_tier(source="Folha de S.Paulo") == 1

def test_cache_rotation(tmp_path, monkeypatch):
    # Mock do arquivo de cache
    test_cache_file = tmp_path / "test_historico.txt"
    monkeypatch.setattr("gestor_cache.ARQUIVO_CACHE", str(test_cache_file))
    
    # Criar um cache com 5005 links
    with open(test_cache_file, "w") as f:
        for i in range(5005):
            f.write(f"http://link-{i}.com\n")
    
    # Salvar novo link deve triggar rotação para 5000
    salvar_no_cache("http://novo-link.com")
    
    with open(test_cache_file, "r") as f:
        lines = f.readlines()
    
    assert len(lines) == 5000
    assert lines[-1].strip() == "http://novo-link.com"
    # O primeiro link (link-0) deve ter sido removido
    assert "http://link-0.com\n" not in lines

def test_deduplicador_interface():
    # Teste básico de fumaça (sem mocks complexos por enquanto)
    # Verifica se a função existe e não quebra se o DB falhar
    assert isinstance(link_ja_processado("http://test.com"), bool)

def test_budget_logic(tmp_path, monkeypatch):
    from gestor_budget import check_budget_ok, registrar_chamada, BUDGET_FILE
    
    test_budget_json = tmp_path / "budget.json"
    monkeypatch.setattr("gestor_budget.BUDGET_FILE", test_budget_json)
    monkeypatch.setattr("gestor_budget.DAILY_CALL_LIMIT", 5)
    
    # Inicialmente OK
    ok, count = check_budget_ok()
    assert ok is True
    assert count == 0
    
    # Registrar 5 chamadas
    for i in range(5):
        registrar_chamada(f"test:model-{i}")
    
    # Agora deve estar bloqueado
    ok, count = check_budget_ok()
    assert ok is False
    assert count == 5
