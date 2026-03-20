#!/usr/bin/env python3
"""
Seed inicial: aplica TAGs editoriais nos top posts de cada categoria
para garantir que a homepage não fique vazia ao migrar para tag_slug.

DEVE SER EXECUTADO ANTES de aplicar o novo tdc_content.
"""

import sys
import os
import time
import requests
from requests.auth import HTTPBasicAuth

sys.path.insert(0, "/home/bitnami/motor_rss")
from dotenv import load_dotenv
load_dotenv("/home/bitnami/motor_rss/.env")

WP_URL = os.getenv("WP_URL", "https://brasileira.news")
WP_USER = os.getenv("WP_USER", "iapublicador")
WP_APP_PASS = os.getenv("WP_APP_PASS", "")
WP_API_BASE = f"{WP_URL}/wp-json/wp/v2"

AUTH = HTTPBasicAuth(WP_USER, WP_APP_PASS)
TIMEOUT = 20

# ── Tag IDs (obtidos na criação) ──────────────────────
TAG_IDS = {
    "home-manchete": 14908,
    "home-submanchete": 14909,
    "home-politica": 14910,
    "home-economia": 14911,
    "home-tecnologia": 14912,
    "home-entretenimento": 14913,
    "home-ciencia": 14914,
    "home-internacional": 14915,
    "home-saude": 14916,
    "home-meioambiente": 14917,
    "home-bemestar": 14918,
    "home-infraestrutura": 14919,
    "home-cultura": 14920,
    "home-sociedade": 14921,
}

# ── Mapa: tag_slug → (category_id, qtd_posts_a_tagear) ──
# Para manchete/submanchete: sem filtro de category (cat=None)
# Para editorias: filtrar por category_id
SEED_MAP = [
    # (tag_slug, category_id_filter, qtd_posts)
    ("home-manchete",       None,  1),
    ("home-submanchete",    None,  3),
    ("home-politica",       71,    1),
    ("home-economia",       72,    2),
    ("home-tecnologia",     129,   8),
    ("home-entretenimento", 122,   5),
    ("home-ciencia",        81,    5),
    ("home-internacional",  88,    5),
    ("home-saude",          73,    5),
    ("home-meioambiente",   136,   4),
    ("home-bemestar",       74,    2),
    ("home-infraestrutura", 78,    5),
    ("home-cultura",        79,    5),
    ("home-sociedade",      76,    3),
]


def fetch_top_posts(category_id=None, per_page=10):
    """Busca últimos posts publicados, opcionalmente filtrados por categoria."""
    params = {
        "per_page": per_page,
        "status": "publish",
        "orderby": "date",
        "order": "desc",
        "_fields": "id,title,tags,categories,featured_media",
    }
    if category_id:
        params["categories"] = category_id
    
    resp = requests.get(
        f"{WP_API_BASE}/posts",
        params=params,
        auth=AUTH,
        timeout=TIMEOUT,
    )
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"    ERRO ao buscar posts (cat={category_id}): {resp.status_code}")
        return []


def add_tag_to_post(post_id, tag_id, current_tags):
    """Adiciona uma tag a um post (preservando as existentes)."""
    if tag_id in current_tags:
        return True  # já tem
    
    new_tags = list(set(current_tags + [tag_id]))
    resp = requests.post(
        f"{WP_API_BASE}/posts/{post_id}",
        json={"tags": new_tags},
        auth=AUTH,
        timeout=TIMEOUT,
    )
    return resp.status_code == 200


def main():
    print("=" * 60)
    print("  SEED INICIAL — Tagear posts para homepage")
    print("=" * 60)
    print()
    
    used_post_ids = set()  # evitar reutilizar o mesmo post em manchete/sub
    total_tagged = 0
    total_errors = 0
    
    for tag_slug, cat_id, qty in SEED_MAP:
        tag_id = TAG_IDS[tag_slug]
        cat_label = f"cat={cat_id}" if cat_id else "(todas)"
        print(f"[{tag_slug}] — buscando {qty} posts ({cat_label})")
        
        # Fetch mais posts que o necessário para ter margem
        posts = fetch_top_posts(category_id=cat_id, per_page=qty * 2)
        
        if not posts:
            print(f"  ⚠ Nenhum post encontrado para {cat_label}")
            continue
        
        tagged_count = 0
        for post in posts:
            if tagged_count >= qty:
                break
            
            post_id = post["id"]
            title = post["title"]["rendered"][:60] if isinstance(post["title"], dict) else str(post["title"])[:60]
            current_tags = post.get("tags", [])
            
            # Para manchete/submanchete, evitar duplicatas
            if tag_slug in ("home-manchete", "home-submanchete"):
                if post_id in used_post_ids:
                    continue
            
            ok = add_tag_to_post(post_id, tag_id, current_tags)
            if ok:
                used_post_ids.add(post_id)
                tagged_count += 1
                total_tagged += 1
                print(f"  ✓ Post {post_id}: {title}")
            else:
                total_errors += 1
                print(f"  ✗ ERRO ao tagear post {post_id}")
            
            time.sleep(0.3)  # rate limiting
        
        if tagged_count < qty:
            print(f"  ⚠ Apenas {tagged_count}/{qty} posts tagueados")
        
        print()
    
    print("=" * 60)
    print(f"Total tagueados: {total_tagged} | Erros: {total_errors}")
    if total_errors == 0:
        print("✓ Seed completo! Pode aplicar o novo tdc_content.")
    else:
        print("⚠ Houve erros — verifique antes de aplicar o tdc_content.")


if __name__ == "__main__":
    main()
