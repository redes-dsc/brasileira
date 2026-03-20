#!/usr/bin/env python3
"""
Cria as TAGs editoriais para curadoria da homepage no WordPress.
Executar UMA VEZ antes de ativar o agente curador.
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

# ── TAGs editoriais a criar ───────────────────────────
EDITORIAL_TAGS = [
    {"name": "Home: Manchete",       "slug": "home-manchete"},
    {"name": "Home: Submanchete",    "slug": "home-submanchete"},
    {"name": "Home: Política",       "slug": "home-politica"},
    {"name": "Home: Economia",       "slug": "home-economia"},
    {"name": "Home: Tecnologia",     "slug": "home-tecnologia"},
    {"name": "Home: Entretenimento", "slug": "home-entretenimento"},
    {"name": "Home: Ciência",        "slug": "home-ciencia"},
    {"name": "Home: Internacional",  "slug": "home-internacional"},
    {"name": "Home: Saúde",          "slug": "home-saude"},
    {"name": "Home: Meio Ambiente",  "slug": "home-meioambiente"},
    {"name": "Home: Bem-Estar",      "slug": "home-bemestar"},
    {"name": "Home: Infraestrutura", "slug": "home-infraestrutura"},
    {"name": "Home: Cultura",        "slug": "home-cultura"},
    {"name": "Home: Sociedade",      "slug": "home-sociedade"},
    {"name": "Home: Especial",       "slug": "home-especial"},
    {"name": "Home: Urgente",        "slug": "home-urgente"},
    {"name": "Consolidada",          "slug": "consolidada"},
]


def get_or_create_tag(name: str, slug: str) -> dict:
    """Busca tag existente ou cria nova. Retorna {id, name, slug}."""
    # Tentar buscar primeiro
    resp = requests.get(
        f"{WP_API_BASE}/tags",
        params={"slug": slug, "per_page": 1},
        auth=AUTH,
        timeout=15,
    )
    if resp.status_code == 200 and resp.json():
        tag = resp.json()[0]
        return {"id": tag["id"], "name": tag["name"], "slug": tag["slug"], "status": "existente"}

    # Criar
    resp = requests.post(
        f"{WP_API_BASE}/tags",
        json={"name": name, "slug": slug},
        auth=AUTH,
        timeout=15,
    )
    if resp.status_code == 201:
        tag = resp.json()
        return {"id": tag["id"], "name": tag["name"], "slug": tag["slug"], "status": "criada"}
    else:
        return {"id": None, "name": name, "slug": slug, "status": f"ERRO {resp.status_code}: {resp.text[:200]}"}


def main():
    print("=" * 60)
    print("  CRIAÇÃO DE TAGs EDITORIAIS — brasileira.news")
    print("=" * 60)
    print()

    results = {}
    errors = 0

    for tag_def in EDITORIAL_TAGS:
        result = get_or_create_tag(tag_def["name"], tag_def["slug"])
        results[tag_def["slug"]] = result

        icon = "✓" if result["id"] else "✗"
        print(f"  {icon} {tag_def['slug']:<25s} → ID={result['id']:<6} [{result['status']}]")

        if not result["id"]:
            errors += 1

        time.sleep(0.5)  # rate limiting

    print()
    print(f"Total: {len(EDITORIAL_TAGS)} tags | Sucesso: {len(EDITORIAL_TAGS) - errors} | Erros: {errors}")

    if errors == 0:
        print("\n✓ Todas as tags criadas com sucesso!")
        # Salvar mapa slug → id para uso posterior
        tag_map = {slug: info["id"] for slug, info in results.items()}
        print("\nMapa TAG_SLUG → ID:")
        for slug, tid in tag_map.items():
            print(f'    "{slug}": {tid},')
    else:
        print("\n✗ Houve erros. Verifique acima.")
        sys.exit(1)


if __name__ == "__main__":
    main()
