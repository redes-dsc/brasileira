#!/usr/bin/env python3
"""
Home Curator Agent — Agente Editor de Primeira Página

Agente autônomo que a cada ciclo:
  1. Busca posts publicados nas últimas N horas
  2. Calcula score de relevância (objetivo + LLM)
  3. Distribui os melhores posts nas posições de destaque da home via tags
  4. Loga cada ciclo

Nenhum conteúdo é modificado — apenas tags são adicionadas/removidas.

Uso:
  python3 curator_agent.py              # ciclo completo
  python3 curator_agent.py --dry-run    # simula sem aplicar tags
  CURATOR_DRY_RUN=1 python3 curator_agent.py  # idem via env
"""

import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Garantir que estamos no diretório correto
os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymysql

import curator_config as cfg
import curator_scorer as scorer
import curator_tagger as tagger

# ─── Logging ─────────────────────────────────────────

def setup_logging():
    """Configura logging para arquivo diário + console."""
    log_dir = cfg.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"curator_{datetime.now():%Y-%m-%d}.log"
    
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    
    file_handler = logging.handlers.TimedRotatingFileHandler(log_file, when="midnight", backupCount=7, encoding="utf-8")
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger = logging.getLogger("curator")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# ─── Conexão DB ──────────────────────────────────────

