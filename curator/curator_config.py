"""
Configurações do Home Curator Agent — brasileira.news

Carrega variáveis compartilhadas do motor_rss/.env
e define constantes específicas do curador.
"""

import os
import sys
from pathlib import Path

# ── Reusar config do motor_rss ────────────────────────
MOTOR_RSS_DIR = Path("/home/bitnami/motor_rss")
sys.path.insert(0, str(MOTOR_RSS_DIR))

from dotenv import load_dotenv
load_dotenv(MOTOR_RSS_DIR / ".env")

# Importa config compartilhado após carregar .env
import config as shared_config

# ── WordPress (herdados) ──────────────────────────────
WP_URL = shared_config.WP_URL
WP_USER = shared_config.WP_USER
WP_APP_PASS = shared_config.WP_APP_PASS
WP_API_BASE = shared_config.WP_API_BASE

# ── Banco de dados (herdados) ─────────────────────────
DB_HOST = shared_config.DB_HOST
DB_PORT = shared_config.DB_PORT
DB_USER = shared_config.DB_USER
DB_PASS = shared_config.DB_PASS
DB_NAME = shared_config.DB_NAME
TABLE_PREFIX = shared_config.TABLE_PREFIX
BLOG_ID = shared_config.BLOG_ID

# ── Chaves LLM (herdadas) ────────────────────────────
GEMINI_KEYS = shared_config.GEMINI_KEYS
ANTHROPIC_KEYS = shared_config.ANTHROPIC_KEYS
OPENAI_KEYS = shared_config.OPENAI_KEYS
GROK_KEYS = shared_config.GROK_KEYS
DEEPSEEK_KEYS = shared_config.DEEPSEEK_KEYS
QWEN_KEYS = shared_config.QWEN_KEYS

# ── Janela de tempo ───────────────────────────────────
CURATOR_WINDOW_HOURS = int(os.getenv("CURATOR_WINDOW_HOURS", "4"))
CURATOR_DRY_RUN = os.getenv("CURATOR_DRY_RUN", "0") == "1"

# ── Paths ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.getenv("LOG_DIR", "/home/bitnami/logs"))

# ── Timeouts e limites ────────────────────────────────
HTTP_TIMEOUT = 15
WP_RETRY_COUNT = 3
LLM_TIMEOUT = 15
LLM_MAX_CALLS_PER_CYCLE = 30
LLM_SCORE_THRESHOLD = 25        # score objetivo mínimo para chamar LLM
LLM_FALLBACK_SCORE = 25         # score retornado se LLM falhar
WP_PATCH_DELAY = 1.0            # segundos entre PATCHes (rate limit)

# ── Scores e filtros ──────────────────────────────────
SCORE_MINIMUM = 50
MIN_WORDS = 200                  # filtro eliminatório
MIN_WORDS_PENALTY = 300          # abaixo disso: -10

# ── Pesos de scoring (positivos) ──────────────────────
SCORE_FONTE_OFICIAL = 30
SCORE_CONSOLIDADA = 20
SCORE_ALTO_INTERESSE = 15
SCORE_RECENTE = 10               # publicado há menos de 1h
SCORE_TEM_IMAGEM = 10
SCORE_TITULO_SEO = 5             # entre 50-80 chars
SCORE_EXCERPT = 5
SCORE_TAGS_RELEVANTES = 5        # >= 3 tags

# ── Pesos de scoring (negativos) ──────────────────────
PENALTY_INTL_SEM_BR = -20
PENALTY_NICHO = -15
PENALTY_CURTO = -10              # < 300 palavras
PENALTY_SEM_IMAGEM = -10
PENALTY_TITULO_CURTO = -5       # < 30 chars

# ── Filtros de diversidade ────────────────────────────
MAX_SAME_CATEGORY_DESTAQUE = 2
MAX_SAME_SOURCE_TOP5 = 1

# ── TAG IDs (criados em criar_tags_editoriais.py) ─────
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
    "home-especial": 14922,
    "home-urgente": 14923,
    "consolidada": 14924,
}

# Lista de todas as tags de curadoria (para limpeza)
ALL_CURATOR_TAG_IDS = list(TAG_IDS.values())

