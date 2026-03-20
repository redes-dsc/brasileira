#!/usr/bin/env python3
"""
Aplica o novo tdc_content (com tag_slugs) no banco de dados.
Atualiza wp_7_postmeta.tdc_content e wp_7_posts.post_content para o post 18135.
"""

import subprocess
import sys

INPUT_FILE = "/home/bitnami/homepage_tdc_tags.txt"
BACKUP_FILE = "/home/bitnami/homepage_tdc_backup_pretags.txt"

# Backup do estado atual do DB antes de aplicar
db_cmd = [
    "/opt/bitnami/mariadb/bin/mariadb",
    "-u", "bn_wordpress",
    "-pd0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b",
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

# Escape for MySQL
escaped = new_content.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

# Build MySQL update commands
sql1 = f"UPDATE wp_7_postmeta SET meta_value='{escaped}' WHERE post_id=18135 AND meta_key='tdc_content';"
sql2 = f"UPDATE wp_7_posts SET post_content='{escaped}' WHERE ID=18135;"

# Write SQL to temp files
sql_file1 = "/tmp/update_homepage_tags.sql"
sql_file2 = "/tmp/update_homepage_tags_post.sql"

with open(sql_file1, "w", encoding="utf-8") as f:
    f.write(sql1)
with open(sql_file2, "w", encoding="utf-8") as f:
    f.write(sql2)

print(f"SQL tdc_content: {sql_file1} ({len(sql1)} bytes)")
print(f"SQL post_content: {sql_file2} ({len(sql2)} bytes)")

# Execute
print("\n--- Atualizando tdc_content ---")
r1 = subprocess.run(db_cmd, stdin=open(sql_file1, "r"), capture_output=True, text=True, timeout=30)
if r1.returncode == 0:
    print("✓ tdc_content atualizado!")
else:
    print(f"✗ Erro: {r1.stderr}")
    sys.exit(1)

print("\n--- Atualizando post_content ---")
r2 = subprocess.run(db_cmd, stdin=open(sql_file2, "r"), capture_output=True, text=True, timeout=30)
if r2.returncode == 0:
    print("✓ post_content atualizado!")
else:
    print(f"✗ Erro: {r2.stderr}")

# Verify
print("\n--- Verificação ---")
verify_sql = "SELECT LENGTH(meta_value) as len FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content';"
r3 = subprocess.run(db_cmd + ["-e", verify_sql], capture_output=True, text=True, timeout=10)
print(r3.stdout.strip())

# Check tag_slugs in DB content
check_sql = "SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'"
r4 = subprocess.run(db_cmd + ["-N", "-e", check_sql], capture_output=True, text=True, timeout=10)
if r4.returncode == 0:
    db_content = r4.stdout.strip()
    import re
    tag_slugs = re.findall(r'tag_slug="([^"]*)"', db_content)
    print(f"\ntag_slugs no DB: {len(tag_slugs)}")
    for ts in tag_slugs:
        print(f"  ✓ {ts}")

# Flush OPcache
print("\n--- Limpando OPcache ---")
subprocess.run(["sudo", "kill", "-USR2", "$(cat /opt/bitnami/php/var/run/php-fpm.pid)"],
               shell=False, capture_output=True)

print("\n✓ Concluído! Verifique a homepage em https://brasileira.news")
