#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atualizar menu de navegação do brasileira.news via REST API
e limpar caches do WordPress/Newspaper.
"""

import requests
import base64
import json

import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Config
WP_URL = "https://brasileira.news/wp-json/wp/v2"
WP_USER = "iapublicador"
WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")

AUTH_HEADERS = {
    'Authorization': f'Basic {base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()}',
    'Content-Type': 'application/json'
}

# ============================================================
# STEP 1: Get existing menus
# ============================================================
print("=== Consultando menus existentes ===")
try:
    # List menus
    r = requests.get(f"{WP_URL}/menus", headers=AUTH_HEADERS, timeout=15)
    if r.status_code == 200:
        menus = r.json()
        for menu in menus:
            print(f"  Menu: {menu.get('name', '?')} (ID: {menu.get('id', '?')})")
    else:
        print(f"  Status: {r.status_code} - Tentando endpoint alternativo...")
        # Try Newspaper/tagDiv specific endpoint or wp/v2/menus
        r = requests.get(f"https://brasileira.news/wp-json/wp/v2/menu-items?menus=11727", headers=AUTH_HEADERS, timeout=15)
        print(f"  Alt status: {r.status_code}")
except Exception as e:
    print(f"  Erro: {e}")

# ============================================================
# STEP 2: Get existing menu items from the header menu
# ============================================================
print("\n=== Menu items do header (td-demo-header-menu, ID: 11727) ===")
try:
    r = requests.get(f"{WP_URL}/menu-items?menus=11727&per_page=50", headers=AUTH_HEADERS, timeout=15)
    if r.status_code == 200:
        items = r.json()
        for item in items:
            print(f"  Item ID:{item.get('id')} title:{item.get('title',{}).get('rendered','?')} url:{item.get('url','?')}")
    else:
        print(f"  Status: {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"  Erro: {e}")

# ============================================================
# STEP 3: Get all categories to create menu items
# ============================================================
print("\n=== Categorias disponíveis ===")
EDITORIAL_CATEGORIES = [
    (71, 'Política'),
    (72, 'Economia'),
    (129, 'Tecnologia'),
    (122, 'Entretenimento'),
    (81, 'Esportes'),
    (88, 'Internacional'),
    (73, 'Justiça'),
    (74, 'Saúde'),
    (136, 'Meio Ambiente'),
]

try:
    r = requests.get(f"{WP_URL}/categories?per_page=100", headers=AUTH_HEADERS, timeout=15)
    if r.status_code == 200:
        categories = r.json()
        cat_map = {c['id']: c for c in categories}
        for cat_id, label in EDITORIAL_CATEGORIES:
            cat = cat_map.get(cat_id)
            if cat:
                print(f"  ✓ {label}: ID={cat_id}, slug={cat['slug']}, link={cat['link']}")
            else:
                print(f"  ✗ {label}: ID={cat_id} NÃO ENCONTRADO")
    else:
        print(f"  Status: {r.status_code}")
except Exception as e:
    print(f"  Erro: {e}")

# ============================================================
# STEP 4: Clear WordPress caches (object cache, transients)
# ============================================================
print("\n=== Limpando caches ===")

# Delete Newspaper/tagDiv transients via SQL
import subprocess

db_cmd = [
    '/opt/bitnami/mariadb/bin/mariadb',
    '-u', 'bn_wordpress',
    '-p' + os.getenv("DB_PASS"),
    '-h', '127.0.0.1',
    '-P', '3306',
    'bitnami_wordpress',
    '-e'
]

# Clear tagDiv caches/transients
cache_queries = [
    "DELETE FROM wp_7_options WHERE option_name LIKE '%_transient_%';",
    "DELETE FROM wp_7_options WHERE option_name LIKE '%td_cache_%';",
    "DELETE FROM wp_7_options WHERE option_name LIKE '%tdc_cache_%';",
]

for q in cache_queries:
    result = subprocess.run(db_cmd + [q], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        print(f"  ✓ {q[:60]}...")
    else:
        print(f"  ✗ {q[:40]}: {result.stderr[:100]}")

print("\nConcluído!")
