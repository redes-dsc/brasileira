"""
Configurações do Motor Consolidado (Raia 3) — brasileira.news
Definições de portais, seletores CSS, thresholds e limites operacionais.
"""

import os
import sys
from pathlib import Path

# Adicionar motor_rss e motor_scrapers ao path para reutilizar módulos
_BITNAMI = Path("/home/bitnami")
sys.path.insert(0, str(_BITNAMI / "motor_rss"))
sys.path.insert(0, str(_BITNAMI / "motor_scrapers"))
sys.path.insert(0, str(_BITNAMI))

# Re-exportar config do motor_rss (carrega .env com WP, DB, LLM keys etc.)
from dotenv import load_dotenv
load_dotenv(_BITNAMI / "motor_rss" / ".env")

# ── Portais Monitorados ─────────────────────────────────

TIER1_PORTALS = [
    {
        "name": "G1",
        "home_url": "https://g1.globo.com",
        "ultimas_url": "https://g1.globo.com/ultimas-noticias/",
        "selectors": [
            "a.feed-post-link",
            ".feed-post-body-title a",
            "h2 a",
        ],
    },
    {
        "name": "UOL",
        "home_url": "https://www.uol.com.br",
        "ultimas_url": "https://www.uol.com.br/noticias/",
        "selectors": [
            ".thumbnail-standard-wrapper h3 a",
            "h3 a",
            "h2 a",
        ],
    },
    {
        "name": "Folha",
        "home_url": "https://www1.folha.uol.com.br",
        "ultimas_url": "https://www1.folha.uol.com.br/ultimas-noticias/",
        "selectors": [
            ".c-headline__title a",
            ".c-main-headline__title a",
            "h2 a",
        ],
    },
    {
        "name": "CNN Brasil",
        "home_url": "https://www.cnnbrasil.com.br",
        "ultimas_url": "https://www.cnnbrasil.com.br/ultimas-noticias/",
        "selectors": [
            "h3.news-item-header__title a",
            "h2 a",
            "h3 a",
        ],
    },
    {
        "name": "Metrópoles",
        "home_url": "https://www.metropoles.com",
        "ultimas_url": "https://www.metropoles.com/ultimas-noticias",
        "selectors": [
            "h2.title a",
            "h3.title a",
            "h2 a",
        ],
    },
    {
        "name": "Poder360",
        "home_url": "https://www.poder360.com.br",
        "ultimas_url": "https://www.poder360.com.br",
        "selectors": [
            ".listagem-item__nome a",
            "article h2 a",
            "h3 a",
            "h2 a",
        ],
    },
    {
        "name": "Estadão",
        "home_url": "https://www.estadao.com.br",
        "ultimas_url": "https://www.estadao.com.br/ultimas/",
        "selectors": [
            ".title a",
            "h2 a",
            "h3 a",
            ".headline a"
        ],
    },
]

TIER2_PORTALS = [
    {
        "name": "Valor Econômico",
        "home_url": "https://valor.globo.com",
        "ultimas_url": "https://valor.globo.com/ultimas-noticias/",
        "selectors": [
            "a.feed-post-link",
            ".feed-post-body-title a",
            "h2 a",
        ],
    },
    {
        "name": "Agência Brasil",
        "home_url": "https://agenciabrasil.ebc.com.br",
        "ultimas_url": "https://agenciabrasil.ebc.com.br/ultimas",
        "rss_url": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml",
        "selectors": [
            ".views-row h2 a",
            "h2 a",
        ],
    },
    {
        "name": "Senado",
        "home_url": "https://www12.senado.leg.br/noticias",
        "ultimas_url": "https://www12.senado.leg.br/noticias/ultimas",
        "selectors": [
            "div.border-bottom-d a",
            ".pt-1.pb-2 a",
            ".sf-item-header-title a",
            ".tileHeadline a",
            "h2 a",
        ],
    },
    {
        "name": "Câmara",
        "home_url": "https://www.camara.leg.br/noticias",
        "ultimas_url": "https://www.camara.leg.br/noticias/ultimas",
        "selectors": [
            ".g-chamada__titulo a",
            "h3 a",
            "h2 a",
        ],
    },
]

