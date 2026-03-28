"""
Módulo de gerenciamento de TAGs editoriais — Home Curator Agent

Responsável por:
  - Limpar tags de curadoria de posts anteriores
  - Aplicar novas tags de curadoria via WP REST API
"""

import logging
import time

import requests
from requests.auth import HTTPBasicAuth

import curator_config as cfg

logger = logging.getLogger("curator")

AUTH = HTTPBasicAuth(cfg.WP_USER, cfg.WP_APP_PASS)


# ─── Buscar posts com tags de curadoria ──────────────

def get_posts_with_curator_tags() -> list[dict]:
    """
    Busca todos os posts que possuem qualquer tag de curadoria.
    Retorna lista de {id, tags} via REST API.
    """
    all_posts = []
    
    for tag_slug, tag_id in cfg.TAG_IDS.items():
        
        try:
            resp = requests.get(
                f"{cfg.WP_API_BASE}/posts",
                params={
                    "tags": tag_id,
                    "per_page": 100,
                    "status": "publish",
                    "_fields": "id,tags",
                },
                auth=AUTH,
                timeout=cfg.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                for post in resp.json():
                    # Evitar duplicatas
                    if not any(p["id"] == post["id"] for p in all_posts):
                        all_posts.append(post)
            
            time.sleep(0.3)
        except Exception as e:
            logger.warning("Erro ao buscar posts com tag %s: %s", tag_slug, e)
    
    return all_posts


# ─── Limpar tags de curadoria ────────────────────────

def clear_curator_tags(dry_run: bool = False) -> int:
    """
    Remove TODAS as tags de curadoria (home-*) de todos os posts.
    Preserva tags normais e as tags especiais (consolidada, home-urgente).
    
    Returns:
        Número de posts limpos.
    """
    # Tags de posição a remover (as que controlam onde o post aparece)
    position_tag_ids = set()
    for tag_slug, tag_id in cfg.TAG_IDS.items():
        if tag_slug.startswith("home-") and tag_slug not in ("home-especial", "home-urgente"):
            position_tag_ids.add(tag_id)
    
    posts = get_posts_with_curator_tags()
    cleaned = 0
    
    for post in posts:
        post_id = post["id"]
        current_tags = post.get("tags", [])
        
        # Remover apenas tags de posição
        new_tags = [t for t in current_tags if t not in position_tag_ids]
        
        if new_tags == current_tags:
            continue  # nenhuma tag de curadoria a remover
        
        if dry_run:
            logger.info(
                "[DRY-RUN] Limparia post %d: %d tags → %d tags",
                post_id, len(current_tags), len(new_tags),
            )
            cleaned += 1
            continue
        
        try:
            resp = requests.post(
                f"{cfg.WP_API_BASE}/posts/{post_id}",
                json={"tags": new_tags},
                auth=AUTH,
                timeout=cfg.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                cleaned += 1
                logger.debug("Limpo post %d: removidas %d tags de curadoria",
                             post_id, len(current_tags) - len(new_tags))
            else:
                logger.warning("Erro ao limpar post %d: HTTP %d", post_id, resp.status_code)
            
            time.sleep(cfg.WP_PATCH_DELAY)
        except Exception as e:
            logger.warning("Erro ao limpar post %d: %s", post_id, e)
    
    logger.info("Tags de curadoria limpas: %d posts afetados", cleaned)
    return cleaned


# ─── Aplicar tag a um post ───────────────────────────

def apply_tag(post_id: int, tag_id: int, current_tags: list[int] = None,
              dry_run: bool = False) -> bool:
    """
    Adiciona uma tag a um post (preservando as existentes).
    
    Args:
        post_id: ID do post
        tag_id: ID da tag a adicionar
        current_tags: tags atuais (se None, busca via API)
        dry_run: se True, não executa
    
    Returns:
        True se sucesso.
    """
    if current_tags is None:
        try:
            resp = requests.get(
                f"{cfg.WP_API_BASE}/posts/{post_id}",
                params={"_fields": "id,tags"},
                auth=AUTH,
                timeout=cfg.HTTP_TIMEOUT,
            )
            if resp.status_code == 200:
                current_tags = resp.json().get("tags", [])
            else:
                current_tags = []
        except Exception as e:
            logger.warning("Erro ao buscar tags do post %d: %s", post_id, e)
            current_tags = []
    
    if tag_id in current_tags:
        return True  # já tem
    
    new_tags = list(set(current_tags + [tag_id]))
    
    if dry_run:
        logger.info("[DRY-RUN] Aplicaria tag %d ao post %d", tag_id, post_id)
        return True
    
    try:
        resp = requests.post(
            f"{cfg.WP_API_BASE}/posts/{post_id}",
            json={"tags": new_tags},
            auth=AUTH,
            timeout=cfg.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            return True
        else:
            logger.warning("Erro ao aplicar tag %d ao post %d: HTTP %d",
                           tag_id, post_id, resp.status_code)
            return False
    except Exception as e:
        logger.warning("Erro ao aplicar tag %d ao post %d: %s", tag_id, post_id, e)
        return False


# ─── Aplicar todas as posições ───────────────────────

def apply_all_positions(selections: dict[str, list[int]],
                        dry_run: bool = False) -> dict:
    """
    Aplica as tags de curadoria para todas as posições selecionadas.
    
    Args:
        selections: {tag_slug: [post_id, post_id, ...]}
        dry_run: se True, não executa
    
    Returns:
        {tag_slug: {"applied": N, "errors": N}}
    """
    results = {tag_slug: {"applied": 0, "errors": 0} for tag_slug in selections}
    
    # 1. Mapear as tags de curadoria que controlamos
    position_tag_ids = set()
    for tag_slug, tag_id in cfg.TAG_IDS.items():
        if tag_slug.startswith("home-") or tag_slug == "consolidada":
            position_tag_ids.add(tag_id)
            
    # 2. Obter estado atual dos posts
    logger.info("Buscando estado atual das tags de curadoria...")
    current_posts = get_posts_with_curator_tags()
    current_state = {p["id"]: set(p.get("tags", [])) for p in current_posts}
    
    # 3. Construir estado desejado
    desired_state = {}
    for tag_slug, post_ids in selections.items():
        tag_id = cfg.TAG_IDS.get(tag_slug)
        if not tag_id:
            logger.warning("Tag slug desconhecido: %s", tag_slug)
            continue
        for post_id in post_ids:
            if post_id not in desired_state:
                desired_state[post_id] = set()
            desired_state[post_id].add(tag_id)
            
    # 4. Calcular e aplicar posts que precisam de atualização
    all_post_ids = set(current_state.keys()) | set(desired_state.keys())
    
    for post_id in all_post_ids:
        curr_tags = current_state.get(post_id)
        if curr_tags is None:
            try:
                resp = requests.get(
                    f"{cfg.WP_API_BASE}/posts/{post_id}",
                    params={"_fields": "id,tags"},
                    auth=AUTH,
                    timeout=cfg.HTTP_TIMEOUT,
                )
                if resp.status_code == 200:
                    curr_tags = set(resp.json().get("tags", []))
                else:
                    curr_tags = set()
            except Exception:
                curr_tags = set()
                
        des_position_tags = desired_state.get(post_id, set())
        curr_position_tags = curr_tags & position_tag_ids
        
        if curr_position_tags == des_position_tags:
            continue

        new_tags = (curr_tags - position_tag_ids) | des_position_tags
        
        if dry_run:
            logger.info("[DRY-RUN] Post %d: curadoria de %s para %s", 
                        post_id, curr_position_tags, des_position_tags)
            continue
            
        success = False
        # Fallback e Retries incorporados
        max_retries = getattr(cfg, "WP_RETRY_COUNT", 3)
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    f"{cfg.WP_API_BASE}/posts/{post_id}",
                    json={"tags": list(new_tags)},
                    auth=AUTH,
                    timeout=cfg.HTTP_TIMEOUT,
                )
                if resp.status_code in (200, 201):
                    logger.debug("Post %d atualizado de atomicamente", post_id)
                    success = True
                    break
                else:
                    logger.warning("Erro HTTP %d ao aplicar tags post %d (tnt %d)", 
                                   resp.status_code, post_id, attempt)
                    time.sleep(cfg.WP_PATCH_DELAY)
            except Exception as e:
                logger.warning("Falha aplicacao post %d (tnt %d): %s", post_id, attempt, e)
                time.sleep(cfg.WP_PATCH_DELAY)
        
        for ts, tid in cfg.TAG_IDS.items():
            if tid in des_position_tags and ts in results:
                if success:
                    results[ts]["applied"] += 1
                else:
                    results[ts]["errors"] += 1

        time.sleep(cfg.WP_PATCH_DELAY)

    return results
