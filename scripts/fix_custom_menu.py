#!/usr/bin/env python3
"""Fix the third menu (td-demo-custom-menu) in the footer bar"""
import requests, base64

WP_URL = "https://brasileira.news/wp-json/wp/v2"
AUTH_HEADERS = {
    'Authorization': f'Basic {base64.b64encode(b"iapublicador:nWgboohRWZGLv2d7ebQgkf80").decode()}',
    'Content-Type': 'application/json'
}

MENU_ID = 11725  # td-demo-custom-menu

# Get current items
r = requests.get(f"{WP_URL}/menu-items?menus={MENU_ID}&per_page=50", headers=AUTH_HEADERS, timeout=15)
items = r.json() if r.status_code == 200 else []
print(f"{len(items)} itens no menu custom:")

# Delete old items
for item in items:
    iid = item.get('id')
    title = item.get('title', {}).get('rendered', '?')
    dr = requests.delete(f"{WP_URL}/menu-items/{iid}?force=true", headers=AUTH_HEADERS, timeout=10)
    print(f"  {'✓' if dr.status_code == 200 else '✗'} Deletado: {title}")

# Create new items with editorial categories
NEW_ITEMS = [
    ('Home', None, 'https://brasileira.news/'),
    ('Política', 71, None),
    ('Economia', 72, None),
    ('Tecnologia', 129, None),
    ('Entretenimento', 122, None),
    ('Esportes', 81, None),
    ('Internacional', 88, None),
    ('Justiça', 73, None),
    ('Saúde', 74, None),
    ('Meio Ambiente', 136, None),
]

for title, cat_id, custom_url in NEW_ITEMS:
    if cat_id:
        cr = requests.get(f"{WP_URL}/categories/{cat_id}", headers=AUTH_HEADERS, timeout=10)
        url = cr.json().get('link', '') if cr.status_code == 200 else ''
        payload = {
            'title': title, 'url': url, 'menus': MENU_ID,
            'object': 'category', 'object_id': cat_id,
            'type': 'taxonomy', 'status': 'publish',
        }
    else:
        payload = {
            'title': title, 'url': custom_url, 'menus': MENU_ID,
            'type': 'custom', 'status': 'publish',
        }
    
    nr = requests.post(f"{WP_URL}/menu-items", headers=AUTH_HEADERS, json=payload, timeout=10)
    print(f"  {'✓' if nr.status_code == 201 else '✗'} Criado: {title}")

print("Concluído!")