# ── Mapa de posições da homepage ──────────────────────
# tag_slug → {"limit": N, "min_score": S, "cat_filter": set de category_ids ou None}
# cat_filter=None → agente tem liberdade total (manchete/submanchete)
# cat_filter=set → post deve pertencer a UMA dessas categorias
# Inclui: cat-mãe + subcategorias oficiais + duplicatas avulsas do motor_rss
HOMEPAGE_POSITIONS = {
    "home-manchete":       {"limit": 1,  "min_score": 40, "cat_filter": None},
    "home-submanchete":    {"limit": 5,  "min_score": 30, "cat_filter": None},
    "home-politica":       {"limit": 1,  "min_score": 25, "cat_filter": {71, 11742}},
    "home-economia":       {"limit": 2,  "min_score": 25, "cat_filter": {72, 11755}},
    "home-tecnologia":     {"limit": 10, "min_score": 20, "cat_filter": {129, 130, 131, 132, 133, 134, 12151, 11997, 13282, 12064, 13268, 14804, 12588}},
    "home-entretenimento": {"limit": 6,  "min_score": 20, "cat_filter": {122, 11931, 11730, 11735, 80}},
    "home-esportes":       {"limit": 5,  "min_score": 20, "cat_filter": {81, 11989, 82, 83, 84, 85, 86, 87}},
    "home-internacional":  {"limit": 6,  "min_score": 20, "cat_filter": {88, 89, 90, 91, 92, 93}},
    "home-justica":        {"limit": 4,  "min_score": 20, "cat_filter": {73, 11772, 13177}},
    "home-meioambiente":   {"limit": 4,  "min_score": 20, "cat_filter": {136, 141, 142, 143, 144, 145, 12405}},
    "home-saude":          {"limit": 4,  "min_score": 20, "cat_filter": {74, 12243, 11738}},
    "home-infraestrutura": {"limit": 5,  "min_score": 20, "cat_filter": {78, 11833}},
    "home-cultura":        {"limit": 5,  "min_score": 20, "cat_filter": {79, 11868, 13043, 13385, 75}},
    "home-sociedade":      {"limit": 3,  "min_score": 20, "cat_filter": {76, 11792, 11729}},
}

# ── Categorias de alto interesse nacional ─────────────
# Política, Economia, Justiça, Saúde, Sociedade (+ dups)
HIGH_INTEREST_CATEGORY_IDS = {71, 72, 73, 74, 76, 11742, 11755, 11772, 12243, 11792, 13177, 11738}

# ── Categorias de nicho (penalização) ─────────────────
# Entretenimento + subs, Futebol Internacional
NICHE_CATEGORY_IDS = {122, 11931, 11730, 11735, 80, 83}

# ── Categoria Internacional ───────────────────────────
INTERNATIONAL_CATEGORY_IDS = {88, 89, 90, 91, 92, 93}

# ── Domínios oficiais brasileiros ─────────────────────
OFFICIAL_DOMAINS = [
    "gov.br", "leg.br", "jus.br",
    "senado.leg.br", "camara.leg.br",
    "stf.jus.br", "stj.jus.br", "tse.jus.br", "tst.jus.br",
    "mpf.mp.br", "tcu.gov.br", "cgu.gov.br",
    "ibge.gov.br", "bcb.gov.br", "bndes.gov.br",
]

# ── Prompt LLM — Avaliação de relevância ──────────────
LLM_CURATOR_SYSTEM_PROMPT = (
    "Você é um editor-chefe sênior de um grande portal de notícias brasileiro. "
    "Sua tarefa é avaliar a relevância de uma notícia para o público brasileiro."
)

LLM_CURATOR_SCORE_PROMPT = """Avalie a relevância desta notícia para o público geral brasileiro.

Considere:
- Impacto nacional (afeta milhões de brasileiros?)
- Atualidade e urgência
- Interesse público (economia, saúde, segurança, política)
- Exclusividade e valor informativo

Título: {title}
Resumo: {excerpt}

Retorne APENAS um número inteiro de 0 a 50.
Nada mais, somente o número."""

# ── Prompt LLM — Decisão de manchete (Premium) ───────
LLM_HEADLINE_SYSTEM_PROMPT = (
    "Você é o editor-chefe da Brasileira.News. "
    "Sua decisão define a manchete principal do portal."
)

LLM_HEADLINE_PROMPT = """Analise os candidatos a manchete principal abaixo e escolha o MELHOR.

Critérios (em ordem de importância):
1. Impacto nacional imediato
2. Urgência e atualidade
3. Qualidade do título (atratividade, clareza)
4. Presença de imagem de destaque
5. Variedade editorial

Candidatos:
{candidates}

Retorne APENAS o número do candidato escolhido (1 a {count}).
Nada mais, somente o número."""