def get_db_connection():
    """Retorna conexão pymysql."""
    return pymysql.connect(
        host=cfg.DB_HOST,
        port=cfg.DB_PORT,
        user=cfg.DB_USER,
        password=cfg.DB_PASS,
        database=cfg.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


# ─── Buscar posts recentes ──────────────────────────

def fetch_recent_posts(hours: int) -> list[dict]:
    """
    Busca posts publicados nas últimas N horas via DB direta.
    Usa queries batch para performance (5 queries total vs ~415 antes).
    """
    logger = logging.getLogger("curator")
    conn = get_db_connection()
    prefix = cfg.TABLE_PREFIX
    
    try:
        with conn.cursor() as cur:
            # ── Query 1: Posts recentes ───────────────────
            cur.execute(f"""
                SELECT p.ID as post_id, p.post_title, p.post_excerpt,
                       p.post_content, p.post_date, p.post_status
                FROM {prefix}posts p
                WHERE p.post_status = 'publish'
                  AND p.post_type = 'post'
                  AND p.post_date >= NOW() - INTERVAL %s HOUR
                ORDER BY p.post_date DESC
                LIMIT 200
            """, (hours,))
            posts = cur.fetchall()
            
            if not posts:
                logger.info("Nenhum post encontrado nas últimas %dh", hours)
                return []
            
            logger.info("Encontrados %d posts nas últimas %dh", len(posts), hours)
            
            post_ids = [p["post_id"] for p in posts]
            posts_by_id = {p["post_id"]: p for p in posts}
            
            # Inicializar campos
            for p in posts:
                p["featured_media"] = 0
                p["categories"] = []
                p["tags"] = []
                p["tag_names"] = []
                p["source_url"] = ""
            
            # ── Query 2: Thumbnails em batch ─────────────
            cur.execute(f"""
                SELECT post_id, meta_value
                FROM {prefix}postmeta
                WHERE post_id IN %s AND meta_key = '_thumbnail_id'
            """, (post_ids,))
            for row in cur.fetchall():
                pid = row["post_id"]
                if pid in posts_by_id:
                    try:
                        posts_by_id[pid]["featured_media"] = int(row["meta_value"])
                    except (ValueError, TypeError):
                        pass
            
            # ── Query 3: Categorias em batch ─────────────
            cur.execute(f"""
                SELECT tr.object_id as post_id, tt.term_id
                FROM {prefix}term_relationships tr
                JOIN {prefix}term_taxonomy tt ON tr.term_taxonomy_id = tt.term_taxonomy_id
                WHERE tr.object_id IN %s AND tt.taxonomy = 'category'
            """, (post_ids,))
            for row in cur.fetchall():
                pid = row["post_id"]
                if pid in posts_by_id:
                    posts_by_id[pid]["categories"].append(row["term_id"])
            
            # ── Query 4: Tags em batch ───────────────────
            cur.execute(f"""
                SELECT tr.object_id as post_id, t.slug, t.name
                FROM {prefix}term_relationships tr
                JOIN {prefix}term_taxonomy tt ON tr.term_taxonomy_id = tt.term_taxonomy_id
                JOIN {prefix}terms t ON tt.term_id = t.term_id
                WHERE tr.object_id IN %s AND tt.taxonomy = 'post_tag'
            """, (post_ids,))
            for row in cur.fetchall():
                pid = row["post_id"]
                if pid in posts_by_id:
                    posts_by_id[pid]["tags"].append(row["slug"])
                    posts_by_id[pid]["tag_names"].append(row["name"])
            
            # ── Query 5: Source URLs em batch ────────────
            cur.execute(f"""
                SELECT post_id, meta_value
                FROM {prefix}postmeta
                WHERE post_id IN %s AND meta_key = 'source_url'
            """, (post_ids,))
            for row in cur.fetchall():
                pid = row["post_id"]
                if pid in posts_by_id:
                    posts_by_id[pid]["source_url"] = row["meta_value"] or ""
            
            logger.info("Enriquecimento batch completo (5 queries)")
            return posts
    finally:
        conn.close()


# ─── Selecionar posts para cada posição ─────────────

def select_positions(scored_posts: list[dict]) -> dict[str, list[int]]:
    """
    Distribui posts nas posições da homepage com base nos scores.
    
    PASS 1: Seleciona posts com score >= min_score (lógica editorial)
    PASS 2: Preenche slots vazios com posts mais recentes da categoria
            (fallback — garante que nenhuma seção fique vazia)
    
    Args:
        scored_posts: lista de {post_id, score, categories, ...} já ordenados
    
    Returns:
        {tag_slug: [post_id, ...]}
    """
    logger = logging.getLogger("curator")
    selections = {}
    used_ids = set()  # evitar duplicatas entre posições
    
    # Ordenar por score decrescente para pass 1
    ranked = sorted(scored_posts, key=lambda p: p["score"], reverse=True)
    
    # Ordenar por data decrescente para pass 2 (fallback)
    by_date = sorted(scored_posts, key=lambda p: p.get("post_date", ""), reverse=True)
    
    from urllib.parse import urlparse
    category_destaque_counts = {}
    source_top5_counts = {}
    
    # ── PASS 1: Seleção por score ────────────────────
    for tag_slug, pos_cfg in cfg.HOMEPAGE_POSITIONS.items():
        limit = pos_cfg["limit"]
        min_score = pos_cfg["min_score"]
        cat_filter = pos_cfg["cat_filter"]
        require_tag = pos_cfg.get("require_tag")
        
        selected = []
        
        for post in ranked:
            if len(selected) >= limit:
                break
            
            post_id = post["post_id"]
            
            if post_id in used_ids:
                continue
            
            if post["score"] < min_score:
                continue
            
            if require_tag and require_tag not in post.get("tags", []):
                continue
            
            # Filtro de categoria (para editorias)
            post_cats = set(post.get("categories", []))
            if cat_filter is not None:
                if not post_cats & cat_filter:
                    continue
                    
            # Regras de Diversidade (Manchete + Submanchete = Top 5 slots)
            is_destaque = tag_slug in ("home-manchete", "home-submanchete")
            src_domain = ""
            if is_destaque:
                violation = False
                for cat in post_cats:
                    if category_destaque_counts.get(cat, 0) >= getattr(cfg, "MAX_SAME_CATEGORY_DESTAQUE", 2):
                        violation = True
                        break
                
                src = post.get("source_url", "")
                src_domain = urlparse(src).netloc.lower() if src else ""
                if src_domain and source_top5_counts.get(src_domain, 0) >= getattr(cfg, "MAX_SAME_SOURCE_TOP5", 1):
                    violation = True
                    
                if violation:
                    continue

            # Regra Dura: Manchete não pode ter mais de 4h
            if tag_slug == "home-manchete":
                from datetime import datetime, timedelta
                try:
                    from zoneinfo import ZoneInfo
                    local_now = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
                except Exception:
                    local_now = datetime.now() - timedelta(hours=3)
                    
                post_date = post.get("post_date")
                if isinstance(post_date, datetime):
                    if (local_now - post_date) > timedelta(hours=4):
                        continue

            selected.append(post_id)
            used_ids.add(post_id)
            
            if is_destaque:
                for cat in post_cats:
                    category_destaque_counts[cat] = category_destaque_counts.get(cat, 0) + 1
                if src_domain:
                    source_top5_counts[src_domain] = source_top5_counts.get(src_domain, 0) + 1
        
        selections[tag_slug] = selected
    
    # ── PASS 2: Fallback — preencher slots vazios ────
    for tag_slug, pos_cfg in cfg.HOMEPAGE_POSITIONS.items():
        limit = pos_cfg["limit"]
        cat_filter = pos_cfg["cat_filter"]
        require_tag = pos_cfg.get("require_tag")
        current = selections.get(tag_slug, [])
        
        if len(current) >= limit:
            continue  # já preenchido
        
        # Não fazer fallback para posições com require_tag (ex: consolidada)
        if require_tag:
            continue
        
        needed = limit - len(current)
        
        for post in by_date:
            if needed <= 0:
                break
            
            post_id = post["post_id"]
            
            if post_id in used_ids:
                continue
                
            # Recusar post no fallback se fortemente penalizado (score < 0)
            if post.get("score", 0) < 0:
                continue
            
            # Para posições com cat_filter, exigir categoria correta
            post_cats = set(post.get("categories", []))
            if cat_filter is not None:
                if not post_cats & cat_filter:
                    continue
            
            is_destaque = tag_slug in ("home-manchete", "home-submanchete")
            src_domain = ""
            if is_destaque:
                violation = False
                for cat in post_cats:
                    if category_destaque_counts.get(cat, 0) >= getattr(cfg, "MAX_SAME_CATEGORY_DESTAQUE", 2):
                        violation = True
                        break
                        
                src = post.get("source_url", "")
                src_domain = urlparse(src).netloc.lower() if src else ""
                if src_domain and source_top5_counts.get(src_domain, 0) >= getattr(cfg, "MAX_SAME_SOURCE_TOP5", 1):
                    violation = True
                    
                if violation:
                    continue
            
            current.append(post_id)
            used_ids.add(post_id)
            needed -= 1
            
            if is_destaque:
                for cat in post_cats:
                    category_destaque_counts[cat] = category_destaque_counts.get(cat, 0) + 1
                if src_domain:
                    source_top5_counts[src_domain] = source_top5_counts.get(src_domain, 0) + 1
        
        selections[tag_slug] = current
    
    # ── Logging ──────────────────────────────────────
    for tag_slug, post_ids in selections.items():
        limit = cfg.HOMEPAGE_POSITIONS[tag_slug]["limit"]
        if post_ids:
            logger.info(
                "Posição %s: %d/%d posts",
                tag_slug, len(post_ids), limit,
            )
        else:
            logger.warning("Posição %s: VAZIA (sem posts compatíveis)", tag_slug)
    
    return selections


# ─── Log no DB ───────────────────────────────────────

def create_log_table():
    """Cria tabela de log se não existir."""
    conn = get_db_connection()
    prefix = cfg.TABLE_PREFIX
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {prefix}curator_log (
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    cycle_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    post_id BIGINT UNSIGNED,
                    position VARCHAR(32),
                    score INT,
                    score_objective INT,
                    score_llm INT,
                    INDEX idx_cycle (cycle_at),
                    INDEX idx_post (post_id)
                )
            """)
        conn.commit()
    finally:
        conn.close()


def log_cycle(selections: dict[str, list[int]], scored_map: dict[int, dict]):
    """Registra o ciclo de curadoria no banco."""
    logger = logging.getLogger("curator")
    conn = get_db_connection()
    prefix = cfg.TABLE_PREFIX
    try:
        with conn.cursor() as cur:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for tag_slug, post_ids in selections.items():
                for post_id in post_ids:
                    info = scored_map.get(post_id, {})
                    cur.execute(f"""
                        INSERT INTO {prefix}curator_log
                        (cycle_at, post_id, position, score, score_objective, score_llm)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        now,
                        post_id,
                        tag_slug,
                        info.get("score_total", 0),
                        info.get("score_objetivo", 0),
                        info.get("score_llm", 0),
                    ))
        conn.commit()
    except Exception as e:
        logger.warning("Erro ao logar ciclo: %s", e)
    finally:
        conn.close()


