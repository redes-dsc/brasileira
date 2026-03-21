#!/usr/bin/env python3
"""
Revisor de Imagens para Posts Antigos - Brasileira.news

Script de baixo impacto que revisa posts antigos sem imagem destacada,
aplicando o curador unificado de imagens em modo seguro (rate-limited).

SEGURANÇA:
- Processa apenas N posts por execução (configurável)
- Delay entre posts para não sobrecarregar APIs
- Logging detalhado para auditoria
- Modo dry-run para teste
- Não interfere com sistemas em produção

Uso:
  python3 revisor_imagens_antigos.py              # Executa com padrões
  python3 revisor_imagens_antigos.py --dry-run    # Simula sem aplicar
  python3 revisor_imagens_antigos.py --limit 10   # Limita a 10 posts
  python3 revisor_imagens_antigos.py --older-than 7  # Posts com mais de 7 dias
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Setup path
sys.path.insert(0, "/home/bitnami")
sys.path.insert(0, "/home/bitnami/motor_rss")

import pymysql
import config
from curador_imagens_unificado import get_curador, generate_search_keywords

# ─── Configuração ────────────────────────────────────────────

DEFAULT_LIMIT = 5          # Posts por execução
DEFAULT_DELAY = 10         # Segundos entre posts
DEFAULT_OLDER_THAN = 1     # Dias mínimos de idade
LOG_FILE = "/home/bitnami/logs/revisor_imagens.log"

# ─── Logging ─────────────────────────────────────────────────

def setup_logging(verbose: bool = False):
    """Configura logging para arquivo e console."""
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    level = logging.DEBUG if verbose else logging.INFO
    
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    
    logger = logging.getLogger("revisor_imagens")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# ─── Database ────────────────────────────────────────────────

def get_db_connection():
    """Retorna conexão com o banco de dados."""
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASS,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_posts_without_images(
    limit: int = DEFAULT_LIMIT,
    older_than_days: int = DEFAULT_OLDER_THAN,
) -> list[dict]:
    """
    Busca posts publicados sem imagem destacada.
    
    Args:
        limit: Número máximo de posts
        older_than_days: Idade mínima em dias
    
    Returns:
        Lista de dicts com post_id, post_title, post_content, source_url
    """
    conn = get_db_connection()
    prefix = config.TABLE_PREFIX
    
    try:
        with conn.cursor() as cur:
            # Buscar posts sem thumbnail
            query = f"""
                SELECT p.ID as post_id, 
                       p.post_title, 
                       p.post_content,
                       p.post_date,
                       pm.meta_value as source_url
                FROM {prefix}posts p
                LEFT JOIN {prefix}postmeta thumb 
                    ON p.ID = thumb.post_id AND thumb.meta_key = '_thumbnail_id'
                LEFT JOIN {prefix}postmeta pm 
                    ON p.ID = pm.post_id AND pm.meta_key = 'source_url'
                WHERE p.post_status = 'publish'
                  AND p.post_type = 'post'
                  AND thumb.meta_value IS NULL
                  AND p.post_date < NOW() - INTERVAL %s DAY
                ORDER BY p.post_date DESC
                LIMIT %s
            """
            cur.execute(query, (older_than_days, limit))
            posts = cur.fetchall()
            return posts
    finally:
        conn.close()


def update_post_thumbnail(post_id: int, media_id: int) -> bool:
    """
    Atualiza o thumbnail de um post.
    
    Args:
        post_id: ID do post
        media_id: ID da mídia no WordPress
    
    Returns:
        True se sucesso, False caso contrário
    """
    conn = get_db_connection()
    prefix = config.TABLE_PREFIX
    
    try:
        with conn.cursor() as cur:
            # Verificar se já existe thumbnail
            cur.execute(f"""
                SELECT meta_id FROM {prefix}postmeta 
                WHERE post_id = %s AND meta_key = '_thumbnail_id'
            """, (post_id,))
            
            existing = cur.fetchone()
            
            if existing:
                # Atualizar existente
                cur.execute(f"""
                    UPDATE {prefix}postmeta 
                    SET meta_value = %s 
                    WHERE post_id = %s AND meta_key = '_thumbnail_id'
                """, (media_id, post_id))
            else:
                # Inserir novo
                cur.execute(f"""
                    INSERT INTO {prefix}postmeta (post_id, meta_key, meta_value)
                    VALUES (%s, '_thumbnail_id', %s)
                """, (post_id, media_id))
            
            conn.commit()
            return True
    except Exception as e:
        logging.getLogger("revisor_imagens").error(f"Erro ao atualizar thumbnail: {e}")
        return False
    finally:
        conn.close()


# ─── Processamento Principal ─────────────────────────────────

def process_posts(
    posts: list[dict],
    dry_run: bool = False,
    delay: int = DEFAULT_DELAY,
) -> dict:
    """
    Processa lista de posts, buscando e aplicando imagens.
    
    Args:
        posts: Lista de posts para processar
        dry_run: Se True, não aplica mudanças
        delay: Segundos de delay entre posts
    
    Returns:
        Dict com estatísticas: {processed, success, failed, skipped}
    """
    logger = logging.getLogger("revisor_imagens")
    curador = get_curador()
    
    stats = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
    }
    
    total = len(posts)
    
    for i, post in enumerate(posts, 1):
        post_id = post["post_id"]
        title = post["post_title"]
        content = post.get("post_content", "")
        source_url = post.get("source_url", "") or ""
        
        logger.info(f"[{i}/{total}] Processando post {post_id}: {title[:50]}...")
        
        try:
            # Gerar keywords otimizadas
            keywords = generate_search_keywords(title, content[:500])
            logger.debug(f"  Keywords: {keywords}")
            
            if dry_run:
                logger.info(f"  [DRY-RUN] Simulando busca de imagem...")
                stats["processed"] += 1
                stats["skipped"] += 1
                continue
            
            # Buscar imagem via curador
            media_id, caption = curador.get_featured_image(
                html_content=content,
                source_url=source_url,
                title=title,
                keywords=keywords
            )
            
            if media_id:
                # Aplicar ao post
                if update_post_thumbnail(post_id, media_id):
                    logger.info(f"  ✓ Imagem {media_id} aplicada ao post {post_id}")
                    stats["success"] += 1
                else:
                    logger.warning(f"  ✗ Falha ao aplicar imagem ao post {post_id}")
                    stats["failed"] += 1
            else:
                logger.warning(f"  ✗ Nenhuma imagem encontrada para post {post_id}")
                stats["failed"] += 1
            
            stats["processed"] += 1
            
        except Exception as e:
            logger.error(f"  ✗ Erro ao processar post {post_id}: {e}")
            stats["failed"] += 1
            stats["processed"] += 1
        
        # Delay entre posts (exceto no último)
        if i < total and not dry_run:
            logger.debug(f"  Aguardando {delay}s antes do próximo post...")
            time.sleep(delay)
    
    return stats


# ─── CLI ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Revisor de Imagens para Posts Antigos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  %(prog)s                      # Processa 5 posts com padrões
  %(prog)s --dry-run            # Simula sem aplicar mudanças
  %(prog)s --limit 20           # Processa até 20 posts
  %(prog)s --older-than 7       # Posts com mais de 7 dias
  %(prog)s --delay 30           # 30s de delay entre posts
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula execução sem aplicar mudanças"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Número máximo de posts a processar (padrão: {DEFAULT_LIMIT})"
    )
    parser.add_argument(
        "--older-than",
        type=int,
        default=DEFAULT_OLDER_THAN,
        help=f"Idade mínima dos posts em dias (padrão: {DEFAULT_OLDER_THAN})"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=DEFAULT_DELAY,
        help=f"Segundos de delay entre posts (padrão: {DEFAULT_DELAY})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Modo verbose (debug)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(verbose=args.verbose)
    
    # Header
    logger.info("=" * 60)
    logger.info("REVISOR DE IMAGENS PARA POSTS ANTIGOS")
    logger.info("=" * 60)
    logger.info(f"  Modo: {'DRY-RUN (simulação)' if args.dry_run else 'PRODUÇÃO'}")
    logger.info(f"  Limite: {args.limit} posts")
    logger.info(f"  Idade mínima: {args.older_than} dias")
    logger.info(f"  Delay: {args.delay}s entre posts")
    logger.info("=" * 60)
    
    # Buscar posts
    logger.info("Buscando posts sem imagem destacada...")
    posts = get_posts_without_images(
        limit=args.limit,
        older_than_days=args.older_than
    )
    
    if not posts:
        logger.info("Nenhum post encontrado para processar.")
        return
    
    logger.info(f"Encontrados {len(posts)} posts para processar.")
    
    # Processar
    start_time = time.time()
    stats = process_posts(
        posts=posts,
        dry_run=args.dry_run,
        delay=args.delay
    )
    elapsed = time.time() - start_time
    
    # Resumo
    logger.info("=" * 60)
    logger.info("RESUMO")
    logger.info("=" * 60)
    logger.info(f"  Processados: {stats['processed']}")
    logger.info(f"  Sucesso: {stats['success']}")
    logger.info(f"  Falhas: {stats['failed']}")
    logger.info(f"  Pulados: {stats['skipped']}")
    logger.info(f"  Tempo total: {elapsed:.1f}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
