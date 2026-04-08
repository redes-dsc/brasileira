#!/usr/bin/env python3
"""
Categorias editoriais — descobertas automaticamente via WP REST API.
Última atualização: 2026-03-31

Para atualizar: python -m scripts.discover_categories (ou executar Steps 1-3 do Task #15)
"""

# =============================================================================
# TIER 1 — Editorias principais (presentes na homepage ou alto volume recente)
# =============================================================================
TIER_1_CATEGORIES = {
    # --- Blocos da Homepage (category_id em td_flex_block) ---
    "tecnologia": {"id": 129, "name": "Tecnologia", "tier": 1},
    "esportes": {"id": 11989, "name": "Esportes", "tier": 1},
    "internacional": {"id": 88, "name": "Internacional", "tier": 1},
    "economia": {"id": 15661, "name": "Economia & Negócios", "tier": 1},
    "politica": {"id": 71, "name": "Política", "tier": 1},
    "cultura": {"id": 79, "name": "Cultura", "tier": 1},
    "entretenimento": {"id": 11931, "name": "Entretenimento", "tier": 1},
    "meio_ambiente_legado": {"id": 136, "name": "Meio Ambiente", "tier": 1},
    
    # --- Alto volume recente (>10 posts em 48h) ---
    "meio_ambiente": {"id": 136, "name": "Meio Ambiente", "tier": 1},
    "agronegocio": {"id": 135, "name": "Agronegócio", "tier": 1},
    "direito_justica": {"id": 73, "name": "Justiça", "tier": 1},
    "seguranca_defesa": {"id": 11792, "name": "Segurança & Defesa", "tier": 1},
    "ciencia_inovacao": {"id": 11868, "name": "Ciência & Inovação", "tier": 1},
    "saude_bem_estar": {"id": 74, "name": "Saúde", "tier": 1},
    "educacao_cultura": {"id": 75, "name": "Educação", "tier": 1},
    "infraestrutura": {"id": 11833, "name": "Infraestrutura & Urbanismo", "tier": 1},
    "energia_clima": {"id": 13177, "name": "Energia & Clima", "tier": 1},
    "segmentos_tecnologia": {"id": 129, "name": "Tecnologia (sub merged)", "tier": 1},
    "futebol": {"id": 82, "name": "Futebol", "tier": 1},
    "oriente_medio": {"id": 93, "name": "Oriente Médio", "tier": 1},
    "musica": {"id": 126, "name": "Música", "tier": 1},
    
    # --- Estados com volume significativo ---
    "para": {"id": 108, "name": "Pará", "tier": 1},
    "paraiba": {"id": 109, "name": "Paraíba", "tier": 1},
    "parana": {"id": 110, "name": "Paraná", "tier": 1},
    "sao_paulo": {"id": 119, "name": "São Paulo", "tier": 1},
}

