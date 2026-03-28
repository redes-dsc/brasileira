#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicar a nova homepage no banco de dados.
Atualiza wp_7_postmeta.tdc_content para o post 18135.
"""

import subprocess
import sys
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

# Read the new tdc_content
with open('/home/bitnami/homepage_tdc_new.txt', 'r', encoding='utf-8') as f:
    new_content = f.read().strip()

print(f"Conteúdo novo: {len(new_content)} bytes")

# Build MySQL update command with variables
print("\n--- Atualizando tdc_content ---")
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
        cursor.execute(
            "UPDATE wp_7_postmeta SET meta_value=%s WHERE post_id=18135 AND meta_key='tdc_content'",
            (new_content,)
        )
        print("✓ tdc_content atualizado com sucesso!")
        
    print("\n--- Verificação ---")
    with conn.cursor() as cursor:
        cursor.execute("SELECT LENGTH(meta_value) FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'")
        len_val = cursor.fetchone()[0]
        print(f"Tamanho no DB: {len_val}")
        
    with conn.cursor() as cursor:
        cursor.execute("SELECT meta_value FROM wp_7_postmeta WHERE post_id=18135 AND meta_key='tdc_content'")
        db_content = cursor.fetchone()[0]
        empty_cats = db_content.count('category_id=""')
        print(f"category_id vazio no DB: {empty_cats} (esperado: 2 - hero grids)")
        for cat in ['71', '72', '129', '122', '81', '88', '73', '136', '74', '78', '79', '76']:
            count = db_content.count(f'category_id="{cat}"')
            if count > 0:
                print(f"  ✓ category_id=\"{cat}\" encontrado ({count}x)")
except Exception as e:
    print(f"✗ Erro: {e}")
    sys.exit(1)
finally:
    if 'conn' in locals() and conn:
        conn.close()

print("\nConcluído!")
