
"""

Conexão MariaDB e operações de banco para o Motor RSS.

Usa pymysql com connection pooling via DBUtils.

"""



import logging
import threading
from contextlib import contextmanager



import pymysql

import pymysql.cursors

from dbutils.pooled_db import PooledDB



import config



logger = logging.getLogger("motor_rss")



_pool = None
_pool_lock = threading.Lock()

def _get_pool():
    """Retorna (ou cria) o pool de conexões global de forma thread-safe."""
    global _pool
    if _pool is None:
        with _pool_lock:
            # Check again inside lock to prevent race condition
            if _pool is None:
                _pool = PooledDB(
                    creator=pymysql,
                    maxconnections=10,
                    mincached=2,
                    maxcached=5,
                    blocking=True,
                    host=config.DB_HOST,
                    port=config.DB_PORT,
                    user=config.DB_USER,
                    password=config.DB_PASS,
                    database=config.DB_NAME,
                    charset="utf8mb4",
                    collation="utf8mb4_general_ci",
                    autocommit=True,
                    cursorclass=pymysql.cursors.DictCursor,
                    ping=1,  # ping on checkout to detect stale connections
                )
                logger.info("Pool de conexões MariaDB criado (min=2, max=10)")
    return _pool


def _get_connection():

    """Retorna uma conexão do pool."""

    return _get_pool().connection()




@contextmanager

def get_db():

    """Context manager para conexão ao banco (pooled)."""

    conn = _get_connection()

    try:

        yield conn

    finally:

        conn.close()  # retorna ao pool, não destrói





def _t(name: str) -> str:

    """Retorna nome da tabela com prefix dinâmico."""

    return f"{config.TABLE_PREFIX}{name}"





def ensure_control_table():

    """Cria a tabela de controle RSS se não existir."""

    ddl = f"""

    CREATE TABLE IF NOT EXISTS {_t('rss_control')} (

        id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

        post_id     BIGINT UNSIGNED NOT NULL,

        source_url  VARCHAR(2048) NOT NULL,

        feed_name   VARCHAR(255) NOT NULL,

        published_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

        llm_used    VARCHAR(64) NOT NULL DEFAULT '',

        INDEX idx_source_url (source_url(768)),

        INDEX idx_post_id (post_id)

    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci

    """

    with get_db() as conn:

        cursor = conn.cursor()

        cursor.execute(ddl)

        cursor.close()

    logger.info("Tabela %s verificada/criada.", _t("rss_control"))





def post_exists(url: str, title: str) -> bool:

    """

    Verifica se um post já existe por URL exata.
    Checa tabela de controle e guid do WordPress.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Checar URL exata na tabela de controle
            cursor.execute(
                f"SELECT 1 FROM {_t('rss_control')} WHERE source_url = %s LIMIT 1",
                (url,),
            )
            if cursor.fetchone():
                return True

            # Checar URL no guid dos posts WP
            cursor.execute(
                f"""
                SELECT 1 FROM {_t('posts')}
                WHERE guid = %s
                  AND post_status = 'publish'
                LIMIT 1
                """,
                (url,),
            )
            result = cursor.fetchone()
            return result is not None





def get_categories() -> dict:

    """Retorna dict {nome_categoria: term_id} das categorias do site."""

    query = f"""

    SELECT t.name, t.term_id

    FROM {_t('terms')} t

    JOIN {_t('term_taxonomy')} tt ON t.term_id = tt.term_id

    WHERE tt.taxonomy = 'category'

    """

    result = {}

    with get_db() as conn:

        cursor = conn.cursor()

        cursor.execute(query)

        for row in cursor.fetchall():

            result[row["name"]] = row["term_id"]

        cursor.close()

    return result





def get_tags() -> dict:

    """Retorna dict {nome_tag: term_id} das tags do site."""

    query = f"""

    SELECT t.name, t.term_id

    FROM {_t('terms')} t

    JOIN {_t('term_taxonomy')} tt ON t.term_id = tt.term_id

    WHERE tt.taxonomy = 'post_tag'

    """

    result = {}

    with get_db() as conn:

        cursor = conn.cursor()

        cursor.execute(query)

        for row in cursor.fetchall():

            result[row["name"]] = row["term_id"]

        cursor.close()

    return result





def register_published(post_id: int, source_url: str, feed_name: str, llm_used: str):

    """Registra um post publicado na tabela de controle."""

    with get_db() as conn:

        cursor = conn.cursor()

        cursor.execute(

            f"""
            INSERT IGNORE INTO {_t('rss_control')}
                (post_id, source_url, feed_name, llm_used)
            VALUES (%s, %s, %s, %s)
            """,

            (post_id, source_url, feed_name, llm_used),

        )

        cursor.close()

    logger.info(

        "Registrado post_id=%d | feed=%s | llm=%s", post_id, feed_name, llm_used

    )





def get_published_urls_last_24h() -> set:

    """Retorna conjunto de URLs publicadas nas últimas 24h."""

    with get_db() as conn:

        cursor = conn.cursor()

        cursor.execute(

            f"""

            SELECT source_url FROM {_t('rss_control')}

            WHERE published_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)

            """,

        )

        urls = {row["source_url"] for row in cursor.fetchall()}

        cursor.close()

    return urls

