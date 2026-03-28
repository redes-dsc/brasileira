"""

Configurações centralizadas para o Motor RSS brasileira.news

Carrega variáveis do .env e define constantes do sistema.

"""



import os

from pathlib import Path

from dotenv import load_dotenv



load_dotenv()



# ── WordPress ──────────────────────────────────────────

WP_URL = os.getenv("WP_URL", "https://brasileira.news")

WP_USER = os.getenv("WP_USER", "iapublicador")

WP_APP_PASS = os.getenv("WP_APP_PASS", "")

WP_API_BASE = f"{WP_URL}/wp-json/wp/v2"



# ── Banco de dados (MariaDB) ──────────────────────────

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")

DB_PORT = int(os.getenv("DB_PORT", "3306"))

DB_USER = os.getenv("DB_USER", "bn_wordpress")

DB_PASS = os.getenv("DB_PASS", "")

DB_NAME = os.getenv("DB_NAME", "bitnami_wordpress")

TABLE_PREFIX = os.getenv("TABLE_PREFIX", "wp_7_")

BLOG_ID = int(os.getenv("BLOG_ID", "7"))



# ── Chaves LLM ────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")

# Chaves múltiplas por provider (rotação / fallback de quota)
def _load_keys(prefix: str) -> list[str]:
    """Carrega todas as keys de um provider (KEY, KEY_2, KEY_3, ...)."""
    keys = []
    base = os.getenv(prefix, "")
    if base:
        keys.append(base)
    for i in range(2, 10):
        k = os.getenv(f"{prefix}_{i}", "")
        if k:
            keys.append(k)
    return keys

ANTHROPIC_KEYS = _load_keys("ANTHROPIC_API_KEY")
GEMINI_KEYS = _load_keys("GEMINI_API_KEY")
GROK_KEYS = _load_keys("GROK_API_KEY")
PERPLEXITY_KEYS = _load_keys("PERPLEXITY_API_KEY")
OPENAI_KEYS = _load_keys("OPENAI_API_KEY")
DEEPSEEK_KEYS = _load_keys("DEEPSEEK_API_KEY")
QWEN_KEYS = _load_keys("QWEN_API_KEY")



# ── Unsplash (imagens) ────────────────────────────────

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")



# ── Ciclo operacional ─────────────────────────────────

CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", "1800"))

MAX_ARTICLES_PER_CYCLE = int(os.getenv("MAX_ARTICLES_PER_CYCLE", "20"))

MIN_ARTICLES_PER_CYCLE = int(os.getenv("MIN_ARTICLES_PER_CYCLE", "15"))



# ── Paths ─────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent

FEEDS_FILE = BASE_DIR / "feeds.json"

LOG_DIR = Path(os.getenv("LOG_DIR", "/home/bitnami/logs"))



# ── Timeouts e limites ────────────────────────────────

HTTP_TIMEOUT = 60

LLM_TIMEOUT = 60

WP_POST_DELAY = 3

WP_RETRY_COUNT = 3

MIN_CONTENT_WORDS = 200

MIN_IMAGE_WIDTH = 400

MIN_IMAGE_HEIGHT = 300



# ── Categorias válidas do site ─────────────────────────

VALID_CATEGORIES = [

    "Segmentos de Tecnologia",

    "Política & Poder",

    "Saúde & Bem-Estar",

    "Economia & Negócios",

    "Meio Ambiente",

    "Segurança & Defesa",

    "Educação & Cultura",

    "Esportes",

    "Internacional",

    "Entretenimento",

    "Agronegócio",

    "Infraestrutura & Urbanismo",

    "Ciência & Inovação",

    "Direito & Justiça",

    "Energia & Clima",

    "Turismo",

]



# ── Prompts LLM ───────────────────────────────────────













LLM_SYSTEM_PROMPT = (

    "Você é o Editor-Chefe Sênior do portal Brasileira.news. "

    "Sua função transformar feeds brutos em peças jornalísticas impecáveis, sempre em formato JSON. "

    "REGRA DE OURO: TOLERÂNCIA ZERO PARA ALUCINAÇÃO. "

    "ESTRITAMENTE PROIBIDO inventar fatos, dados, estatísticas, nomes ou acontecimentos. "

    "Atue APENAS como reescritor/tradutor/editor de excelência do texto fornecido."

)



