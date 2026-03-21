#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive fix: decode ALL base64 strings in tdc_content to find remaining English text.
"""
import re
import base64
import urllib.parse
import subprocess
import sys
import os
from dotenv import load_dotenv

load_dotenv()

DB_CMD = [
    '/opt/bitnami/mariadb/bin/mariadb',
    '-u', 'bn_wordpress',
    '-p' + os.getenv("DB_PASS"),
    '-h', '127.0.0.1', '-P', '3306',
    'bitnami_wordpress', '-N', '-e'
]

# Read current tdc_content
result = subprocess.run(DB_CMD + [
    "SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'"
], capture_output=True, text=True, timeout=30)

content = result.stdout.strip()
print(f"Content size: {len(content)} bytes")
print()

# ============================================================
# Find ALL base64-encoded values in the content
# ============================================================
# Pattern: attribute="base64_string" where base64 is > 8 chars
b64_pattern = r'([a-z_]+)="((?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?)"'

print("=== ALL BASE64 DECODED VALUES ===")
seen = set()
all_attrs = []
for m in re.finditer(b64_pattern, content):
    attr_name = m.group(1)
    b64_val = m.group(2)
    
    if len(b64_val) < 8:
        continue
    
    # Skip known non-base64 attrs
    if attr_name in ('tdc_css', 'css', 'custom_css', 'style', 'color', 'modules_on_row'):
        continue
    
    try:
        decoded = base64.b64decode(b64_val).decode('utf-8', errors='replace')
        # URL-decode
        decoded_clean = urllib.parse.unquote(decoded).strip()
        
        if decoded_clean and decoded_clean not in seen and len(decoded_clean) > 1:
            seen.add(decoded_clean)
            pos = m.start()
            all_attrs.append((pos, attr_name, decoded_clean, b64_val))
    except:
        pass

# Sort by position
all_attrs.sort(key=lambda x: x[0])

for pos, attr, decoded, b64 in all_attrs:
    # Flag English text
    is_english = any(w in decoded.lower() for w in [
        'unlock', 'access', 'premium', 'subscribe', 'never miss', 
        'browse free', 'devices', 'email', 'view all', 'load more',
        'latest', 'popular', 'celebrity', 'technology', 'finance',
        'marketing', 'women', 'war in ukraine', 'gain full',
        'breaking news', 'articles', 'trending', 'my account',
        'all', 'custom ad'
    ])
    flag = " *** ENGLISH ***" if is_english else ""
    print(f"  pos={pos:>6} [{attr}] = \"{decoded[:80]}\"{flag}")

print()

# ============================================================
# Also find remaining plain-text English
# ============================================================
print("=== PLAIN-TEXT ENGLISH CHECK ===")
english_patterns = [
    'View All', 'Load More', 'Breaking news', 'Latest Articles',
    'Popular:', 'My account', 'SUBSCRIBE', 'Unlock All',
    'Gain full access', 'Never miss a story', 'Browse free',
    'Your email address', 'War in Ukraine', 'Celebrities',
    'Custom Ad Box'
]

for pat in english_patterns:
    count = content.count(pat)
    if count > 0:
        print(f"  Found: \"{pat}\" ({count}x)")

print()

# ============================================================
# Check mega menu - submenu items under Política
# ============================================================
print("=== MEGA MENU ITEMS ===")
result2 = subprocess.run(DB_CMD + ["""
SELECT p.ID, p.post_title, p.menu_order,
  (SELECT pm2.meta_value FROM wp_7_postmeta pm2 WHERE pm2.post_id = p.ID AND pm2.meta_key = '_menu_item_menu_item_parent' LIMIT 1) as parent_id,
  (SELECT pm3.meta_value FROM wp_7_postmeta pm3 WHERE pm3.post_id = p.ID AND pm3.meta_key = '_menu_item_url' LIMIT 1) as url
FROM wp_7_posts p
JOIN wp_7_term_relationships tr ON p.ID = tr.object_id
JOIN wp_7_term_taxonomy tt ON tr.term_taxonomy_id = tt.term_taxonomy_id
WHERE tt.term_id = 11727 AND p.post_type = 'nav_menu_item' AND p.post_status = 'publish'
ORDER BY p.menu_order
"""], capture_output=True, text=True, timeout=15)
print(result2.stdout[:2000] if result2.stdout else result2.stderr[:500])

# ============================================================
# Check the top bar menu  
# ============================================================
print("\n=== TOP BAR CONFIGURATION ===")
result3 = subprocess.run(DB_CMD + ["""
SELECT option_name, LEFT(option_value, 200) FROM wp_7_options 
WHERE option_name LIKE '%td_option%' OR option_name LIKE '%topbar%' OR option_name LIKE '%top_bar%'
LIMIT 20
"""], capture_output=True, text=True, timeout=15)
print(result3.stdout[:2000] if result3.stdout else "No results")

# Check for td theme options
result4 = subprocess.run(DB_CMD + ["""
SELECT option_name FROM wp_7_options 
WHERE option_name LIKE 'td_%' 
ORDER BY option_name LIMIT 30
"""], capture_output=True, text=True, timeout=15)
print("\n=== TD OPTIONS ===")
print(result4.stdout[:2000] if result4.stdout else "No results")
