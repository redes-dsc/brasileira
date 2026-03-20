"""

curator_config.py

Configurações, pesos editoriais e constantes do Home Curator Agent.

Portal: brasileira.news

"""



import os

from dataclasses import dataclass, field

from typing import Dict, List



# ─────────────────────────────────────────────

# CREDENCIAIS (via variáveis de ambiente)

# ─────────────────────────────────────────────

WP_BASE_URL: str = os.environ.get("WP_BASE_URL", "https://brasileira.news/wp-json/wp/v2")

WP_USER: str = os.environ.get("WP_USER", "")

WP_APP_PASSWORD: str = os.environ.get("WP_APP_PASSWORD", "")



GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

GEMINI_TIMEOUT: int = int(os.environ.get("GEMINI_TIMEOUT", "20"))



# ─────────────────────────────────────────────

# JANELA DE TEMPO E CICLO

# ─────────────────────────────────────────────

CURATOR_WINDOW_HOURS: int = int(os.environ.get("CURATOR_WINDOW_HOURS", "4"))

CURATOR_CYCLE_MINUTES: int = int(os.environ.get("CURATOR_CYCLE_MINUTES", "30"))



# ─────────────────────────────────────────────

# LIMITES LLM

# ─────────────────────────────────────────────

MAX_LLM_CALLS_PER_CYCLE: int = int(os.environ.get("MAX_LLM_CALLS_PER_CYCLE", "50"))

WP_API_MAX_RPM: int = 60          # max requisições/minuto à WP REST API

WP_FETCH_PAGE_SIZE: int = 100     # per_page na busca



# ─────────────────────────────────────────────

# TAGS DE DESTAQUE

# ─────────────────────────────────────────────

HIGHLIGHT_TAGS: List[str] = [

    "home-manchete",

    "home-destaque",

    "home-recentes",

    "editoria-destaque",

    "home-especial",

]



# ─────────────────────────────────────────────

# POSIÇÕES E REGRAS

# ─────────────────────────────────────────────

@dataclass

class PositionConfig:

    tag: str

    count: int

    min_score: int

    description: str

    extra_rules: Dict = field(default_factory=dict)





POSITIONS: List[PositionConfig] = [

    PositionConfig(

        tag="home-manchete",

        count=1,

        min_score=80,

        description="Manchete principal",

        extra_rules={"prefer_consolidated": True, "prefer_official": True},

    ),

    PositionConfig(

        tag="home-destaque",

        count=4,

        min_score=65,

        description="Chamadas de destaque",

        extra_rules={"min_different_editorias": 3},

    ),

    PositionConfig(

        tag="home-recentes",

        count=8,

        min_score=50,

        description="Últimas relevantes",

        extra_rules={"order": "score_desc"},

    ),

    PositionConfig(

        tag="home-especial",

        count=2,

        min_score=70,

        description="Matérias consolidadas especiais",

        extra_rules={"require_tag": "consolidada", "override_priority": True},

    ),

]



EDITORIA_DESTAQUE_CONFIG = PositionConfig(

    tag="editoria-destaque",

    count=2,           # por editoria

    min_score=55,

    description="Destaques por editoria",

)



# ─────────────────────────────────────────────

# FILTROS OBRIGATÓRIOS (ELIMINATÓRIOS)

# ─────────────────────────────────────────────

FILTER_MIN_SCORE: int = 50

FILTER_MIN_WORDS: int = 200

FILTER_MAX_SAME_CATEGORY: int = 2   # máx posts da mesma cat no destaque

FILTER_MAX_SAME_SOURCE: int = 1     # máx posts do mesmo veículo no TOP 5



# ─────────────────────────────────────────────

# PESOS DO SCORER (critérios objetivos)

# ─────────────────────────────────────────────

SCORE_WEIGHTS: Dict[str, int] = {

    # Positivos

    "official_source": 30,          # fonte gov.br, leg.br, jus.br

    "consolidated_tag": 20,         # tag "consolidada"

    "high_interest_theme": 15,      # economia, política, saúde

    "recent_post_1h": 10,           # < 1h de publicação

    "has_featured_image": 10,       # tem imagem de destaque

    "title_seo_length": 5,          # título entre 50-80 chars

    "has_excerpt": 5,               # excerpt preenchido

    "has_enough_tags": 5,           # >= 3 tags



    # Negativos

    "international_no_br": -20,     # fonte internacional sem contexto BR

    "niche_theme": -15,             # entretenimento, esportes internacionais

    "short_post": -10,              # < 300 palavras

    "no_featured_image": -10,       # sem imagem

    "short_title": -5,              # título < 30 chars

}



# Temas de alto interesse nacional

HIGH_INTEREST_THEMES: List[str] = [

    "economia", "política", "saúde", "segurança", "educação",

    "meio ambiente", "justiça", "legislação", "previdência",

    "inflação", "desemprego", "brasil", "governo federal",

]



# Temas de nicho (penalidade)

NICHE_THEMES: List[str] = [

    "entretenimento", "celebridade", "reality show", "novela",

    "futebol europeu", "nba", "nfl", "fórmula 1 internacional",

    "k-pop", "anime",

]



# Domínios de fontes oficiais

OFFICIAL_SOURCE_DOMAINS: List[str] = [

    "gov.br", "leg.br", "jus.br", "senado.leg.br",

    "camara.leg.br", "stf.jus.br", "tst.jus.br",

    "planalto.gov.br", "agenciabrasil.ebc.com.br",

]



# ─────────────────────────────────────────────

# LOGGING

# ─────────────────────────────────────────────

LOG_DIR: str = os.environ.get("LOG_DIR", "/home/bitnami/logs")

DB_LOG_TABLE: str = "wp_7_curator_log"



# Conexão MariaDB (para log)

DB_HOST: str = os.environ.get("DB_HOST", "127.0.0.1")

DB_PORT: int = int(os.environ.get("DB_PORT", "3306"))

DB_NAME: str = os.environ.get("DB_NAME", "bitnami_wordpress")

DB_USER: str = os.environ.get("DB_USER", "bn_wordpress")

DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")
