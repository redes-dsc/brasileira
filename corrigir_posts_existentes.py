#!/usr/bin/env python3

import os, re, time, logging, requests, mysql.connector

from dotenv import load_dotenv

from requests.adapters import HTTPAdapter

from urllib3.util.retry import Retry

import google.generativeai as genai



load_dotenv()

os.makedirs('/home/bitnami/logs', exist_ok=True)

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s [%(levelname)s] %(message)s',

    handlers=[

        logging.FileHandler('/home/bitnami/logs/correcao_posts.log'),

        logging.StreamHandler()

    ]

)

logger = logging.getLogger(__name__)



WP_URL      = os.getenv("WP_URL", "https://brasileira.news")

WP_USER     = os.getenv("WP_USER")

WP_APP_PASS = os.getenv("WP_APP_PASS")

DB_HOST     = os.getenv("DB_HOST", "127.0.0.1")

DB_PORT     = int(os.getenv("DB_PORT", "3306"))

DB_USER     = os.getenv("DB_USER", "bn_wordpress")

DB_PASS     = os.getenv("DB_PASS")

DB_NAME     = os.getenv("DB_NAME", "bitnami_wordpress")

GEMINI_KEY  = os.getenv("GEMINI_API_KEY")



# Prefix correto para brasileira.news (blog_id=7)

TP = "wp_7_"



genai.configure(api_key=GEMINI_KEY)

gemini = genai.GenerativeModel("gemini-1.5-flash")



TITLE_PREFIXES = [

    r'^OFICIAL:\s*', r'^GOVERNO:\s*', r'^COMERCIAL:\s*',

    r'^IMPRENSA:\s*', r'^NOTA:\s*', r'^RELEASE:\s*',

    r'^\[OFICIAL\]\s*', r'^\[GOVERNO\]\s*', r'^\[IMPRENSA\]\s*',

    r'^Publicado em \w+:\s*', r'^Via \w+:\s*',

]



CATEGORY_MAP = {

    "Segmentos de Tecnologia": ["tecnologia","tech","software","hardware","startup"],

    "Politica & Poder":        ["politica","governo","congresso","senado","presidente"],

    "Economia & Negocios":     ["economia","mercado","financas","bolsa","inflacao","pib"],

    "Saude & Bem-Estar":       ["saude","medicina","hospital","sus","doenca"],

    "Meio Ambiente":           ["meio ambiente","clima","amazonia","sustentabilidade"],

    "Seguranca & Defesa":      ["seguranca","policia","crime","defesa","militar"],

    "Educacao & Cultura":      ["educacao","escola","universidade","cultura"],

    "Esportes":                ["futebol","esporte","atleta","campeonato"],

    "Internacional":           ["internacional","exterior","eua","china","europa"],

    "Entretenimento":          ["entretenimento","celebridade","cinema","musica"],

}



def create_session():

    s = requests.Session()

    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429,500,502,503,504])

    s.mount("https://", HTTPAdapter(max_retries=retry))

    s.mount("http://",  HTTPAdapter(max_retries=retry))

    s.auth = (WP_USER, WP_APP_PASS)

    s.headers.update({"Content-Type": "application/json"})

    return s



SESSION = create_session()



def get_db():

    return mysql.connector.connect(

        host=DB_HOST, port=DB_PORT,

        user=DB_USER, password=DB_PASS,

        database=DB_NAME,

        charset='utf8mb4',

        collation='utf8mb4_general_ci',

        use_unicode=True

    )



def fetch_all_posts():

    conn = get_db()

    cur  = conn.cursor(dictionary=True)

    cur.execute(f"""

        SELECT ID, post_title, post_content, post_excerpt

        FROM {TP}posts

        WHERE post_status='publish' AND post_type='post'

        ORDER BY ID ASC

    """)

    posts = cur.fetchall()

    cur.close(); conn.close()

    logger.info(f"Posts encontrados: {len(posts)}")

    return posts



def clean_title(title):

    orig = title

    for p in TITLE_PREFIXES:

        title = re.sub(p, '', title, flags=re.IGNORECASE).strip()

    title = title.strip('"').strip("'").strip()

    if title and title[0].islower():

        title = title[0].upper() + title[1:]

    return title, title != orig



def update_title_db(post_id, title):

    conn = get_db()

    cur  = conn.cursor()

    cur.execute(f"UPDATE {TP}posts SET post_title=%s WHERE ID=%s", (title, post_id))

    conn.commit(); cur.close(); conn.close()



def needs_excerpt_fix(excerpt):

    return not excerpt or len(excerpt.strip()) < 30



def generate_excerpt(title, content):

    text = re.sub(r'<[^>]+>', '', content)[:1500]

    try:

        prompt = (

            f"Crie um resumo jornalistico de 2 frases (max 280 caracteres) "

            f"para o artigo abaixo. Sem aspas. Direto e informativo.\n\n"

            f"Titulo: {title}\n\nConteudo: {text}"

        )

        r = gemini.generate_content(prompt)

        return r.text.strip()[:280]

    except Exception as e:

        logger.warning(f"Excerpt fallback: {e}")

        sentences = re.split(r'(?<=[.!?])\s+', text)

        return ' '.join(sentences[:2])[:280]



def update_excerpt_db(post_id, excerpt):

    conn = get_db()

    cur  = conn.cursor()

    cur.execute(f"UPDATE {TP}posts SET post_excerpt=%s WHERE ID=%s", (excerpt, post_id))

    conn.commit(); cur.close(); conn.close()



def get_featured_image_id(post_id):

    conn = get_db()

    cur  = conn.cursor()

    cur.execute(

        f"SELECT meta_value FROM {TP}postmeta WHERE post_id=%s AND meta_key='_thumbnail_id'",

        (post_id,)

    )

    row = cur.fetchone()

    cur.close(); conn.close()

    return int(row[0]) if row and row[0] else None



