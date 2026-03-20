#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicar a nova homepage no banco de dados.
Atualiza wp_7_postmeta.tdc_content para o post 18135.
"""

import subprocess
import sys

# Read the new tdc_content
with open('/home/bitnami/homepage_tdc_new.txt', 'r', encoding='utf-8') as f:
    new_content = f.read().strip()

print(f"Conteúdo novo: {len(new_content)} bytes")

# Escape for MySQL
escaped = new_content.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')

# Build MySQL update command
sql = f"""UPDATE wp_7_postmeta SET meta_value='{escaped}' WHERE post_id=18135 AND meta_key='tdc_content';"""

# Write SQL to temp file (safer than command line for large content)
sql_file = '/tmp/update_homepage.sql'
with open(sql_file, 'w', encoding='utf-8') as f:
    f.write(sql)

print(f"SQL escrito em: {sql_file} ({len(sql)} bytes)")

# Also update post_content (which contains the rendered shortcodes)
# The post_content needs to match tdc_content for Newspaper theme to work
sql2 = f"""UPDATE wp_7_posts SET post_content='{escaped}' WHERE ID=18135;"""
sql_file2 = '/tmp/update_homepage_post.sql'
with open(sql_file2, 'w', encoding='utf-8') as f:
    f.write(sql2)

print(f"SQL post_content escrito em: {sql_file2}")

# Execute the SQL
db_cmd = [
    '/opt/bitnami/mariadb/bin/mariadb',
    '-u', 'bn_wordpress',
    f'-p{os.getenv("DB_PASS")}',
    '-h', '127.0.0.1',
    '-P', '3306',
    'bitnami_wordpress'
]

print("\n--- Atualizando tdc_content ---")
result1 = subprocess.run(db_cmd, stdin=open(sql_file, 'r'), capture_output=True, text=True, timeout=30)
if result1.returncode == 0:
    print("✓ tdc_content atualizado com sucesso!")
else:
    print(f"✗ Erro: {result1.stderr}")
    sys.exit(1)

print("\n--- Atualizando post_content ---")
result2 = subprocess.run(db_cmd, stdin=open(sql_file2, 'r'), capture_output=True, text=True, timeout=30)
if result2.returncode == 0:
    print("✓ post_content atualizado com sucesso!")
else:
    print(f"✗ Erro: {result2.stderr}")

# Verify
print("\n--- Verificação ---")
verify_sql = "SELECT LENGTH(meta_value) as len FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content';"
result3 = subprocess.run(db_cmd + ['-e', verify_sql], capture_output=True, text=True, timeout=10)
print(result3.stdout)

# Verify categories in the new content
verify_sql2 = "SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'"
result4 = subprocess.run(db_cmd + ['-N', '-e', verify_sql2], capture_output=True, text=True, timeout=10)
if result4.returncode == 0:
    db_content = result4.stdout.strip()
    empty_cats = db_content.count('category_id=""')
    print(f"category_id vazio no DB: {empty_cats} (esperado: 2 - hero grids)")
    for cat in ['71', '72', '129', '122', '81', '88', '73', '136', '74', '78', '79', '76']:
        count = db_content.count(f'category_id="{cat}"')
        if count > 0:
            print(f"  ✓ category_id=\"{cat}\" encontrado ({count}x)")

print("\nConcluído!")
