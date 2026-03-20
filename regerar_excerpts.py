#!/usr/bin/env python3

"""

regerar_excerpts.py

Reprocessa APENAS os excerpts ruins (curtos, vazios ou fallback)

usando gemini-2.0-flash via nova biblioteca google-genai.

"""

import os, re, time, logging, mysql.connector

from dotenv import load_dotenv

from google import genai

from google.genai import types



load_dotenv()

os.makedirs('/home/bitnami/logs', exist_ok=True)

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s [%(levelname)s] %(message)s',

    handlers=[

        logging.FileHandler('/home/bitnami/logs/excerpts.log'),

        logging.StreamHandler()

    ]

)

logger = logging.getLogger(__name__)



DB_HOST    = os.getenv("DB_HOST", "127.0.0.1")

DB_PORT    = int(os.getenv("DB_PORT", "3306"))

DB_USER    = os.getenv("DB_USER", "bn_wordpress")

DB_PASS    = os.getenv("DB_PASS")

DB_NAME    = os.getenv("DB_NAME", "bitnami_wordpress")

GEMINI_KEY = os.getenv("GEMINI_API_KEY")



TP = "wp_7_"  # brasileira.news = blog_id 7



client = genai.Client(api_key=GEMINI_KEY)



def get_db():

    return mysql.connector.connect(

        host=DB_HOST, port=DB_PORT,

        user=DB_USER, password=DB_PASS,

        database=DB_NAME,

        charset='utf8mb4',

        collation='utf8mb4_general_ci',

        use_unicode=True

    )



def fetch_posts_sem_excerpt():

    """Busca posts com excerpt vazio ou menor que 80 caracteres."""

    conn = get_db()

    cur  = conn.cursor(dictionary=True)

    cur.execute(f"""

        SELECT ID, post_title, post_content, post_excerpt

        FROM {TP}posts

        WHERE post_status='publish' AND post_type='post'

          AND (post_excerpt IS NULL OR CHAR_LENGTH(TRIM(post_excerpt)) < 80)

        ORDER BY ID ASC

    """)

    posts = cur.fetchall()

    cur.close(); conn.close()

    logger.info(f"Posts com excerpt ruim: {len(posts)}")

    return posts



def gerar_excerpt(title, content):

    texto = re.sub(r'<[^>]+>', '', content)[:2000].strip()

    if not texto:

        return ''

    prompt = (

        f"Você é um editor jornalístico brasileiro sênior. "

        f"Escreva um resumo jornalístico de exatamente 2 frases (máximo 300 caracteres) "

        f"para o artigo abaixo. Use linguagem clara, direta e profissional. "

        f"Não use aspas, não repita o título, não comece com 'O artigo'.\n\n"

        f"Título: {title}\n\n"

        f"Conteúdo: {texto}"

    )

    try:

        resp = client.models.generate_content(

            model="gemini-2.0-flash",

            contents=prompt,

            config=types.GenerateContentConfig(

                max_output_tokens=120,

                temperature=0.4,

            )

        )

        return resp.text.strip()[:300]

    except Exception as e:

        logger.warning(f"Gemini falhou: {e}")

        # Fallback: primeiras 2 frases limpas

        frases = re.split(r'(?<=[.!?])\s+', texto)

        return ' '.join(frases[:2])[:280]



def update_excerpt(post_id, excerpt):

    conn = get_db()

    cur  = conn.cursor()

    cur.execute(

        f"UPDATE {TP}posts SET post_excerpt=%s WHERE ID=%s",

        (excerpt, post_id)

    )

    conn.commit(); cur.close(); conn.close()



def main():

    posts = fetch_posts_sem_excerpt()

    total = len(posts)

    ok = 0

    erro = 0



    for i, post in enumerate(posts):

        pid     = post['ID']

        title   = post['post_title'] or ''

        content = post['post_content'] or ''



        try:

            excerpt = gerar_excerpt(title, content)

            if excerpt:

                update_excerpt(pid, excerpt)

                ok += 1

                logger.info(f"[{i+1}/{total}] ID {pid}: {excerpt[:80]}...")

            else:

                logger.warning(f"[{i+1}/{total}] ID {pid}: excerpt vazio, pulando")



        except Exception as e:

            erro += 1

            logger.error(f"[{i+1}/{total}] ID {pid} ERRO: {e}")



        # Throttle: Gemini free tier ~15 req/min

        time.sleep(4)



        if (i+1) % 50 == 0:

            logger.info(f"--- Progresso: {i+1}/{total} | OK: {ok} | Erros: {erro} ---")



    logger.info("=== CONCLUIDO ===")

    logger.info(f"  Total: {total} | Gerados: {ok} | Erros: {erro}")



if __name__ == "__main__":

    main()