# =============================================================================
# TIER 2 — Editorias secundárias (volume moderado ou categorias legadas)
# =============================================================================
TIER_2_CATEGORIES = {
    # --- Categorias principais legadas (estrutura antiga WP) ---
    "brasil": {"id": 78, "name": "Brasil", "tier": 2},
    "poder_legado": {"id": 71, "name": "Poder", "tier": 2},
    "dinheiro_legado": {"id": 72, "name": "Dinheiro", "tier": 2},
    "justica_direito": {"id": 73, "name": "Justiça & Direito", "tier": 2},
    "saude": {"id": 74, "name": "Saúde", "tier": 2},
    "educacao_ciencia": {"id": 75, "name": "Educação, Ciência & Tecnologia", "tier": 2},
    "sociedade": {"id": 76, "name": "Sociedade", "tier": 2},
    
    # --- Entretenimento e cultura ---
    "famosos": {"id": 122, "name": "Famosos", "tier": 2},
    "celebridades": {"id": 11729, "name": "Celebridades", "tier": 2},
    "turismo": {"id": 80, "name": "Turismo", "tier": 2},
    
    # --- Estados UF (volume menor) ---
    "estados_uf": {"id": 94, "name": "Estados (UF)", "tier": 2},
    "rio_de_janeiro": {"id": 113, "name": "Rio de Janeiro", "tier": 2},
    "rio_grande_sul": {"id": 115, "name": "Rio Grande do Sul", "tier": 2},
    "distrito_federal": {"id": 101, "name": "Distrito Federal", "tier": 2},
    "minas_gerais": {"id": 107, "name": "Minas Gerais", "tier": 2},
    "bahia": {"id": 99, "name": "Bahia", "tier": 2},
    "ceara": {"id": 100, "name": "Ceará", "tier": 2},
    "pernambuco": {"id": 111, "name": "Pernambuco", "tier": 2},
    "goias": {"id": 103, "name": "Goiás", "tier": 2},
    "santa_catarina": {"id": 118, "name": "Santa Catarina", "tier": 2},
    "amazonas": {"id": 98, "name": "Amazonas", "tier": 2},
    "maranhao": {"id": 104, "name": "Maranhão", "tier": 2},
    "mato_grosso_sul": {"id": 106, "name": "Mato Grosso do Sul", "tier": 2},
    "tocantins": {"id": 121, "name": "Tocantins", "tier": 2},
    
    # --- Internacional ---
    "europa": {"id": 90, "name": "Europa", "tier": 2},
    "africa": {"id": 92, "name": "África", "tier": 2},
    "americas": {"id": 89, "name": "Américas", "tier": 2},
    
    # --- Subcategorias legadas ---
    "dinheiro_2": {"id": 11755, "name": "Dinheiro", "tier": 2},
    "justica_2": {"id": 11772, "name": "Justiça", "tier": 2},
    "poder_2": {"id": 11742, "name": "Poder", "tier": 2},
    "cultura_2": {"id": 11738, "name": "Cultura", "tier": 2},
    "turismo_2": {"id": 11736, "name": "Turismo", "tier": 2},
    
    # --- Tech subcategorias ---
    "tech": {"id": 12151, "name": "Tech", "tier": 2},
    "ia": {"id": 130, "name": "Inteligência Artificial", "tier": 2},
    "telecomunicacoes": {"id": 137, "name": "Telecomunicações", "tier": 2},
    "tech_inovacao": {"id": 19953, "name": "Tecnologia & Inovação", "tier": 2},
    
    # --- Esportes subcategorias ---
    "futebol_internacional": {"id": 83, "name": "Futebol Internacional", "tier": 2},
    
    # --- Sistema ---
    "uncategorized": {"id": 1, "name": "Uncategorized", "tier": 2},
    
    # --- Outras categorias com posts recentes ---
    "direitos_justica_2": {"id": 13385, "name": "Direitos & Justiça", "tier": 2},
    "tech_software": {"id": 21967, "name": "Tecnologia & Software", "tier": 2},
    "cultura_entretenimento": {"id": 21679, "name": "Cultura & Entretenimento", "tier": 2},
}

# =============================================================================
# ALL CATEGORIES — Combinação de TIER 1 e TIER 2
# =============================================================================
CATEGORIES = {**TIER_1_CATEGORIES, **TIER_2_CATEGORIES}

# =============================================================================
# REVERSE LOOKUPS
# =============================================================================
# {id: name} — para converter ID numérico em nome legível
CATEGORY_BY_ID = {v["id"]: v["name"] for v in CATEGORIES.values()}

# {slug: {id, name, tier}} — para lookup por slug
CATEGORY_BY_SLUG = {k: v for k, v in CATEGORIES.items()}

# =============================================================================
# HOMEPAGE BLOCK IDS — IDs de categorias presentes nos blocos da homepage
# =============================================================================
# Esses são os category_id encontrados em td_flex_block na homepage
HOMEPAGE_CATEGORY_IDS = {
    15661,  # Economia & Negócios
    15285,  # Política & Poder
    88,     # Internacional
    129,    # Tecnologia
    11931,  # Entretenimento
    11989,  # Esportes
    15652,  # Meio Ambiente Legado
    79,     # Cultura
}

