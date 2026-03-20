#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reorganizar Homepage - Brasileira.news
Modifica o tdc_content para:
1. Mapear category_ids em cada bloco de posts
2. Corrigir links button_url
3. Substituir labels demo por labels reais
"""

import re
import sys

# ============================================================
# MAPEAMENTO DE CATEGORIAS por ordem editorial (mais quente → menos quente)
# ============================================================
# Posição 1-2: Big Grid (hero) = sem categoria (puxa tudo), os últimos posts mais recentes
# Posição 3: Política & Poder (71) - 869 posts  
# Posição 4: Economia & Negócios (72) - 499 posts
# Posição 5: Tecnologia (129) - 1429 posts
# Posição 6: Entretenimento (122) - 734 posts
# Posição 7: Esportes (81) - 573 posts
# Posição 8: Internacional (88) - 553 posts
# Posição 9: Justiça & Direito (73) - 384 posts
# Posição 10: Meio Ambiente (136) - 625 posts
# Posição 11: Saúde (74) - 145 posts
# Posição 12: Infraestrutura (78) - 775 posts
# Posição 13: Cultura (79) - 250 posts
# Posição 14 (sidebar/footer): Sociedade (76) - 207 posts

# Read the backup
with open('/home/bitnami/homepage_tdc_backup.txt', 'r', encoding='utf-8') as f:
    content = f.read().strip()

print(f"Tamanho original: {len(content)} bytes")

# ============================================================
# STEP 1: Assign category_ids to each block sequentially
# ============================================================

# Category assignments in order of appearance
# First 2 big_grid blocks: keep empty (hero shows all latest)
# Then flex_block_1 and flex_block_4 blocks get categories
CATEGORY_IDS_BY_POSITION = {
    # big_grid_flex_1 blocks (hero) - positions 0,1
    0: '',       # Hero big grid - all categories
    1: '',       # Second big grid (if any) - keep as is
    # flex blocks - positions 2 onwards  
    2: '71',     # Política & Poder
    3: '72',     # Economia & Negócios
    4: '129',    # Segmentos de Tecnologia
    5: '122',    # Entretenimento & Famosos
    6: '81',     # Esportes
    7: '88',     # Internacional
    8: '73',     # Justiça & Direito
    9: '136',    # Meio Ambiente
    10: '74',    # Saúde
    11: '78',    # Infraestrutura & Cidades
    12: '79',    # Cultura
    13: '76',    # Sociedade & Direitos Humanos
}

# Track positions of all post-displaying blocks
block_pattern = r'\[(td_flex_block_\d+|td_block_big_grid_flex_\d+)([^\]]*?)\]'
block_positions = []

for m in re.finditer(block_pattern, content):
    block_positions.append({
        'start': m.start(),
        'end': m.end(),
        'full_match': m.group(0),
        'block_type': m.group(1),
        'attrs': m.group(2),
    })

print(f"Encontrados {len(block_positions)} blocos de posts")

# Apply category_ids
new_content = content
offset_delta = 0  # Track position shifts from replacements

for i, block in enumerate(block_positions):
    cat_id = CATEGORY_IDS_BY_POSITION.get(i, '')
    
    old_block = block['full_match']
    
    if f'category_id=""' in old_block:
        new_block = old_block.replace('category_id=""', f'category_id="{cat_id}"')
    elif 'category_id=' not in old_block:
        # Add category_id if not present
        new_block = old_block[:-1] + f' category_id="{cat_id}"]'
    else:
        new_block = old_block
    
    if old_block != new_block:
        adjusted_start = block['start'] + offset_delta
        adjusted_end = block['end'] + offset_delta
        new_content = new_content[:adjusted_start] + new_block + new_content[adjusted_end:]
        offset_delta += len(new_block) - len(old_block)
        print(f"  Bloco {i+1} ({block['block_type']}): category_id=\"\" -> category_id=\"{cat_id}\"")
    else:
        print(f"  Bloco {i+1} ({block['block_type']}): sem mudança (cat_id={cat_id})")

# ============================================================
# STEP 2: Fix button_url links pointing to demo categories
# ============================================================
BUTTON_URL_REPLACEMENTS = {
    'category/news/politics/': 'category/politica-poder/',
    'category/food/': 'category/economia-negocios/',
    'category/women/': 'category/entretenimento-famosos/',
    'category/celebrity/': 'category/esportes-modalidades/',
    'category/travel/': 'category/internacional/',
    'category/music/': 'category/cultura/',
}

for old_url, new_url in BUTTON_URL_REPLACEMENTS.items():
    count = new_content.count(f'button_url="{old_url}"')
    if count > 0:
        new_content = new_content.replace(f'button_url="{old_url}"', f'button_url="{new_url}"')
        print(f"  button_url: \"{old_url}\" -> \"{new_url}\" ({count}x)")

# ============================================================
# STEP 3: Fix base64-encoded section labels 
# ============================================================
import base64
import urllib.parse

# Map demo labels to real editorial labels
LABEL_REPLACEMENTS = {
    'Food': 'Política & Poder',
    'Destinations': 'Mais Lidas',
    'Travel': 'Internacional',
    'Music': 'Cultura',
    'Celebrity': 'Esportes',
    'Women': 'Entretenimento',
    'Newsletter': 'Newsletter',
}

# Find and replace base64-encoded description labels in tdm_block_inline_text
desc_pattern = r'(description=")([A-Za-z0-9+/=]{4,})(")'

def replace_b64_desc(match):
    prefix = match.group(1)
    b64_val = match.group(2)
    suffix = match.group(3)
    
    try:
        decoded = base64.b64decode(b64_val).decode('utf-8')
        decoded_text = urllib.parse.unquote(decoded).strip()
        
        # Check if it's a known demo label to replace
        for demo_label, real_label in LABEL_REPLACEMENTS.items():
            if decoded_text == demo_label:
                new_encoded = base64.b64encode(urllib.parse.quote(real_label).encode()).decode()
                print(f"  Label B64: \"{decoded_text}\" -> \"{real_label}\"")
                return prefix + new_encoded + suffix
    except:
        pass
    
    return match.group(0)

new_content = re.sub(desc_pattern, replace_b64_desc, new_content)

# ============================================================
# STEP 4: Write output
# ============================================================
output_file = '/home/bitnami/homepage_tdc_new.txt'
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"\nTamanho novo: {len(new_content)} bytes")
print(f"Arquivo salvo: {output_file}")

# Verify the changes
remaining_empty = new_content.count('category_id=""')
print(f"\nVerificação: {remaining_empty} blocos ainda com category_id vazio")
# Only the hero grids should have empty (positions 0,1) 

# Count categories assigned
for cat_id in ['71', '72', '129', '122', '81', '88', '73', '136', '74', '78', '79', '76']:
    count = new_content.count(f'category_id="{cat_id}"')
    if count > 0:
        print(f"  category_id=\"{cat_id}\" aparece {count}x")
