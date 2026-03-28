#!/usr/bin/env python3
"""
Aplica o novo tdc_content (com tag_slugs) no banco de dados.
Atualiza wp_7_postmeta.tdc_content e wp_7_posts.post_content para o post 18135.
"""

import subprocess
import sys
import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

INPUT_FILE = "/home/bitnami/homepage_tdc_tags.txt"
BACKUP_FILE = "/home/bitnami/homepage_tdc_backup_pretags.txt"

# Backup do estado atual do DB antes de aplicar
db_cmd = [
    "/opt/bitnami/mariadb/bin/mariadb",
    "-u", "bn_wordpress",
    "-p" + os.getenv("DB_PASS"),
    "-h", "127.0.0.1",
    "-P", "3306",
    "bitnami_wordpress",
]

print("--- Backup do tdc_content atual ---")
backup_sql = "SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'"
result_bk = subprocess.run(db_cmd + ["-N", "-e", backup_sql], capture_output=True, text=True, timeout=15)
if result_bk.returncode == 0:
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        f.write(result_bk.stdout.strip())
    print(f"✓ Backup salvo: {BACKUP_FILE} ({len(result_bk.stdout.strip())} bytes)")
else:
    print(f"✗ Erro no backup: {result_bk.stderr}")
    sys.exit(1)

# Read the new tdc_content
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    new_content = f.read().strip()

print(f"Conteúdo novo: {len(new_content)} bytes")

# Conectar e aplicar via PyMySQL
try:
    conn = pymysql.connect(
        host='127.0.0.1',
        user='bn_wordpress',
        password=os.getenv("DB_PASS"),
        database='bitnami_wordpress',
        port=3306,
        autocommit=True
    )
    with conn.cursor() as cursor:
        print("\n--- Atualizando tdc_content ---")
        cursor.execute(
            "UPDATE wp_7_postmeta SET meta_value=%s WHERE post_id=18135 AND meta_key='tdc_content'",
            (new_content,)
        )
        print("✓ tdc_content atualizado!")

    # Verify
    print("\n--- Verificação ---")
    with conn.cursor() as cursor:
        cursor.execute("SELECT LENGTH(meta_value) FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'")
        len_val = cursor.fetchone()[0]
        print(f"Tamanho no DB: {len_val}")
        
    # Check tag_slugs in DB content
    with conn.cursor() as cursor:
        cursor.execute("SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'")
        db_content = cursor.fetchone()[0]
        import re
        tag_slugs = re.findall(r'tag_slug="([^"]*)"', db_content)
        print(f"\ntag_slugs no DB: {len_val and len(tag_slugs)}")
        for ts in tag_slugs:
            print(f"  ✓ {ts}")

finally:
    if 'conn' in locals() and conn:
        conn.close()

# Flush OPcache
print("\n--- Limpando OPcache ---")
try:
    with open("/opt/bitnami/php/var/run/php-fpm.pid") as f:
        pid = f.read().strip()
    subprocess.run(["sudo", "kill", "-USR2", pid], check=False)
except Exception as e:
    print(f"Erro a limpar OPcache: {e}")

print("\n✓ Concluído! Verifique a homepage em https://brasileira.news")