# =============================================================================
# CATEGORY_GROUPS — Subcategorias e categorias-irmãs por slot (homepage)
# =============================================================================
# Fonte: briefings/briefing-s5-fix-cursor-subcategorias.pplx.md
# Atualizar quando o WP ganhar novas subcategorias editoriais relevantes.

CATEGORY_GROUPS: dict[int, frozenset[int]] = {
    # Tecnologia (slot 129)
    129: frozenset(
        {
            129, 130, 131, 132, 133, 134, 137, 11868, 12151, 14804, 19953, 21967,
            13219, 13268, 13282,
        }
    ),
    # Internacional (88)
    88: frozenset({88, 89, 90, 91, 92, 93}),
    # Sustentabilidade / Meio Ambiente legado (15652) + 136 e filhos
    15652: frozenset({15652, 136, 13177, 141, 142, 143, 144, 145}),
    # Cultura (79)
    79: frozenset({79, 11738, 12405, 13043, 15339, 15650, 21679}),
    # Entretenimento (11931) + árvore 123
    11931: frozenset({11931, 122, 11729, 123, 124, 125, 126, 127, 128}),
    # Esportes (11989) + categorias irmãs
    11989: frozenset({11989, 82, 83, 84, 85, 86, 87}),
    # Economia (15661)
    15661: frozenset({15661, 72, 11755, 135, 11730, 138, 139, 140}),
    # Política (15285)
    15285: frozenset({15285, 71, 11734, 11742}),
}


def get_category_group(slot_category_id: int) -> frozenset[int]:
    """IDs de categoria WordPress que contam para o slot com `category_id` dado."""
    g = CATEGORY_GROUPS.get(slot_category_id)
    if g is not None:
        return g
    return frozenset({slot_category_id})


# Ordem de prioridade para rollup no prompt V2 (primeiro match ganha)
_HOMEPAGE_SLOT_CATEGORY_PRIORITY: tuple[int, ...] = (
    15661,
    71,
    88,
    129,
    11931,
    11989,
    136,
    79,
)


def canonical_slot_category_id_for_post(category_ids: set[int]) -> int | None:
    """
    Primeiro `category_id` de slot da homepage cujo grupo intersecta as categorias do post.
    Usado em `format_posts_pool_v2` para alinhar listagem ao `editorial_analyzer`.
    """
    if not category_ids:
        return None
    for slot_cat_id in _HOMEPAGE_SLOT_CATEGORY_PRIORITY:
        if category_ids & get_category_group(slot_cat_id):
            return slot_cat_id
    return None


# =============================================================================
# BACKWARD COMPATIBILITY — Alias para código legado
# =============================================================================
# Usado em wp_reader.py, homepage_editor.py, s5_editorial_worker.py
MAIN_CATEGORIES = {
    v["name"]: {"id": v["id"], "slug": k}
    for k, v in TIER_1_CATEGORIES.items()
}

# Adiciona mapeamento legado para nomes antigos usados no código
_LEGACY_NAME_MAP = {
    "Política": {"id": 71, "slug": "politica"},
    "Economia": {"id": 15661, "slug": "economia"},
    "Saúde": {"id": 74, "slug": "saude"},
    "Educação": {"id": 75, "slug": "educacao"},
    "Segurança": {"id": 11792, "slug": "seguranca_defesa"},
    "Justiça": {"id": 73, "slug": "justica"},
    "Brasil": {"id": 78, "slug": "brasil"},
    "Mundo": {"id": 88, "slug": "internacional"},
    "Cultura & Entretenimento": {"id": 79, "slug": "cultura"},
    "Tecnologia": {"id": 129, "slug": "tecnologia"},
    "Esportes": {"id": 11989, "slug": "esportes"},
    "Ciência & Meio Ambiente": {"id": 136, "slug": "meio_ambiente"},
}
MAIN_CATEGORIES.update(_LEGACY_NAME_MAP)