LLM_REWRITE_PROMPT_TEMPLATE = """Reescreva o artigo abaixo seguindo OBRIGATORIAMENTE estas regras:



=== MANUAL DE REDAÇÃO ===



1. IDIOMA: Português do Brasil. Se o texto estiver em outro idioma, traduza com precisão jornalística.



2. TÍTULO (h1title): 70 a 90 caracteres. Palavra-chave nas primeiras 8 palavras. Sem prefixos (OFICIAL:, GOVERNO:, Via X:).



3. CONTEÚDO — mínimo 400 palavras:
   - OBRIGATÓRIO: TODOS os parágrafos de texto fluído devem ser envolvidos e fechados corretamente por tags <p> e </p>. NUNCA deixe texto solto.
   - 1º parágrafo LIDE: responda O quê? Quem? Quando? Onde? Como? Por quê?

   - OBRIGATÓRIO no 1º ou 2º parágrafo: citar a fonte com link HTML:

     De acordo com informações do/da <a href="URL_DA_FONTE" target="_blank" rel="nofollow">NOME_DA_FONTE</a>

   - Use <h2> a cada 2-3 parágrafos formulados como PERGUNTAS (estilo FAQ)

   - Use <strong> nas entidades cruciais no primeiro terço do texto

   - Use <blockquote> APENAS para aspas diretas reais do texto original — NUNCA invente aspas

   - Use <ul> quando houver listas de prazos, fatores ou pontos principais

   - PROIBIDO: asteriscos (**), underscores (__), cerquilhas (#) — use APENAS HTML
   - PROIBIDO: envelopar o conteúdo com blocos markdown de código (como ```html ou ```json). O JSON deve conter a string HTML limpa.
   - PROIBIDO: inventar informações para alongar o texto artificialmente
   - Números: por extenso de zero a dez, numerais a partir de 11

   - Moedas: R$ antes do número. Acima de mil: R$ 1,5 milhão

   - Linguagem chapa-branca: transforme linguagem promocional em relato objetivo

   - Presunção de inocência: use "suspeito de", "acusado de"

   - CVV (188): incluir SOMENTE se a notícia tratar explicitamente de suicídio



4. EXCERPT: 2 frases objetivas, máx 300 chars, sem aspas, sem repetir o título.



5. CATEGORIA: Escolha UMA: {categories}



6. TAGS: 3 a 5 entidades reais do texto (pessoas, instituições, leis). PROIBIDO palavras genéricas ou adjetivos.



=== MANUAL DE SEO ===



7. seo_title: máx 60 caracteres (evita truncamento na SERP). Palavra-chave principal no início.



8. seo_description: máx 155 caracteres. Inclua micro CTA (ex: "Saiba mais", "Entenda", "Veja").



9. push_notification: chamada curtíssima até 80 chars para notificação push.



=== MANUAL DE FOTOJORNALISMO — CURADORIA DE IMAGEM ===

Você é o Editor de Fotografia do portal. Sua missão é definir a melhor imagem factual para esta matéria.
A imagem será buscada em bancos de agências oficiais (EBC, Gov.br, Flickr governamental) e na Wikimedia Commons.
Analise o texto COMPLETO que você acabou de reescrever e determine:

--- PRINCÍPIO FUNDAMENTAL ---
Se a notícia é sobre uma PESSOA, busque uma foto dessa pessoa.
Use o nome + o STATUS JORNALÍSTICO que define o papel dela NA NOTÍCIA.
  "Daniel Vorcaro preso" — não "Daniel Vorcaro helicóptero PF"
  "Lula" — não "Lula coletiva" ou "Lula discurso"
  "André Mendonça" — não "André Mendonça sessão STF"
STATUS é a condição da pessoa (preso, ministro, réu, candidato). CENA é detalhe do momento (helicóptero, plenário, microfone). Use status, nunca cena.
Nós NÃO temos câmera no local do fato. Não tente simular o momento.

Se a notícia NÃO tem protagonista humano, busque o OBJETO FÍSICO REAL.

--- LÓGICA DE BUSCA ---

PESSOA PÚBLICA:
  Nome + status jornalístico quando relevante.
  "Daniel Vorcaro preso" — "Leila Pereira presidente" — "Moise Kouame"
  Se o status é óbvio (presidente Lula), o nome basta: "Lula".

CONFRONTO ESPORTIVO:
  Apenas os nomes dos dois clubes/atletas.
  "Vasco Fluminense" — "Palmeiras São Paulo"

LUGAR / INSTITUIÇÃO (sem protagonista humano):
  Nome do local. "Banco Central" — "Refinaria Irã"

DESASTRE / OPERAÇÃO (o evento é o fato):
  Local + tipo. "enchente RS" — "operação Polícia Federal"

TEMA ABSTRATO (sem pessoa nem local):
  Conceito visual. "vacinação SUS" — "inteligência artificial"

--- REGRAS TÉCNICAS ---
- Para pessoas: nome + 1 palavra de status se relevante. Máx 3 palavras.
- Para locais/eventos: máx 3-4 palavras.
- Nomes curtos: "Lula", "Moro", "Bolsonaro", "STF".
- Sem AND/OR.
- Para commons: NOME FORMAL COMPLETO.

10. imagem_busca_gov: Nome da pessoa (+ status se relevante) ou nome do local. Máx 3 palavras.
11. imagem_busca_commons: Nome formal/enciclopédico da pessoa ou entidade para Wikimedia.
12. block_stock_images: true para qualquer notícia factual real. false APENAS para temas abstratos atemporais.
13. legenda_imagem: Legenda factual (máx 150 chars).

Retorne APENAS JSON válido com estas chaves:
titulo, conteudo, excerpt, categoria, tags, seo_title, seo_description, push_notification, imagem_busca_gov, imagem_busca_commons, block_stock_images, legenda_imagem



--- ARTIGO ORIGINAL ---

Título: {title}

Fonte: {source}

URL da fonte: {url}



{content}

"""


# ── Validação de variáveis obrigatórias ───────────────

def validate_config():

    """Valida presença das variáveis obrigatórias no .env."""

    obrigatorias = {

        "WP_APP_PASS": WP_APP_PASS,

        "DB_PASS": DB_PASS,

        "GEMINI_API_KEY": GEMINI_API_KEY,

    }

    faltando = [k for k, v in obrigatorias.items() if not v]

    if faltando:

        raise EnvironmentError(

            f"Variáveis obrigatórias ausentes no .env: {faltando}"

        )

