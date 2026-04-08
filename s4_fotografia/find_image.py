"""
Pipeline de Busca de Imagens — Sistema 4 Fotografia
brasileira.news · V2

Orquestrador de 3 fases para busca de imagem:
    Phase 1: Always (Agência Brasil)
    Phase 2: Conditional parallel (Câmara, Senado, CNJ, STF, MPF)
    Phase 3: Fallback sequential (Google, Flickr, Wikimedia, Pexels, Unsplash)
"""

import sys
import time
import hashlib
import logging
import concurrent.futures
from pathlib import Path
from typing import Optional

# Adiciona o diretório do projeto ao path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_rss.llm_router import call_llm, TIER_ECONOMY
from s4_fotografia.sources import (
    SOURCES_ORDERED,
    PHASE_1_SOURCES,
    PHASE_2_SOURCES,
    PHASE_3_SOURCES,
    SOURCES_BY_NAME,
    get_relevant_sources,
)
from s4_fotografia.supabase_ops import (
    log_image_search,
    upsert_used_image,
    update_query_stats,
    check_image_used,
)
from s4_fotografia.wp_upload import process_and_upload

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

QUALITY_THRESHOLD = 5.0  # Score mínimo para aceitar imagem (0-10)
MAX_CANDIDATES_PER_SOURCE = 5  # Limitar candidatos para avaliação LLM
MAX_REUSE_COUNT = 2  # Permite reuso se used_count <= este valor
PHASE_2_TIMEOUT = 15  # Timeout para execução paralela da Phase 2


# ─────────────────────────────────────────────────────────────────────────────
# Prompt de Avaliação de Qualidade
# ─────────────────────────────────────────────────────────────────────────────

QUALITY_SYSTEM_PROMPT = """Avalie a relevância desta imagem para o artigo jornalístico.

Critérios (score de 0 a 10):
- Relevância editorial: a imagem representa visualmente o tema do artigo?
- Adequação contextual: a imagem é apropriada para jornalismo brasileiro?
- Qualidade esperada: pela descrição/fonte, parece ser uma imagem de boa qualidade?

PENALIZE:
- Imagens genéricas sem relação com o fato (-3 pontos)
- Stock óbvio em notícia política/judicial (-2 pontos)
- Imagens de celebridades para notícias institucionais (-2 pontos)
- Sem informação suficiente para avaliar (-1 ponto)

BONIFIQUE:
- Imagem de fonte governamental oficial (+1 ponto)
- Imagem com pessoa/entidade citada no artigo (+2 pontos)
- Imagem recente de evento relacionado (+1 ponto)

Responda APENAS com JSON:
{"score": 7.5, "reason": "Justificativa breve em uma linha"}"""


# ─────────────────────────────────────────────────────────────────────────────
# Função Principal
# ─────────────────────────────────────────────────────────────────────────────


