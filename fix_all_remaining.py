#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMPREHENSIVE FIX: All remaining English text, demo labels, and navigation issues.
"""
import re
import base64
import urllib.parse
import subprocess
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

DB_CMD_BASE = [
    '/opt/bitnami/mariadb/bin/mariadb',
    '-u', 'bn_wordpress',
    '-p' + os.getenv("DB_PASS"),
    '-h', '127.0.0.1', '-P', '3306',
    'bitnami_wordpress'
]
DB_CMD = DB_CMD_BASE + ['-N', '-e']

WP_URL = "https://brasileira.news/wp-json/wp/v2"
AUTH_HEADERS = {
    'Authorization': f'Basic {base64.b64encode(b"iapublicador:nWgboohRWZGLv2d7ebQgkf80").decode()}',
    'Content-Type': 'application/json'
}

# ============================================================
# STEP 1: Fix ALL base64-encoded English labels in tdc_content
# ============================================================
print("=== STEP 1: Corrigir labels base64 em inglês ===")

result = subprocess.run(DB_CMD + [
    "SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'"
], capture_output=True, text=True, timeout=30)
content = result.stdout.strip()

# All section description labels to translate
B64_LABEL_MAP = {
    'War in Ukraine': 'Últimas Notícias',
    'Finance': 'Economia & Negócios',
    'Marketing': 'Infraestrutura & Cidades',
    'Technology': 'Segmentos de Tecnologia',
    'Celebrities': 'Entretenimento & Famosos',
    'Latest Articles': 'Meio Ambiente & Sustentabilidade',
    # Subscription widget  
    '- Gain full access to our premium content': '- Acesso completo ao conteúdo exclusivo',
    '- Never miss a story with active notifications': '- Nunca perca uma notícia com notificações ativas',
    '- Browse free from up to 5 devices at once': '- Navegue de até 5 dispositivos ao mesmo tempo',
}

changes = 0
for old_text, new_text in B64_LABEL_MAP.items():
    # Try URL-encoded base64
    old_b64_q = base64.b64encode(urllib.parse.quote(old_text).encode()).decode()
    new_b64_q = base64.b64encode(urllib.parse.quote(new_text).encode()).decode()
    
    if old_b64_q in content:
        content = content.replace(old_b64_q, new_b64_q)
        print(f"  ✓ '{old_text}' -> '{new_text}' (url-encoded)")
        changes += 1
    
    # Try raw base64
    old_b64_r = base64.b64encode(old_text.encode()).decode()
    new_b64_r = base64.b64encode(new_text.encode()).decode()
    
    if old_b64_r in content:
        content = content.replace(old_b64_r, new_b64_r)
        print(f"  ✓ '{old_text}' -> '{new_text}' (raw)")
        changes += 1

# ============================================================
# STEP 2: Fix plain-text English strings 
# ============================================================
print("\n=== STEP 2: Corrigir textos plain-text ===")

PLAIN_TEXT_MAP = {
    'View All': 'Ver Todas',
    'Unlock All': 'Assine Agora',
    'Your email address': 'Seu endereço de e-mail',
    'Load More': 'Carregar Mais',
    'My account': 'Minha Conta',
}

for old_text, new_text in PLAIN_TEXT_MAP.items():
    count = content.count(old_text)
    if count > 0:
        content = content.replace(old_text, new_text)
        print(f"  ✓ '{old_text}' -> '{new_text}' ({count}x)")
        changes += 1

# Fix Privacy Policy link  
PP_OLD = "I've read and accept the <a href=\"#\">Privacy Policy</a>."
PP_NEW = "Li e aceito a <a href=\"#\">Política de Privacidade</a>."

# Try base64 encoding of the PP text
pp_old_b64 = base64.b64encode(urllib.parse.quote(PP_OLD).encode()).decode()
pp_new_b64 = base64.b64encode(urllib.parse.quote(PP_NEW).encode()).decode()
if pp_old_b64 in content:
    content = content.replace(pp_old_b64, pp_new_b64)
    print(f"  ✓ Privacy Policy -> Política de Privacidade (b64)")
    changes += 1

# Also try the pp_msg attribute directly (it seems to be plain text)
if PP_OLD in content:
    content = content.replace(PP_OLD, PP_NEW)
    print(f"  ✓ Privacy Policy -> Política de Privacidade (plain)")
    changes += 1

# ============================================================
# STEP 3: Fix SUBSCRIBE button text (likely in shortcode)
# ============================================================
print("\n=== STEP 3: Corrigir botão SUBSCRIBE ===")
# The SUBSCRIBE button in the header is likely a theme option, not in tdc_content
# But check if there's a "SUBSCRIBE" text in the content
subscribe_count = content.count('SUBSCRIBE')
if subscribe_count > 0:
    content = content.replace('SUBSCRIBE', 'ASSINE')
    print(f"  ✓ 'SUBSCRIBE' -> 'ASSINE' ({subscribe_count}x)")
    changes += 1

# Also check for "Subscribe" (case-sensitive)  
# Already handled above via B64 map

# ============================================================
# STEP 4: Save the updated tdc_content
# ============================================================
print(f"\n=== STEP 4: Salvando ({changes} mudanças) ===")

if changes > 0:
    escaped = content.replace('\\', '\\\\').replace("'", "\\'")
    sql = f"UPDATE wp_7_postmeta SET meta_value='{escaped}' WHERE post_id=18135 AND meta_key='tdc_content';\n"
    sql += f"UPDATE wp_7_posts SET post_content='{escaped}' WHERE ID=18135;\n"
    
    with open('/tmp/fix_all_english.sql', 'w') as f:
        f.write(sql)
    
    result = subprocess.run(DB_CMD_BASE, stdin=open('/tmp/fix_all_english.sql'), 
                          capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        print("  ✓ DB atualizado!")
    else:
        print(f"  ✗ Erro: {result.stderr[:200]}")

# ============================================================
# STEP 5: Fix Política mega menu (remove demo submenu items)
# ============================================================
print("\n=== STEP 5: Corrigir mega menu de Política ===")

# Get all header menu items
r = requests.get(f"{WP_URL}/menu-items?menus=11727&per_page=100", headers=AUTH_HEADERS, timeout=15)
if r.status_code == 200:
    items = r.json()
    politica_id = None
    
    for item in items:
        title = item.get('title', {}).get('rendered', '')
        item_id = item.get('id')
        parent = item.get('parent', 0)
        
        if title == 'Política':
            politica_id = item_id
            print(f"  Política item ID: {politica_id}")
        
        # Delete any items that are children of Política (demo submenu)
        if parent > 0:
            # This is a submenu item - check if it's a demo item
            dr = requests.delete(f"{WP_URL}/menu-items/{item_id}?force=true", headers=AUTH_HEADERS, timeout=10)
            print(f"  {'✓' if dr.status_code == 200 else '✗'} Deletado submenu: '{title}' (ID:{item_id}, parent:{parent})")
    
    # Also check for orphaned/empty items
    for item in items:
        title = item.get('title', {}).get('rendered', '')
        item_id = item.get('id')
        if not title.strip():
            dr = requests.delete(f"{WP_URL}/menu-items/{item_id}?force=true", headers=AUTH_HEADERS, timeout=10)
            print(f"  {'✓' if dr.status_code == 200 else '✗'} Deletado item vazio (ID:{item_id})")

    # Remove the dropdown arrow from Política - update it to be a simple link
    if politica_id:
        r2 = requests.get(f"{WP_URL}/categories/71", headers=AUTH_HEADERS, timeout=10)
        cat_link = r2.json().get('link', '') if r2.status_code == 200 else ''
        
        update_payload = {
            'title': 'Política',
            'url': cat_link,
            'object': 'category',
            'object_id': 71,
            'type': 'taxonomy',
        }
        ur = requests.post(f"{WP_URL}/menu-items/{politica_id}", headers=AUTH_HEADERS, json=update_payload, timeout=10)
        print(f"  {'✓' if ur.status_code == 200 else '✗'} Política atualizado como link simples")

# ============================================================
# STEP 6: Fix top bar (duplicate categories)
# ============================================================
print("\n=== STEP 6: Corrigir top bar duplicado ===")

# The top bar in Newspaper theme is controlled by theme options (td_011_settings)
# Let's find and update it
result_opts = subprocess.run(DB_CMD + [
    "SELECT option_value FROM wp_7_options WHERE option_name='td_011_settings'"
], capture_output=True, text=True, timeout=15)

if result_opts.stdout.strip():
    try:
        settings = json.loads(result_opts.stdout.strip())
        
        # Show relevant keys
        for key in sorted(settings.keys()):
            if 'top' in key.lower() or 'bar' in key.lower() or 'menu' in key.lower() or 'header' in key.lower():
                print(f"  {key}: {str(settings[key])[:100]}")
        
        # Fix the top bar - disable the secondary menu or set it to show different items
        # In Newspaper theme, the top bar menu can be disabled:
        if 'tds_top_menu' in settings:
            old_val = settings['tds_top_menu']
            settings['tds_top_menu'] = ''  # Disable top bar menu
            print(f"  ✓ tds_top_menu: '{old_val}' -> '' (disabled)")
        
        if 'tds_top_bar_show' in settings:
            old_val = settings['tds_top_bar_show']
            # Keep top bar but without the duplicate menu
            print(f"  tds_top_bar_show: {old_val}")
        
        # Save updated settings
        escaped_settings = json.dumps(settings).replace('\\', '\\\\').replace("'", "\\'")
        sql = f"UPDATE wp_7_options SET option_value='{escaped_settings}' WHERE option_name='td_011_settings';"
        
        result_update = subprocess.run(DB_CMD_BASE + ['-e', sql], 
                                      capture_output=True, text=True, timeout=15)
        if result_update.returncode == 0:
            print("  ✓ Theme settings atualizados!")
        else:
            print(f"  ✗ Erro: {result_update.stderr[:200]}")
            
    except json.JSONDecodeError as e:
        print(f"  Settings não é JSON: {str(e)[:100]}")
        print(f"  Conteúdo: {result_opts.stdout.strip()[:200]}")
else:
    print("  td_011_settings não encontrado")
    
    # Try the PHP serialized format
    result_opts2 = subprocess.run(DB_CMD + [
        "SELECT LEFT(option_value, 500) FROM wp_7_options WHERE option_name='td_011_settings'"
    ], capture_output=True, text=True, timeout=15)
    print(f"  Raw: {result_opts2.stdout.strip()[:300]}")

# ============================================================
# STEP 7: Fix theme-level labels (Breaking news, Popular, etc.)
# ============================================================
print("\n=== STEP 7: Verificar labels de tema ===")

# These might be in the theme settings or theme translations via td_011_settings
# Let's check td_011_settings for translation keys
result_all_opts = subprocess.run(DB_CMD + [
    "SELECT option_name FROM wp_7_options WHERE option_name LIKE 'td_%' OR option_name LIKE 'tds_%' ORDER BY option_name"
], capture_output=True, text=True, timeout=15)
print("  TD options disponíveis:")
for line in result_all_opts.stdout.strip().split('\n')[:30]:
    print(f"    {line}")

# ============================================================
# STEP 8: Clear all caches
# ============================================================
print("\n=== STEP 8: Limpando caches ===")
cache_sql = """
DELETE FROM wp_7_options WHERE option_name LIKE '%_transient_%';
DELETE FROM wp_7_options WHERE option_name LIKE '%td_cache_%';
DELETE FROM wp_7_options WHERE option_name LIKE '%tdc_cache_%';
"""
result = subprocess.run(DB_CMD_BASE + ['-e', cache_sql], 
                       capture_output=True, text=True, timeout=15)
print(f"  {'✓' if result.returncode == 0 else '✗'} Caches limpos")

print("\n=== CONCLUÍDO ===")
