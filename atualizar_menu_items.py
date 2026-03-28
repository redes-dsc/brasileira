#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Substituir itens do menu de navegação demo por categorias editoriais reais.
"""

import requests
import base64

import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

WP_URL = "https://brasileira.news/wp-json/wp/v2"
WP_USER = "iapublicador"
WP_APP_PASSWORD = os.getenv("WP_APP_PASS")

AUTH_HEADERS = {
    'Authorization': f'Basic {base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()}',
    'Content-Type': 'application/json'
}

# Menu items to update: (existing_item_id, new_title, new_category_id)
# Current items: 18274(News), 18275(Women), 18276(Celebrity), 18277(Travel), 18278(Food), 18279(Music)
MENU_UPDATES = [
    (18274, 'Política',       71),   # News -> Política
    (18275, 'Economia',       72),   # Women -> Economia
    (18276, 'Tecnologia',     129),  # Celebrity -> Tecnologia
    (18277, 'Entretenimento', 122),  # Travel -> Entretenimento
    (18278, 'Esportes',       81),   # Food -> Esportes
    (18279, 'Internacional',  88),   # Music -> Internacional
]

# Additional menu items to create
MENU_NEW_ITEMS = [
    ('Justiça',       73),
    ('Saúde',         74),
    ('Meio Ambiente', 136),
]

print("=== Atualizando itens de menu existentes ===")
for item_id, new_title, cat_id in MENU_UPDATES:
    # Get category URL
    r = requests.get(f"{WP_URL}/categories/{cat_id}", headers=AUTH_HEADERS, timeout=10)
    if r.status_code == 200:
        cat_link = r.json().get('link', '')
    else:
        print(f"  ✗ Categoria {cat_id} não encontrada")
        continue

    # Update the menu item
    payload = {
        'title': new_title,
        'url': cat_link,
        'object': 'category',
        'object_id': cat_id,
        'type': 'taxonomy',
    }
    
    r = requests.post(f"{WP_URL}/menu-items/{item_id}", 
                      headers=AUTH_HEADERS, json=payload, timeout=10)
    if r.status_code == 200:
        print(f"  ✓ Item {item_id}: -> {new_title} ({cat_link})")
    else:
        print(f"  ✗ Item {item_id}: {r.status_code} - {r.text[:200]}")

print("\n=== Criando novos itens de menu ===")
for new_title, cat_id in MENU_NEW_ITEMS:
    r = requests.get(f"{WP_URL}/categories/{cat_id}", headers=AUTH_HEADERS, timeout=10)
    if r.status_code == 200:
        cat_link = r.json().get('link', '')
    else:
        print(f"  ✗ Categoria {cat_id} não encontrada")
        continue

    payload = {
        'title': new_title,
        'url': cat_link,
        'menus': 11727,  # header menu
        'object': 'category',
        'object_id': cat_id,
        'type': 'taxonomy',
        'status': 'publish',
    }
    
    r = requests.post(f"{WP_URL}/menu-items", 
                      headers=AUTH_HEADERS, json=payload, timeout=10)
    if r.status_code == 201:
        print(f"  ✓ Criado: {new_title} ({cat_link})")
    else:
        print(f"  ✗ Criar {new_title}: {r.status_code} - {r.text[:200]}")

print("\nMenu atualizado!")