def get_first_image_from_content(content):

    m = re.search(r'src=["\']([^"\']+\.(jpg|jpeg|png|webp))["\']', content, re.IGNORECASE)

    return m.group(1) if m else None



def upload_image_from_url(img_url, post_title):

    try:

        r = requests.get(img_url, timeout=15, stream=True)

        r.raise_for_status()

        ext      = img_url.split('?')[0].split('.')[-1].lower() or 'jpg'

        filename = re.sub(r'[^a-z0-9]', '-', post_title.lower())[:50] + '.' + ext

        ctype    = 'image/jpeg' if ext == 'jpg' else f'image/{ext}'

        resp = SESSION.post(

            f"{WP_URL}/wp-json/wp/v2/media",

            headers={"Content-Disposition": f'attachment; filename="{filename}"',

                     "Content-Type": ctype},

            data=r.content,

            auth=(WP_USER, WP_APP_PASS)

        )

        if resp.status_code in [200,201]:

            return resp.json().get('id')

    except Exception as e:

        logger.warning(f"Upload imagem falhou: {e}")

    return None



def set_featured_image(post_id, media_id):

    SESSION.post(

        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",

        json={"featured_media": media_id},

        auth=(WP_USER, WP_APP_PASS)

    )



def get_category_id_by_name(name):

    conn = get_db()

    cur  = conn.cursor()

    cur.execute(f"""

        SELECT t.term_id FROM {TP}terms t

        JOIN {TP}term_taxonomy tt ON t.term_id=tt.term_id

        WHERE t.name=%s AND tt.taxonomy='category'

    """, (name,))

    row = cur.fetchone()

    cur.close(); conn.close()

    return row[0] if row else None



def get_post_category_ids(post_id):

    conn = get_db()

    cur  = conn.cursor()

    cur.execute(f"""

        SELECT t.term_id FROM {TP}terms t

        JOIN {TP}term_taxonomy tt ON t.term_id=tt.term_id

        JOIN {TP}term_relationships tr ON tt.term_taxonomy_id=tr.term_taxonomy_id

        WHERE tr.object_id=%s AND tt.taxonomy='category'

    """, (post_id,))

    rows = cur.fetchall()

    cur.close(); conn.close()

    return [r[0] for r in rows]



def detect_better_category(title, content):

    text   = (title + ' ' + content[:500]).lower()

    scores = {}

    for cat, kws in CATEGORY_MAP.items():

        s = sum(1 for kw in kws if kw in text)

        if s > 0:

            scores[cat] = s

    return max(scores, key=scores.get) if scores else None



def find_duplicates():

    conn = get_db()

    cur  = conn.cursor(dictionary=True)

    cur.execute(f"""

        SELECT post_title, COUNT(*) cnt,

               GROUP_CONCAT(ID ORDER BY ID ASC) ids

        FROM {TP}posts

        WHERE post_status='publish' AND post_type='post'

        GROUP BY post_title HAVING cnt > 1

    """)

    dups = cur.fetchall()

    cur.close(); conn.close()

    return dups



def trash_post(post_id):

    r = SESSION.delete(

        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",

        auth=(WP_USER, WP_APP_PASS)

    )

    return r.status_code in [200,201]



def main():

    stats = dict(total=0, titulo=0, excerpt=0, imagem=0, categoria=0, duplicata=0, erro=0)



    logger.info("=== FASE 0: Removendo duplicatas ===")

    dups = find_duplicates()

    logger.info(f"Grupos duplicados: {len(dups)}")

    for d in dups:

        ids = [int(x) for x in d['ids'].split(',')]

        for old_id in ids[1:]:

            if trash_post(old_id):

                stats['duplicata'] += 1

                logger.info(f"  Removido ID {old_id}: {d['post_title'][:60]}")

            time.sleep(0.2)



    logger.info("=== FASE 1: Corrigindo posts ===")

    posts = fetch_all_posts()

    stats['total'] = len(posts)



    for i, post in enumerate(posts):

        pid     = post['ID']

        title   = post['post_title'] or ''

        content = post['post_content'] or ''

        excerpt = post['post_excerpt'] or ''



        try:

            new_title, changed = clean_title(title)

            if changed:

                update_title_db(pid, new_title)

                stats['titulo'] += 1

                title = new_title



            if needs_excerpt_fix(excerpt):

                update_excerpt_db(pid, generate_excerpt(title, content))

                stats['excerpt'] += 1

                time.sleep(0.3)



            if not get_featured_image_id(pid):

                img_url = get_first_image_from_content(content)

                if img_url:

                    mid = upload_image_from_url(img_url, title)

                    if mid:

                        set_featured_image(pid, mid)

                        stats['imagem'] += 1



            cat_ids = get_post_category_ids(pid)

            if len(cat_ids) <= 1:

                best = detect_better_category(title, content)

                if best:

                    cid = get_category_id_by_name(best)

                    if cid and cid not in cat_ids:

                        SESSION.post(

                            f"{WP_URL}/wp-json/wp/v2/posts/{pid}",

                            json={"categories": [cid]},

                            auth=(WP_USER, WP_APP_PASS)

                        )

                        stats['categoria'] += 1



        except Exception as e:

            stats['erro'] += 1

            logger.error(f"[{pid}] ERRO: {e}")



        if (i+1) % 50 == 0:

            logger.info(f"Progresso: {i+1}/{stats['total']} | {stats}")

            time.sleep(1)



    logger.info("=== CONCLUIDO ===")

    for k, v in stats.items():

        logger.info(f"  {k}: {v}")



if __name__ == "__main__":

    main()

