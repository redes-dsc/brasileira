#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Corrigir conteúdo demo restante:
1. Título "World of Women" na homepage 
2. Footer menu (Finance, Marketing, etc.)
3. Footer text "Company" em inglês
"""

import base64
import urllib.parse
import subprocess
import requests
import sys

DB_CMD = [
    '/opt/bitnami/mariadb/bin/mariadb',
    '-u', 'bn_wordpress',
    '-p' + os.getenv("DB_PASS"),
    '-h', '127.0.0.1', '-P', '3306',
    'bitnami_wordpress', '-N', '-e'
]

WP_URL = "https://brasileira.news/wp-json/wp/v2"
WP_USER = "iapublicador"
import os
from dotenv import load_dotenv

load_dotenv()

WP_APP_PASSWORD = os.getenv("WP_APP_PASS")
AUTH_HEADERS = {
    'Authorization': f'Basic {base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()}',
    'Content-Type': 'application/json'
}

# ============================================================
# STEP 1: Fix "World of Women" and other demo titles in tdc_content
# ============================================================
print("=== STEP 1: Corrigir títulos demo na homepage ===")

# Read current tdc_content from DB
result = subprocess.run(DB_CMD + [
    "SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'"
], capture_output=True, text=True, timeout=30)

if result.returncode != 0:
    print(f"Erro ao ler DB: {result.stderr}")
    sys.exit(1)

content = result.stdout.strip()
print(f"  Lido: {len(content)} bytes")

# List of demo labels to replace (both URL-encoded and raw base64)
DEMO_TITLE_REPLACEMENTS = {
    'World of Women': 'Saúde & Bem-Estar',
    'Food': 'Política & Poder',
    'Destinations': 'Mais Lidas',
    'Celebrity': 'Esportes',
    'Travel Blog': 'Internacional',
    'Music': 'Cultura',
    'Subscribe': 'Assine',
}

changes_made = 0
for old_label, new_label in DEMO_TITLE_REPLACEMENTS.items():
    # Try URL-encoded base64
    old_b64_q = base64.b64encode(urllib.parse.quote(old_label).encode()).decode()
    new_b64_q = base64.b64encode(urllib.parse.quote(new_label).encode()).decode()
    
    if old_b64_q in content:
        content = content.replace(old_b64_q, new_b64_q)
        print(f"  ✓ '{old_label}' -> '{new_label}' (URL-encoded)")
        changes_made += 1
    
    # Try raw base64
    old_b64_r = base64.b64encode(old_label.encode()).decode()
    new_b64_r = base64.b64encode(new_label.encode()).decode()
    
    if old_b64_r in content:
        content = content.replace(old_b64_r, new_b64_r)
        print(f"  ✓ '{old_label}' -> '{new_label}' (raw)")
        changes_made += 1

# Also fix English subscription text
SUB_TEXTS = {
    'Stay on top of what': 'Fique por dentro',
    'Subscription deal': 'Assine a newsletter',
    'Unlock All': 'Ver Mais',
    'View All': 'Ver Todas',
    'Your email address': 'Seu e-mail',
    'I\'ve read and accept the': 'Li e aceito a',
    'Privacy Policy': 'Política de Privacidade',
    'Gain full access to our premium content': 'Acesso completo ao conteúdo premium',
    'Never miss a story with active notifications': 'Nunca perca uma notícia com notificações',
    'Browse free from up to 5 devices at once': 'Navegue de até 5 dispositivos ao mesmo tempo',
}

for old_text, new_text in SUB_TEXTS.items():
    old_b64 = base64.b64encode(urllib.parse.quote(old_text).encode()).decode()
    new_b64 = base64.b64encode(urllib.parse.quote(new_text).encode()).decode()
    
    if old_b64 in content:
        content = content.replace(old_b64, new_b64)
        print(f"  ✓ Text: '{old_text[:30]}...' -> '{new_text[:30]}...'")
        changes_made += 1

# Fix "category/food/" etc in remaining places
URL_FIXES = {
    'category/food/': 'category/politica-poder/',
    'category/women/': 'category/saude/',
    'category/celebrity/': 'category/esportes-modalidades/',
    'category/travel/': 'category/internacional/',
    'category/music/': 'category/cultura/',
}

for old_url, new_url in URL_FIXES.items():
    if old_url in content:
        content = content.replace(old_url, new_url)
        print(f"  ✓ URL: '{old_url}' -> '{new_url}'")
        changes_made += 1

print(f"\n  Total de substituições: {changes_made}")

# Write back to DB if changes made
if changes_made > 0:
    print("\n  Salvando no banco...")
    escaped = content.replace('\\', '\\\\').replace("'", "\\'")
    sql = f"UPDATE wp_7_postmeta SET meta_value='{escaped}' WHERE post_id=18135 AND meta_key='tdc_content';"
    sql2 = f"UPDATE wp_7_posts SET post_content='{escaped}' WHERE ID=18135;"
    
    with open('/tmp/fix_demo.sql', 'w') as f:
        f.write(sql + '\n' + sql2)
    
    result = subprocess.run([
        '/opt/bitnami/mariadb/bin/mariadb',
        '-u', 'bn_wordpress',
        '-p' + os.getenv("DB_PASS"),
        '-h', '127.0.0.1', '-P', '3306',
        'bitnami_wordpress'
    ], stdin=open('/tmp/fix_demo.sql', 'r'), capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0:
        print("  ✓ tdc_content + post_content atualizados!")
    else:
        print(f"  ✗ Erro: {result.stderr}")
else:
    print("  Nenhuma substituição necessária no tdc_content")

# ============================================================
# STEP 2: Update footer menu
# ============================================================
print("\n=== STEP 2: Atualizar menu do rodapé ===")

# Get footer menu items
try:
    r = requests.get(f"{WP_URL}/menu-items?menus=11726&per_page=50", headers=AUTH_HEADERS, timeout=15)
    if r.status_code == 200:
        items = r.json()
        print(f"  {len(items)} itens no footer menu")
        
        FOOTER_CATEGORIES = [
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
        
        # Delete existing items and recreate
        for item in items:
            item_id = item.get('id')
            dr = requests.delete(f"{WP_URL}/menu-items/{item_id}?force=true", headers=AUTH_HEADERS, timeout=10)
            if dr.status_code == 200:
                print(f"  ✓ Deletado: {item.get('title',{}).get('rendered','?')}")
            else:
                print(f"  ✗ Deletar {item_id}: {dr.status_code}")
        
        # Create new items
        for cat_id, label in FOOTER_CATEGORIES:
            cr = requests.get(f"{WP_URL}/categories/{cat_id}", headers=AUTH_HEADERS, timeout=10)
            if cr.status_code == 200:
                cat_link = cr.json().get('link', '')
                payload = {
                    'title': label,
                    'url': cat_link,
                    'menus': 11726,
                    'object': 'category',
                    'object_id': cat_id,
                    'type': 'taxonomy',
                    'status': 'publish',
                }
                nr = requests.post(f"{WP_URL}/menu-items", headers=AUTH_HEADERS, json=payload, timeout=10)
                if nr.status_code == 201:
                    print(f"  ✓ Criado: {label}")
                else:
                    print(f"  ✗ Criar {label}: {nr.status_code} - {nr.text[:100]}")
    else:
        print(f"  Status: {r.status_code}")
except Exception as e:
    print(f"  Erro: {e}")

# ============================================================
# STEP 3: Clear caches again
# ============================================================
print("\n=== STEP 3: Limpando caches ===")
cache_sql = """
DELETE FROM wp_7_options WHERE option_name LIKE '%_transient_%';
DELETE FROM wp_7_options WHERE option_name LIKE '%td_cache_%';
DELETE FROM wp_7_options WHERE option_name LIKE '%tdc_cache_%';
"""
result = subprocess.run([
    '/opt/bitnami/mariadb/bin/mariadb',
    '-u', 'bn_wordpress',
    '-p' + os.getenv("DB_PASS"),
    '-h', '127.0.0.1', '-P', '3306', 'bitnami_wordpress', '-e', cache_sql
], capture_output=True, text=True, timeout=15)

if result.returncode == 0:
    print("  ✓ Caches limpos!")
else:
    print(f"  ✗ {result.stderr[:100]}")

print("\nConcluído!")