MAIS_LIDAS_PORTALS = [
    {
        "name": "G1",
        "url": "https://g1.globo.com/",
        "selectors": [
            ".bastian-most-read a",
            "ol.most-read li a",
            '[class*="mais-lidas"] a',
            '[class*="most-read"] a',
        ],
        "section": "mais_lidas",
    },
    {
        "name": "UOL",
        "url": "https://www.uol.com.br/",
        "rss_url": "http://rss.uol.com.br/feed/noticias.xml",
        "selectors": [
            ".most-read a",
            '[class*="mais-lidas"] a',
            '[data-tb-region="mais-lidas"] a',
        ],
        "section": "mais_lidas",
    },
    {
        "name": "Metrópoles",
        "url": "https://www.metropoles.com/",
        "selectors": [
            ".most-read-wrapper a",
            '[class*="mais-lidas"] a',
            ".most-read a",
        ],
        "section": "mais_lidas",
    },
]

# ── Stopwords Português ─────────────────────────────────

STOPWORDS_PT = {
    "a", "à", "ao", "aos", "as", "às", "ante", "após", "até",
    "com", "contra", "da", "das", "de", "desde", "do", "dos",
    "e", "é", "ela", "elas", "ele", "eles", "em", "entre",
    "era", "essa", "essas", "esse", "esses", "esta", "estas",
    "este", "estes", "eu", "foi", "for", "foram", "há",
    "isso", "isto", "já", "lhe", "lhes", "mais", "mas",
    "me", "meu", "minha", "na", "nas", "no", "nos", "nós",
    "num", "numa", "não", "o", "os", "ou", "para", "pela",
    "pelas", "pelo", "pelos", "per", "pode", "por", "qual",
    "quando", "que", "quem", "se", "sem", "ser", "será",
    "seu", "seus", "sob", "sobre", "sua", "suas", "são",
    "também", "te", "tem", "ter", "teu", "tua", "tu", "um",
    "uma", "umas", "uns", "vai", "vão", "você", "vos",
    "diz", "dizer", "disse", "como", "pode", "ainda", "novo",
    "nova", "após", "segundo", "afirma", "aponta",
}

# ── Thresholds ──────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.45
MIN_SOURCES_TRENDING = 1
MIN_CONTENT_WORDS = 150
MAX_CONTENT_WORDS_PAY = 100  # abaixo disso = paywall
MIN_SYNTHESIS_WORDS = 600
MAX_SYNTHESIS_WORDS = 1200
MAX_PLAGIARISM_RATIO = 0.40
MAX_SOURCES_PER_TOPIC = 7
MIN_SOURCES_PER_TOPIC = 1

# ── Limites operacionais ────────────────────────────────

MAX_ARTICLES_PER_CYCLE = 3
DEDUP_WINDOW_HOURS = 4
THEME_COOLDOWN_HOURS = 6
ARTICLE_MIN_INTERVAL_HOURS = 1

# ── Publicação ──────────────────────────────────────────

ID_REDACAO = 4  # "Redação Brasileira"
TAG_CONSOLIDADA = "consolidada"
TAG_HOME_ESPECIAL = "home-especial"
FEED_NAME_CONSOLIDADA = "consolidada"

# ── Caminhos ────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.getenv("LOG_DIR", "/home/bitnami/logs"))
LOG_FILE = LOG_DIR / "raia3_consolidado.log"

# ── DRY RUN ─────────────────────────────────────────────

DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
PUBLISH_AS_DRAFT = os.getenv("PUBLISH_AS_DRAFT", "0") == "1"

# ── Temas Proibidos ─────────────────────────────────────

TEMAS_PROIBIDOS = [
    "fofoca",
    "celebridade",
    "reality show",
    "bbb",
    "big brother",
    "horóscopo",
    "signos",
    "novela",
    "resumo de novela",
    "quem saiu do bbb",
    "vaza foto",
    "flagra",
]

# ── Prioridade Editorial ────────────────────────────────

PRIORIDADE_TEMAS = {
    "política": 10,
    "economia": 9,
    "segurança": 8,
    "saúde": 7,
    "educação": 6,
    "meio ambiente": 5,
    "tecnologia": 4,
    "esportes": 3,
    "internacional": 2,
}