def find_image(
    query: str,
    post_id: int,
    category_slug: str,
    editorial_context: Optional[dict] = None
) -> Optional[dict]:
    """
    Executa pipeline de 3 fases para encontrar imagem.

    PHASE 1 — ALWAYS (sequential):
        1. Agência Brasil (EBC) — fonte prioritária, sempre consultada

    PHASE 2 — CONDITIONAL (parallel):
        Apenas se o artigo menciona o órgão (entidades, categoria, domínio)
        2. Agência Câmara
        3. Agência Senado
        4. CNJ
        5. STF
        6. MPF
        → Se QUALQUER retornar resultado válido, usa e para

    PHASE 3 — FALLBACK (sequential):
        7. Google Images
        8. Flickr geral
        9. Wikimedia Commons
        10. Pexels
        11. Unsplash

    Args:
        query: Query de busca gerada por build_search_query()
        post_id: ID do post WordPress
        category_slug: Slug da categoria para estatísticas
        editorial_context: Contexto editorial do Sistema 3 (opcional)

    Returns:
        Dict com imagem selecionada ou None se nenhuma encontrada:
        {
            'url': str,
            'source': str,
            'author': str,
            'license': str,
            'description': str,
            'score': float,
            'media_id': int  # WordPress media ID após upload
        }
    """
    logger.info(f"[find_image] Iniciando pipeline 3-fases para post {post_id}, query: '{query}'")
    
    if not query or not query.strip():
        logger.warning(f"[find_image] Query vazia para post {post_id}")
        return None
    
    best_image = None
    main_topic = ""  # Para update_query_stats
    source_order = 0  # Track order across all phases

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 1: ALWAYS (Agência Brasil)
    # ─────────────────────────────────────────────────────────────────────────
    
    logger.info(f"[find_image] === PHASE 1: ALWAYS ===")
    
    for source_key, search_fn, source_name in PHASE_1_SOURCES:
        source_order += 1
        result = _search_and_evaluate_source(
            source_key=source_key,
            search_fn=search_fn,
            source_name=source_name,
            query=query,
            post_id=post_id,
            category_slug=category_slug,
            source_order=source_order,
        )
        
        if result:
            best_image = result
            main_topic = result.get("description", query.split()[0] if query else "")[:50]
            logger.info(f"[find_image] Phase 1 encontrou imagem de {source_key}")
            break  # Found valid image in Phase 1

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 2: CONDITIONAL (parallel)
    # ─────────────────────────────────────────────────────────────────────────
    
    if not best_image:
        logger.info(f"[find_image] === PHASE 2: CONDITIONAL ===")
        
        # Determine which Phase 2 sources are relevant
        relevant_sources = get_relevant_sources(editorial_context or {})
        
        if relevant_sources:
            logger.info(f"[find_image] Phase 2 sources relevantes: {relevant_sources}")
            
            result = _search_conditional_parallel(
                query=query,
                relevant_sources=relevant_sources,
                post_id=post_id,
                category_slug=category_slug,
                base_source_order=source_order,
            )
            
            if result:
                best_image = result
                main_topic = result.get("description", query.split()[0] if query else "")[:50]
                logger.info(f"[find_image] Phase 2 encontrou imagem de {result.get('source')}")
        else:
            logger.info(f"[find_image] Phase 2: Nenhuma fonte condicional relevante para o contexto")
        
        # Update source_order counter for Phase 3
        source_order += len(PHASE_2_SOURCES)

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 3: FALLBACK (sequential)
    # ─────────────────────────────────────────────────────────────────────────
    
    if not best_image:
        logger.info(f"[find_image] === PHASE 3: FALLBACK ===")
        
        for source_key, search_fn, source_name in PHASE_3_SOURCES:
            source_order += 1
            result = _search_and_evaluate_source(
                source_key=source_key,
                search_fn=search_fn,
                source_name=source_name,
                query=query,
                post_id=post_id,
                category_slug=category_slug,
                source_order=source_order,
            )
            
            if result:
                best_image = result
                main_topic = result.get("description", query.split()[0] if query else "")[:50]
                logger.info(f"[find_image] Phase 3 encontrou imagem de {source_key}")
                break

    # ─────────────────────────────────────────────────────────────────────────
    # Pós-processamento
    # ─────────────────────────────────────────────────────────────────────────

    if best_image:
        # Upload para WordPress
        media_id = _upload_image(best_image)
        
        if media_id:
            best_image["media_id"] = media_id
            
            # Registra imagem usada
            image_hash = hashlib.md5(best_image["url"].encode()).hexdigest()
            upsert_used_image(
                image_url=best_image["url"],
                image_hash=image_hash,
                post_id=post_id,
                source=best_image["source"],
                author=best_image.get("author"),
                license_type=best_image.get("license"),
            )
            
            # Atualiza estatísticas de query (sucesso)
            update_query_stats(
                category=category_slug,
                topic=main_topic,
                query=query,
                source=best_image["source"],
                success=True,
            )
            
            logger.info(f"[find_image] Sucesso! media_id={media_id} para post {post_id}")
            return best_image
        else:
            logger.error(f"[find_image] Falha no upload da imagem para post {post_id}")
            # Atualiza estatísticas como falha (upload falhou)
            update_query_stats(
                category=category_slug,
                topic=main_topic,
                query=query,
                source=best_image["source"],
                success=False,
            )
            return None

    # Pipeline exaurido sem encontrar imagem
    logger.warning(f"[find_image] Pipeline 3-fases exaurido sem imagem para post {post_id}")
    update_query_stats(
        category=category_slug,
        topic=main_topic or (query.split()[0] if query else ""),
        query=query,
        source="pipeline_exausto",
        success=False,
    )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 Parallel Execution
# ─────────────────────────────────────────────────────────────────────────────


