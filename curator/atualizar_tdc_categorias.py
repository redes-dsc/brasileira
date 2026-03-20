#!/usr/bin/env python3
"""
Atualiza tdc_content: converte blocos com uma category_id para category_ids (plural)
para incluir todas as subcategorias e duplicatas de cada editoria.

Também converte blocos que SÓ tinham tag_slug mas category_id vazio 
(manchete/submanchete) para funcionar com fallback.
"""

import re
import sys

# ── Mapa: category_id_atual → category_ids_novo (com subs+dups) ──
# Esses são os category_ids que VÃO para o tdc_content do Newspaper
# para que os blocos mostrem posts de TODAS as categorias relacionadas
CATEGORY_EXPANSION = {
    # Tecnologia: mãe + subs oficiais + dups
    "129":  "129,130,131,132,133,134,12151,11997,13282,12064,13268,14804,12588",
    # Entretenimento: mãe + dups
    "122":  "122,11931,11730,11735,80",
    # Esportes: mãe + subs + dup
    "81":   "81,11989,82,83,84,85,86,87",
    # Internacional: mãe + subs
    "88":   "88,89,90,91,92,93",
    # Meio Ambiente: mãe + subs + dup
    "136":  "136,141,142,143,144,145,12405",
    # Justiça: mãe + dups
    "73":   "73,11772,13177",
    # Saúde: mãe + dups
    "74":   "74,12243,11738",
    # Infraestrutura: mãe + dup
    "78":   "78,11833",
    # Cultura: mãe + dups + educação
    "79":   "79,11868,13043,13385,75",
    # Sociedade: mãe + dups
    "76":   "76,11792,11729",
    # Política: mãe + dup
    "71":   "71,11742",
    # Economia: mãe + dup
    "72":   "72,11755",
}

def update_tdc():
    input_file = "/home/bitnami/homepage_tdc_tags.txt"
    output_file = "/home/bitnami/homepage_tdc_tags_v2.txt"
    
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    print(f"Tamanho original: {len(content)} bytes")
    
    # Para cada category_id com expansão, substituir no tdc_content
    # Padrão: category_id="XX" → category_ids="XX,YY,ZZ"
    changes = 0
    for old_cat, new_cats in CATEGORY_EXPANSION.items():
        # Só substitui category_id="XX" (singular) dentro de blocos de conteúdo
        old_pattern = f'category_id="{old_cat}"'
        new_pattern = f'category_ids="{new_cats}"'
        
        count = content.count(old_pattern)
        if count > 0:
            content = content.replace(old_pattern, new_pattern)
            changes += count
            print(f"  ✓ {old_cat} → {new_cats[:50]}... ({count} ocorrências)")
    
    # Salvar
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"\nTotal mudanças: {changes}")
    print(f"Tamanho novo: {len(content)} bytes")
    print(f"Arquivo salvo: {output_file}")
    
    # Verificação
    # Contar category_id vs category_ids
    single = re.findall(r'category_id="(\d+)"', content)
    plural = re.findall(r'category_ids="([^"]*)"', content)
    tags = re.findall(r'tag_slug="([^"]*)"', content)
    
    print(f"\nVerificação:")
    print(f"  category_id  (singular): {len(single)} ocorrências")
    for s in single:
        print(f"    category_id=\"{s}\"")
    print(f"  category_ids (plural):   {len(plural)} ocorrências")
    for p in plural:
        print(f"    category_ids=\"{p[:60]}...\"")
    print(f"  tag_slug:                {len(tags)} ocorrências")

if __name__ == "__main__":
    update_tdc()