# ─── Ciclo principal ─────────────────────────────────

def run_cycle(dry_run: bool = False):
    """Executa um ciclo completo de curadoria."""
    logger = logging.getLogger("curator")
    start_time = time.time()
    
    logger.info("=" * 60)
    logger.info("CURATOR AGENT — Início do ciclo %s",
                "[DRY-RUN]" if dry_run else "")
    logger.info("=" * 60)
    
    # 1. Buscar posts recentes
    logger.info("Fase 1: Buscando posts (janela: %dh)...", cfg.CURATOR_WINDOW_HOURS)
    posts = fetch_recent_posts(cfg.CURATOR_WINDOW_HOURS)
    
    if not posts:
        logger.warning("Nenhum post encontrado. Encerrando ciclo.")
        return
    
    # 2. Calcular scores
    logger.info("Fase 2: Calculando scores de %d posts...", len(posts))
    llm_budget = {"remaining": cfg.LLM_MAX_CALLS_PER_CYCLE}
    scored_posts = []
    scored_map = {}  # post_id → breakdown
    
    for post in posts:
        total_score, breakdown = scorer.score_post(post, llm_budget)
        
        if total_score < 0:
            continue  # eliminado
        
        post["score"] = total_score
        scored_posts.append(post)
        scored_map[post["post_id"]] = breakdown
    
    logger.info(
        "Scoring concluído: %d posts válidos (de %d), %d chamadas LLM usadas",
        len(scored_posts), len(posts),
        cfg.LLM_MAX_CALLS_PER_CYCLE - llm_budget["remaining"],
    )
    
    # 3. Top posts por score
    scored_posts.sort(key=lambda p: p["score"], reverse=True)
    logger.info("Top 10 por score:")
    for i, p in enumerate(scored_posts[:10]):
        logger.info(
            "  %2d. [%3d pts] %s",
            i + 1, p["score"], p["post_title"][:70],
        )
    
    # 4. Decisão de manchete via LLM Premium
    manchete_candidates = scored_posts[:5]  # Top 5 para decisão
    if manchete_candidates:
        headline_idx = scorer.decide_headline([
            {
                "post_id": p["post_id"],
                "post_title": p["post_title"],
                "post_excerpt": p["post_excerpt"],
                "score": p["score"],
            }
            for p in manchete_candidates
        ])
        
        # Reordenar: colocar o escolhido como primeiro
        if headline_idx > 0 and headline_idx < len(manchete_candidates):
            chosen = manchete_candidates.pop(headline_idx)
            manchete_candidates.insert(0, chosen)
            # Atualizar lista geral
            scored_posts = [
                p for p in scored_posts if p["post_id"] != chosen["post_id"]
            ]
            scored_posts.insert(0, chosen)
        
        logger.info("Manchete escolhida: %s", manchete_candidates[0]["post_title"][:70])
    
    # 5. Selecionar posts para cada posição
    logger.info("Fase 3: Distribuindo posts nas posições...")
    selections = select_positions(scored_posts)
    
    # Resumo
    total_selected = sum(len(ids) for ids in selections.values())
    logger.info("Total posts selecionados: %d", total_selected)
    
    # 6. Aplicar tags
    logger.info("Fase 4: Aplicando tags %s...", "[DRY-RUN]" if dry_run else "")
    results = tagger.apply_all_positions(selections, dry_run=dry_run)
    
    # 7. Log no DB
    if not dry_run:
        logger.info("Fase 5: Registrando ciclo no banco...")
        log_cycle(selections, scored_map)

    # 8. Fase 6: Verificação de Imagem unificada
    if not dry_run:
        logger.info("Fase 6: Verificando/curando imagens dos destaques selecionados...")
        try:
            sys.path.insert(0, "/home/bitnami")
            from curador_imagens_unificado import get_curador
            
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    # Obter posts sem imagem
                    for tag_slug, post_ids in selections.items():
                        for post_id in post_ids:
                            info = next((p for p in scored_posts if p["post_id"] == post_id), None)
                            if info and not info.get("featured_media"):
                                logger.info(f"Post {post_id} sem imagem. Acionando curador unificado...")
                                
                                curador = get_curador()
                                media_id, _ = curador.get_featured_image(
                                    html_content=info.get("post_content", ""),
                                    source_url=info.get("source_url", ""),
                                    title=info.get("post_title", ""),
                                    keywords=" ".join(info.get("tags", [])[:3])
                                )
                                if media_id:
                                    # Update no banco (postmeta)
                                    cur.execute(
                                        f"INSERT INTO {cfg.TABLE_PREFIX}postmeta (post_id, meta_key, meta_value) VALUES (%s, '_thumbnail_id', %s)",
                                        (post_id, media_id)
                                    )
                                    logger.info(f"Fase 6: Imagem {media_id} atribuída ao post {post_id}.")
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Erro na Fase 6 (Verificação de Imagens): {e}")
            
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("Ciclo concluído em %.1fs", elapsed)
    logger.info("=" * 60)
    
    # Resumo final
    for tag_slug, result in results.items():
        status = "✓" if result["errors"] == 0 else "⚠"
        logger.info(
            "  %s %s: %d aplicadas, %d erros",
            status, tag_slug, result["applied"], result["errors"],
        )


# ─── Entry point ─────────────────────────────────────

def main():
    logger = setup_logging()
    
    # Flags
    dry_run = cfg.CURATOR_DRY_RUN or "--dry-run" in sys.argv
    
    try:
        # Garantir tabela de log
        create_log_table()
        
        # Executar ciclo
        run_cycle(dry_run=dry_run)
        
    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário.")
    except Exception as e:
        logger.exception("Erro fatal no Curator Agent: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
