#!/usr/bin/env python3
"""
Migra homepage de category_id para tag_slug.
- Blocos 1-2 (manchete/sub): tag_slug puro (sem category_id)
- Blocos 3-14 (editorias): mantém category_id + adiciona tag_slug
"""

import re
import sys

# ── Mapa: posição → (category_id_manter, tag_slug_adicionar) ──
# Posições 0-1: manchete/submanchete — liberdade total (sem category_id)
# Posições 2-13: editorias — coerência temática (manter category_id)
TAG_MAP = {
    0:  ("",    "home-manchete"),
    1:  ("",    "home-submanchete"),
    2:  ("71",  "home-politica"),
    3:  ("72",  "home-economia"),
    4:  ("129", "home-tecnologia"),
    5:  ("122", "home-entretenimento"),
    6:  ("81",  "home-ciencia"),
    7:  ("88",  "home-internacional"),
    8:  ("73",  "home-saude"),
    9:  ("136", "home-meioambiente"),
    10: ("74",  "home-bemestar"),
    11: ("78",  "home-infraestrutura"),
    12: ("79",  "home-cultura"),
    13: ("76",  "home-sociedade"),
}

# Category names for logging
CAT_NAMES = {
    "": "(todos)", "71": "Política", "72": "Economia", "129": "Tecnologia",
    "122": "Entretenimento", "81": "Ciência", "88": "Internacional",
    "73": "Saúde", "136": "Meio Ambiente", "74": "Saúde/Bem-Estar",
    "78": "Infraestrutura", "79": "Cultura", "76": "Sociedade",
}

def migrate():
    # Read current tdc_content
    input_file = "/tmp/homepage_tdc_raw.txt"
    output_file = "/home/bitnami/homepage_tdc_tags.txt"
    
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    print(f"Tamanho original: {len(content)} bytes")
    
    # Find all post-displaying blocks in order
    block_pattern = r'\[(td_flex_block_\d+|td_block_big_grid_flex_\d+)([^\]]*)\]'
    blocks = []
    for m in re.finditer(block_pattern, content):
        blocks.append({
            "start": m.start(),
            "end": m.end(),
            "full_match": m.group(0),
            "block_type": m.group(1),
            "attrs": m.group(2),
        })
    
    print(f"Encontrados {len(blocks)} blocos de posts")
    
    if len(blocks) != 14:
        print(f"AVISO: Esperados 14 blocos, encontrados {len(blocks)}. Continuando com cautela...")
    
    # Apply tag_slug to each block
    new_content = content
    offset_delta = 0
    
    for i, block in enumerate(blocks):
        if i not in TAG_MAP:
            print(f"  [{i+1:2d}] {block['block_type']:<30s} — SEM MAPEAMENTO, pulando")
            continue
        
        expected_cat, tag_slug = TAG_MAP[i]
        old_block = block["full_match"]
        new_block = old_block
        
        # Check: block already has tag_slug?
        if f'tag_slug="' in old_block:
            print(f"  [{i+1:2d}] {block['block_type']:<30s} — JÁ TEM tag_slug, pulando")
            continue
        
        # For manchete/submanchete (pos 0-1): ensure category_id="" (empty)
        if i <= 1:
            # These should have category_id="" — just add tag_slug
            new_block = new_block.replace(
                f'category_id="{expected_cat}"',
                f'category_id="" tag_slug="{tag_slug}"'
            )
            # If category_id wasn't found with expected value, try empty
            if 'tag_slug=' not in new_block:
                new_block = re.sub(
                    r'category_id="[^"]*"',
                    f'category_id="" tag_slug="{tag_slug}"',
                    new_block,
                    count=1,
                )
        else:
            # For editorial sections (pos 2-13): keep category_id, add tag_slug after it
            if f'category_id="{expected_cat}"' in old_block:
                new_block = old_block.replace(
                    f'category_id="{expected_cat}"',
                    f'category_id="{expected_cat}" tag_slug="{tag_slug}"'
                )
            else:
                # Fallback: add tag_slug after any category_id
                new_block = re.sub(
                    r'(category_id="[^"]*")',
                    rf'\1 tag_slug="{tag_slug}"',
                    old_block,
                    count=1,
                )
        
        if old_block == new_block:
            print(f"  [{i+1:2d}] {block['block_type']:<30s} — SEM MUDANÇA (verificar manualmente)")
            continue
        
        # Apply replacement
        adjusted_start = block["start"] + offset_delta
        adjusted_end = block["end"] + offset_delta
        new_content = new_content[:adjusted_start] + new_block + new_content[adjusted_end:]
        offset_delta += len(new_block) - len(old_block)
        
        cat_name = CAT_NAMES.get(expected_cat, expected_cat)
        print(f"  [{i+1:2d}] {block['block_type']:<30s} cat={expected_cat:<5s} ({cat_name:<15s}) + tag_slug=\"{tag_slug}\"")
    
    # Write output
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print(f"\nTamanho novo: {len(new_content)} bytes (delta: {len(new_content) - len(content):+d})")
    print(f"Arquivo salvo: {output_file}")
    
    # Verification
    tag_slugs_found = re.findall(r'tag_slug="([^"]*)"', new_content)
    print(f"\nVerificação: {len(tag_slugs_found)} tag_slugs encontrados:")
    for ts in tag_slugs_found:
        print(f"  ✓ tag_slug=\"{ts}\"")
    
    # Verify category_ids still present for editorial blocks
    cat_ids_found = re.findall(r'category_id="(\d+)"', new_content)
    print(f"\ncategory_ids mantidos: {len(cat_ids_found)}")
    for cid in sorted(set(cat_ids_found)):
        count = cat_ids_found.count(cid)
        name = CAT_NAMES.get(cid, "?")
        print(f"  ✓ category_id=\"{cid}\" ({name}) — {count}x")


if __name__ == "__main__":
    migrate()