def _search_conditional_parallel(
    query: str,
    relevant_sources: list[str],
    post_id: int,
    category_slug: str,
    base_source_order: int,
) -> Optional[dict]:
    """
    Search Phase 2 sources in parallel, return best result.
    
    Args:
        query: Search query
        relevant_sources: List of source keys to search (e.g., ['cnj', 'stf'])
        post_id: WordPress post ID
        category_slug: Category slug
        base_source_order: Starting source order number
    
    Returns:
        Best evaluated image dict or None
    """
    all_results = []
    source_order_map = {}
    
    # Build map of relevant sources
    phase_2_by_key = {key: (fn, name) for key, fn, name in PHASE_2_SOURCES}
    
    # Determine source order for each relevant source
    for idx, (source_key, _, _) in enumerate(PHASE_2_SOURCES, start=1):
        source_order_map[source_key] = base_source_order + idx
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(relevant_sources)) as executor:
        futures = {}
        
        for source_key in relevant_sources:
            if source_key not in phase_2_by_key:
                continue
            
            search_fn, source_name = phase_2_by_key[source_key]
            future = executor.submit(search_fn, query)
            futures[future] = (source_key, source_name)
        
        for future in concurrent.futures.as_completed(futures, timeout=PHASE_2_TIMEOUT):
            source_key, source_name = futures[future]
            start_time = time.time()
            
            try:
                source_results = future.result()
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                if not source_results:
                    log_image_search(
                        post_id=post_id,
                        search_query=query,
                        source_tried=source_key,
                        source_order=source_order_map.get(source_key, 0),
                        results_found=0,
                        image_selected=None,
                        image_applied=False,
                        quality_score=None,
                        rejection_reason="nenhum resultado encontrado (Phase 2)",
                        processing_time_ms=processing_time_ms,
                    )
                    continue
                
                logger.info(f"[find_image] Phase 2 {source_name}: {len(source_results)} resultado(s)")
                
                # Filter already used images
                filtered_results = _filter_already_used(source_results)
                
                if not filtered_results:
                    log_image_search(
                        post_id=post_id,
                        search_query=query,
                        source_tried=source_key,
                        source_order=source_order_map.get(source_key, 0),
                        results_found=len(source_results),
                        image_selected=None,
                        image_applied=False,
                        quality_score=None,
                        rejection_reason="todas as imagens já foram usadas (Phase 2)",
                        processing_time_ms=processing_time_ms,
                    )
                    continue
                
                # Add source_key to each result for tracking
                for r in filtered_results:
                    r["source_key"] = source_key
                    r["source_name"] = source_name
                    r["source_order"] = source_order_map.get(source_key, 0)
                
                all_results.extend(filtered_results[:MAX_CANDIDATES_PER_SOURCE])
                
            except concurrent.futures.TimeoutError:
                logger.warning(f"[find_image] Phase 2 {source_name}: timeout")
                log_image_search(
                    post_id=post_id,
                    search_query=query,
                    source_tried=source_key,
                    source_order=source_order_map.get(source_key, 0),
                    results_found=0,
                    image_selected=None,
                    image_applied=False,
                    quality_score=None,
                    rejection_reason="timeout (Phase 2)",
                    processing_time_ms=PHASE_2_TIMEOUT * 1000,
                )
            except Exception as e:
                logger.warning(f"[find_image] Phase 2 {source_name} error: {e}")
                log_image_search(
                    post_id=post_id,
                    search_query=query,
                    source_tried=source_key,
                    source_order=source_order_map.get(source_key, 0),
                    results_found=0,
                    image_selected=None,
                    image_applied=False,
                    quality_score=None,
                    rejection_reason=f"erro: {str(e)[:100]} (Phase 2)",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
    
    if not all_results:
        return None
    
    # Evaluate all candidates and select best
    best_candidate = _evaluate_candidates(
        candidates=all_results,
        query=query,
        category_slug=category_slug,
    )
    
    if best_candidate and best_candidate.get("score", 0) >= QUALITY_THRESHOLD:
        source_key = best_candidate.get("source_key", best_candidate.get("source", ""))
        source_order = best_candidate.get("source_order", 0)
        
        log_image_search(
            post_id=post_id,
            search_query=query,
            source_tried=source_key,
            source_order=source_order,
            results_found=len(all_results),
            image_selected=best_candidate["url"],
            image_applied=True,
            quality_score=best_candidate["score"],
            rejection_reason=None,
            processing_time_ms=0,  # Already logged per-source
        )
        
        return {
            "url": best_candidate["url"],
            "source": source_key,
            "author": best_candidate.get("author") or best_candidate.get("credit", ""),
            "license": best_candidate.get("license", ""),
            "description": best_candidate.get("description", ""),
            "score": best_candidate["score"],
        }
    
    # Log rejection for best candidate if it didn't meet threshold
    if best_candidate:
        rejection_score = best_candidate.get("score", 0)
        log_image_search(
            post_id=post_id,
            search_query=query,
            source_tried=best_candidate.get("source_key", "phase_2_aggregate"),
            source_order=best_candidate.get("source_order", 0),
            results_found=len(all_results),
            image_selected=best_candidate["url"],
            image_applied=False,
            quality_score=rejection_score,
            rejection_reason=f"score {rejection_score:.1f} < {QUALITY_THRESHOLD} (Phase 2)",
            processing_time_ms=0,
        )
    
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Single Source Evaluation
# ─────────────────────────────────────────────────────────────────────────────


def _search_and_evaluate_source(
    source_key: str,
    search_fn,
    source_name: str,
    query: str,
    post_id: int,
    category_slug: str,
    source_order: int,
) -> Optional[dict]:
    """
    Search a single source and evaluate results.
    
    Args:
        source_key: Source identifier
        search_fn: Search function to call
        source_name: Human-readable source name
        query: Search query
        post_id: WordPress post ID
        category_slug: Category slug
        source_order: Order in pipeline
    
    Returns:
        Best evaluated image dict or None
    """
    start_time = time.time()
    
    logger.info(f"[find_image] [{source_order}/11] Tentando {source_name} ({source_key})...")
    
    try:
        # 1. Execute search
        results = search_fn(query)
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        if not results:
            log_image_search(
                post_id=post_id,
                search_query=query,
                source_tried=source_key,
                source_order=source_order,
                results_found=0,
                image_selected=None,
                image_applied=False,
                quality_score=None,
                rejection_reason="nenhum resultado encontrado",
                processing_time_ms=processing_time_ms,
            )
            logger.debug(f"[find_image] {source_key}: nenhum resultado")
            return None
        
        logger.info(f"[find_image] {source_key}: {len(results)} resultado(s) encontrado(s)")
        
        # 2. Filter already-used images
        filtered_results = _filter_already_used(results)
        
        if not filtered_results:
            log_image_search(
                post_id=post_id,
                search_query=query,
                source_tried=source_key,
                source_order=source_order,
                results_found=len(results),
                image_selected=None,
                image_applied=False,
                quality_score=None,
                rejection_reason="todas as imagens já foram usadas",
                processing_time_ms=processing_time_ms,
            )
            logger.debug(f"[find_image] {source_key}: todas imagens já usadas")
            return None
        
        # 3. Evaluate candidates via LLM
        best_candidate = _evaluate_candidates(
            candidates=filtered_results[:MAX_CANDIDATES_PER_SOURCE],
            query=query,
            category_slug=category_slug,
        )
        
        if best_candidate and best_candidate.get("score", 0) >= QUALITY_THRESHOLD:
            # Image accepted!
            quality_score = best_candidate["score"]
            
            log_image_search(
                post_id=post_id,
                search_query=query,
                source_tried=source_key,
                source_order=source_order,
                results_found=len(results),
                image_selected=best_candidate["url"],
                image_applied=True,
                quality_score=quality_score,
                rejection_reason=None,
                processing_time_ms=processing_time_ms,
            )
            
            return {
                "url": best_candidate["url"],
                "source": source_key,
                "author": best_candidate.get("author") or best_candidate.get("credit", ""),
                "license": best_candidate.get("license", ""),
                "description": best_candidate.get("description", ""),
                "score": quality_score,
            }
        
        else:
            # Score below threshold
            rejection_score = best_candidate.get("score", 0) if best_candidate else 0
            rejection_reason = (
                f"score {rejection_score:.1f} < {QUALITY_THRESHOLD}"
                if best_candidate
                else "avaliação LLM falhou"
            )
            
            log_image_search(
                post_id=post_id,
                search_query=query,
                source_tried=source_key,
                source_order=source_order,
                results_found=len(results),
                image_selected=best_candidate["url"] if best_candidate else None,
                image_applied=False,
                quality_score=rejection_score if best_candidate else None,
                rejection_reason=rejection_reason,
                processing_time_ms=processing_time_ms,
            )
            logger.debug(f"[find_image] {source_key}: rejeitado - {rejection_reason}")
            return None
    
    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.warning(f"[find_image] Erro em {source_key}: {e}")
        log_image_search(
            post_id=post_id,
            search_query=query,
            source_tried=source_key,
            source_order=source_order,
            results_found=0,
            image_selected=None,
            image_applied=False,
            quality_score=None,
            rejection_reason=f"erro: {str(e)[:100]}",
            processing_time_ms=processing_time_ms,
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Funções Auxiliares
# ─────────────────────────────────────────────────────────────────────────────


def _filter_already_used(results: list[dict]) -> list[dict]:
    """Filtra e penaliza imagens já utilizadas.
    
    NOTA: Esta função MODIFICA o score das imagens no dict de entrada
    (penaliza imagens já usadas em 30%) para priorizar imagens novas.
    """
    if not results:
        return results
    
    filtered = []
    for img in results:
        url = img.get("url", "")
        if not url:
            continue
        if check_image_used(url):
            logger.debug(f"[filter] Imagem já usada, permitindo com prioridade menor: {url[:60]}...")
            img["score"] = img.get("score", 0.5) * 0.7  # Penalizar score
        filtered.append(img)
    return filtered


def _evaluate_candidates(
    candidates: list[dict],
    query: str,
    category_slug: str,
) -> Optional[dict]:
    """
    Avalia candidatos via LLM e retorna o melhor.

    CE-4: Cada avaliação é uma chamada LLM isolada.

    Args:
        candidates: Lista de imagens candidatas
        query: Query de busca utilizada
        category_slug: Categoria do artigo

    Returns:
        Candidato com maior score, com 'score' e 'eval_reason' adicionados
    """
    if not candidates:
        return None

    # Se apenas um candidato, avalia diretamente
    if len(candidates) == 1:
        return _evaluate_single(candidates[0], query, category_slug)

    # Múltiplos candidatos: avalia cada um e pega o melhor
    best = None
    best_score = -1

    for candidate in candidates:
        evaluated = _evaluate_single(candidate, query, category_slug)
        if evaluated:
            score = evaluated.get("score", 0)
            if score > best_score:
                best_score = score
                best = evaluated

    return best


def _evaluate_single(
    candidate: dict,
    query: str,
    category_slug: str,
) -> Optional[dict]:
    """
    Avalia um único candidato via LLM.

    Args:
        candidate: Dict com dados da imagem
        query: Query de busca
        category_slug: Categoria do artigo

    Returns:
        Candidato com 'score' e 'eval_reason' adicionados
    """
    try:
        user_prompt = f"""IMAGEM A AVALIAR:
URL: {candidate.get('url', '')}
Fonte: {candidate.get('source', '')}
Título: {candidate.get('title', '')}
Descrição: {candidate.get('description', '')[:200]}
Crédito: {candidate.get('credit', '') or candidate.get('author', '')}

CONTEXTO:
Query de busca: {query}
Categoria do artigo: {category_slug}

Avalie (0-10):"""

        response, provider = call_llm(
            system_prompt=QUALITY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tier=TIER_ECONOMY,
            parse_json=True,
        )

        if response and isinstance(response, dict):
            score = float(response.get("score", 0))
            reason = response.get("reason", "")
            
            result = candidate.copy()
            result["score"] = score
            result["eval_reason"] = reason
            
            logger.debug(f"[evaluate] Score {score:.1f}: {reason[:50]}...")
            return result

    except Exception as e:
        logger.warning(f"[evaluate] Erro na avaliação LLM: {e}")

    # Fallback: retorna candidato com score médio
    result = candidate.copy()
    result["score"] = 5.0  # Score neutro
    result["eval_reason"] = "avaliação LLM falhou, score padrão"
    return result


def _upload_image(image_data: dict) -> Optional[int]:
    """
    Faz upload da imagem para WordPress.

    Args:
        image_data: Dict com url, author, license, description

    Returns:
        media_id do WordPress ou None se falhar
    """
    try:
        media_id = process_and_upload(
            image_url=image_data["url"],
            caption_text=image_data.get("description", ""),
            author=image_data.get("author", ""),
            license_type=image_data.get("license", ""),
            alt_text=image_data.get("description", "")[:125] if image_data.get("description") else "",
        )
        return media_id

    except Exception as e:
        logger.error(f"[upload] Erro no upload: {e}")
        return None
