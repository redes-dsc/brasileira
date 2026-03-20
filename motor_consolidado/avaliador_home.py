#!/usr/bin/env python3
"""
Avaliador de Homepage (Benchmarking Agent)

Compara a cobertura editorial da brasileira.news com os portais TIER 1,
identifica gaps de cobertura, mede frescor e diversidade, e gera
relatório com ações recomendadas via LLM.

Uso:
    python3 avaliador_home.py              # relatório completo
    python3 avaliador_home.py --quick      # só gap analysis (sem LLM)

Agendamento (crontab):
    0 4,10,16,22 * * * /home/bitnami/venv/bin/python3 \
        /home/bitnami/motor_consolidado/avaliador_home.py >> /home/bitnami/logs/benchmark_cron.log 2>&1
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

# Setup paths
_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(Path("/home/bitnami/motor_rss")))
sys.path.insert(0, str(Path("/home/bitnami/motor_scrapers")))
sys.path.insert(0, str(Path("/home/bitnami")))

from config_consolidado import TIER1_PORTALS, STOPWORDS_PT, LOG_DIR
import config
import db

# ── Logging ──────────────────────────────────────────────

BENCHMARK_DIR = LOG_DIR / "benchmark"
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("avaliador")


def _setup_logging():
    """Configure logging handlers — called once from main()."""
    if logger.handlers:
        return  # avoid duplicate handlers
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = logging.FileHandler(LOG_DIR / "benchmark_cron.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)


# ── Constantes ───────────────────────────────────────────

SIMILARITY_MATCH = 0.40      # threshold para considerar "coberto"
HOMEPAGE_WINDOW_HOURS = 6    # janela de posts recentes para comparar
MAX_LLM_INPUT_CHARS = 6000   # limitar input do LLM


# ═══════════════════════════════════════════════════════════
# PHASE 1 — Scrape Both Sides
# ═══════════════════════════════════════════════════════════

def fetch_brasileira_homepage() -> dict:
    """
    Busca o estado atual da homepage do brasileira.news via DB.
    Retorna dict com posts por posição + posts recentes.
    """
    prefix = config.TABLE_PREFIX

    homepage = {
        "manchete": [],
        "submanchete": [],
        "editorias": {},
        "recent_all": [],
        "stats": {},
    }

    try:
        with db.get_db() as conn:
            cursor = conn.cursor()

            # Posts com tags home-* nas últimas N horas
            cursor.execute(f"""
                SELECT p.ID, p.post_title, p.post_date, p.post_excerpt,
                       t.slug as tag_slug,
                       (SELECT GROUP_CONCAT(t2.name SEPARATOR ', ')
                        FROM {prefix}term_relationships tr2
                        JOIN {prefix}term_taxonomy tt2 ON tr2.term_taxonomy_id = tt2.term_taxonomy_id
                        JOIN {prefix}terms t2 ON tt2.term_id = t2.term_id
                        WHERE tr2.object_id = p.ID AND tt2.taxonomy = 'category'
                       ) as categories
                FROM {prefix}posts p
                JOIN {prefix}term_relationships tr ON p.ID = tr.object_id
                JOIN {prefix}term_taxonomy tt ON tr.term_taxonomy_id = tt.term_taxonomy_id
                JOIN {prefix}terms t ON tt.term_id = t.term_id
                WHERE p.post_status = 'publish'
                  AND p.post_type = 'post'
                  AND tt.taxonomy = 'post_tag'
                  AND t.slug LIKE 'home-%%'
                  AND p.post_date >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                ORDER BY p.post_date DESC
            """, (HOMEPAGE_WINDOW_HOURS * 2,))

            for row in cursor.fetchall():
                tag = row["tag_slug"]
                entry = {
                    "id": row["ID"],
                    "title": row["post_title"],
                    "date": str(row["post_date"]),
                    "categories": row["categories"] or "",
                }

                if tag == "home-manchete":
                    homepage["manchete"].append(entry)
                elif tag == "home-submanchete":
                    homepage["submanchete"].append(entry)
                else:
                    editoria = tag.replace("home-", "")
                    homepage["editorias"].setdefault(editoria, []).append(entry)

            # Todos os posts recentes (para verificar cobertura)
            cursor.execute(f"""
                SELECT p.ID, p.post_title, p.post_date,
                       (SELECT GROUP_CONCAT(t2.name SEPARATOR ', ')
                        FROM {prefix}term_relationships tr2
                        JOIN {prefix}term_taxonomy tt2 ON tr2.term_taxonomy_id = tt2.term_taxonomy_id
                        JOIN {prefix}terms t2 ON tt2.term_id = t2.term_id
                        WHERE tr2.object_id = p.ID AND tt2.taxonomy = 'category'
                       ) as categories,
                       (SELECT GROUP_CONCAT(t3.slug SEPARATOR ',')
                        FROM {prefix}term_relationships tr3
                        JOIN {prefix}term_taxonomy tt3 ON tr3.term_taxonomy_id = tt3.term_taxonomy_id
                        JOIN {prefix}terms t3 ON tt3.term_id = t3.term_id
                        WHERE tr3.object_id = p.ID AND tt3.taxonomy = 'post_tag'
                       ) as all_tags
                FROM {prefix}posts p
                WHERE p.post_status = 'publish'
                  AND p.post_type = 'post'
                  AND p.post_date >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                ORDER BY p.post_date DESC
                LIMIT 100
            """, (HOMEPAGE_WINDOW_HOURS,))

            for row in cursor.fetchall():
                tags = (row.get("all_tags") or "").split(",")
                homepage["recent_all"].append({
                    "id": row["ID"],
                    "title": row["post_title"],
                    "date": str(row["post_date"]),
                    "categories": row["categories"] or "",
                    "has_home_tag": any(t.startswith("home-") for t in tags),
                    "is_consolidada": "consolidada" in tags,
                })

            cursor.close()

        # Stats
        homepage["stats"]["total_recent"] = len(homepage["recent_all"])
        homepage["stats"]["on_homepage"] = sum(1 for p in homepage["recent_all"] if p["has_home_tag"])
        homepage["stats"]["editorias_count"] = len(homepage["editorias"])
        homepage["stats"]["has_manchete"] = len(homepage["manchete"]) > 0
        homepage["stats"]["consolidadas"] = sum(1 for p in homepage["recent_all"] if p["is_consolidada"])

    except Exception as e:
        logger.error("Erro ao buscar homepage brasileira.news: %s", e)

    return homepage


def fetch_tier1_titles() -> list[dict]:
    """Raspa títulos dos portais TIER 1 via scraper_homes."""
    from scraper_homes import scrape_all_portals
    return scrape_all_portals(cycle_number=1)


def fetch_tier1_trending(titles: list[dict]) -> list[dict]:
    """Detecta temas trending nos portais TIER 1."""
    from detector_trending import detect_trending
    return detect_trending(titles)


# ═══════════════════════════════════════════════════════════
# PHASE 2 — Coverage Gap Analysis
# ═══════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    """Normaliza para comparação."""
    import unicodedata
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = re.sub(r"[\u0300-\u036f]", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_matching_post(topic_title: str, posts: list[dict]) -> dict | None:
    """Busca post na brasileira.news que cubra o mesmo tema."""
    norm_topic = _normalize(topic_title)
    best_match = None
    best_ratio = 0.0

    for post in posts:
        norm_post = _normalize(post["title"])
        ratio = SequenceMatcher(None, norm_topic, norm_post).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = post

    if best_ratio >= SIMILARITY_MATCH:
        return {**best_match, "similarity": best_ratio}
    return None


def analyze_coverage(trending: list[dict], homepage: dict) -> list[dict]:
    """
    Para cada tema trending, classifica a cobertura da brasileira.news.
    COVERED: post existe + tem tag home-*
    PUBLISHED_NOT_HIGHLIGHTED: post existe sem tag home-*
    MISSING: não tem post correspondente
    """
    all_posts = homepage["recent_all"]
    gaps = []

    for topic in trending:
        label = topic["topic_label"]
        sources = list(topic["sources"])
        score = topic["score"]

        matching = _find_matching_post(label, all_posts)

        if matching:
            if matching.get("has_home_tag"):
                status = "COVERED"
            else:
                status = "PUBLISHED_NOT_HIGHLIGHTED"
        else:
            status = "MISSING"

        gaps.append({
            "topic": label,
            "sources": sources,
            "source_count": len(sources),
            "trending_score": score,
            "status": status,
            "matching_post": matching.get("title") if matching else None,
            "matching_id": matching.get("id") if matching else None,
            "similarity": matching.get("similarity", 0) if matching else 0,
        })

    return gaps


# ═══════════════════════════════════════════════════════════
# PHASE 3 — Freshness & Diversity Metrics
# ═══════════════════════════════════════════════════════════

def calculate_metrics(homepage: dict) -> dict:
    """Calcula métricas de frescor e diversidade."""
    now = datetime.now()
    metrics = {}

    # Frescor da manchete
    if homepage["manchete"]:
        manchete_date = homepage["manchete"][0].get("date", "")
        try:
            md = datetime.fromisoformat(str(manchete_date))
            metrics["manchete_age_min"] = int((now - md).total_seconds() / 60)
        except (ValueError, TypeError):
            metrics["manchete_age_min"] = None
    else:
        metrics["manchete_age_min"] = None

    # Frescor dos destaques (submanchete)
    ages = []
    for post in homepage.get("submanchete", []):
        try:
            pd = datetime.fromisoformat(str(post.get("date", "")))
            ages.append(int((now - pd).total_seconds() / 60))
        except (ValueError, TypeError):
            pass
    metrics["submanchete_avg_age_min"] = int(sum(ages) / len(ages)) if ages else None

    # Frescor médio geral dos posts na home
    home_ages = []
    for post in homepage["recent_all"]:
        if post.get("has_home_tag"):
            try:
                pd = datetime.fromisoformat(str(post.get("date", "")))
                home_ages.append(int((now - pd).total_seconds() / 60))
            except (ValueError, TypeError):
                pass
    metrics["homepage_avg_age_min"] = int(sum(home_ages) / len(home_ages)) if home_ages else None

    # Diversidade editorial
    all_cats = set()
    for post in homepage["recent_all"]:
        if post.get("has_home_tag"):
            cats = post.get("categories", "")
            for c in cats.split(","):
                c = c.strip()
                if c:
                    all_cats.add(c)
    metrics["editorias_on_homepage"] = sorted(all_cats)
    metrics["editorias_count"] = len(all_cats)

    # Categorias de todos os posts vs categorias na home
    all_recent_cats = set()
    for post in homepage["recent_all"]:
        cats = post.get("categories", "")
        for c in cats.split(","):
            c = c.strip()
            if c:
                all_recent_cats.add(c)
    metrics["editorias_total_available"] = len(all_recent_cats)
    metrics["editorias_missing_from_home"] = sorted(all_recent_cats - all_cats)

    # Stats básicos
    metrics["total_posts_recent"] = homepage["stats"].get("total_recent", 0)
    metrics["posts_on_homepage"] = homepage["stats"].get("on_homepage", 0)
    metrics["consolidadas_count"] = homepage["stats"].get("consolidadas", 0)
    metrics["has_manchete"] = homepage["stats"].get("has_manchete", False)

    return metrics


# ═══════════════════════════════════════════════════════════
# PHASE 4 — LLM Editorial Review
# ═══════════════════════════════════════════════════════════

def llm_editorial_review(gaps: list[dict], metrics: dict, homepage: dict) -> dict | None:
    """
    Envia resumo ao LLM para avaliação editorial e sugestões.
    Usa TIER_CONSOLIDATOR (Claude → GPT-4o → Gemini Pro) para análise premium.
    """
    from llm_router import call_llm, TIER_CONSOLIDATOR

    # Montar resumo dos dados
    manchete_title = homepage["manchete"][0]["title"] if homepage["manchete"] else "(sem manchete)"
    submanchetes = [p["title"] for p in homepage.get("submanchete", [])]

    editorias_str = "\n".join([
        f"  - {ed}: {len(posts)} posts"
        for ed, posts in homepage["editorias"].items()
    ]) or "  (nenhuma editoria com destaque)"

    gaps_str = ""
    for g in gaps:
        emoji = {"COVERED": "✓", "PUBLISHED_NOT_HIGHLIGHTED": "⚠", "MISSING": "✗"}
        gaps_str += f"\n  {emoji.get(g['status'], '?')} [{g['status']}] {g['topic'][:60]} ({', '.join(g['sources'][:3])})"

    metrics_str = (
        f"Manchete age: {metrics.get('manchete_age_min', '?')} min\n"
        f"Avg homepage age: {metrics.get('homepage_avg_age_min', '?')} min\n"
        f"Editorias on home: {metrics.get('editorias_count', 0)}\n"
        f"Missing editorias: {', '.join(metrics.get('editorias_missing_from_home', []))}\n"
        f"Posts on homepage: {metrics.get('posts_on_homepage', 0)} / {metrics.get('total_posts_recent', 0)}\n"
        f"Consolidated articles: {metrics.get('consolidadas_count', 0)}"
    )

    system_prompt = (
        "Você é um consultor editorial sênior avaliando o desempenho "
        "do portal brasileira.news em comparação com os grandes portais brasileiros. "
        "Seja direto, objetivo e propositivo."
    )

    user_prompt = f"""Avalie o estado editorial atual do portal brasileira.news.

=== HOMEPAGE ATUAL ===
Manchete: {manchete_title}
Submanchetes: {', '.join(s[:50] for s in submanchetes) or '(nenhuma)'}

Editorias com destaque:
{editorias_str}

=== COBERTURA vs PORTAIS TIER 1 (G1, Folha, UOL, CNN, Metrópoles, Poder360) ===
{gaps_str or '  Nenhum trending detectado neste momento.'}

=== MÉTRICAS ===
{metrics_str}

---

Retorne APENAS JSON válido com estas chaves:
- score: número inteiro de 0 a 100 (nota geral da homepage)
- pontos_fortes: lista de 2-3 pontos fortes identificados
- pontos_fracos: lista de 2-3 fraquezas ou oportunidades perdidas
- acoes_recomendadas: lista de 3 ações concretas e específicas para melhorar
- resumo: parágrafo de 2-3 frases resumindo a avaliação
"""

    try:
        result, provider = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt[:MAX_LLM_INPUT_CHARS],
            tier=TIER_CONSOLIDATOR,
            parse_json=True,
        )

        if result:
            result["_provider"] = provider
            logger.info("Avaliação LLM via %s: score=%s", provider, result.get("score", "?"))
            return result
        else:
            logger.warning("LLM não retornou avaliação")

    except Exception as e:
        logger.error("Erro na avaliação LLM: %s", e)

    return None


# ═══════════════════════════════════════════════════════════
# PHASE 5 — Report Generation
# ═══════════════════════════════════════════════════════════

def generate_report(gaps: list[dict], metrics: dict, llm_review: dict | None, homepage: dict) -> tuple[str, dict]:
    """Gera relatório MD (legível) e JSON (estruturado)."""

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    file_prefix = now.strftime("%Y-%m-%d_%H")

    # ── Cobertura ──
    total_trending = len(gaps)
    covered = sum(1 for g in gaps if g["status"] == "COVERED")
    published_no_highlight = sum(1 for g in gaps if g["status"] == "PUBLISHED_NOT_HIGHLIGHTED")
    missing = sum(1 for g in gaps if g["status"] == "MISSING")
    coverage_rate = (covered / total_trending * 100) if total_trending > 0 else 0

    # ── Markdown Report ──
    md = []
    md.append(f"# Benchmark: brasileira.news vs TIER 1")
    md.append(f"**Data:** {timestamp}\n")

    md.append("## Cobertura de Trending")
    md.append(f"| Métrica | Valor |")
    md.append(f"|---------|-------|")
    md.append(f"| Temas trending TIER 1 | {total_trending} |")
    md.append(f"| Cobertos na home | {covered} ({coverage_rate:.0f}%) |")
    md.append(f"| Publicados sem destaque | {published_no_highlight} |")
    md.append(f"| Ausentes | {missing} |")
    md.append("")

    if gaps:
        md.append("### Detalhamento")
        for g in gaps:
            icon = {"COVERED": "✅", "PUBLISHED_NOT_HIGHLIGHTED": "⚠️", "MISSING": "❌"}.get(g["status"], "❓")
            md.append(f"- {icon} **{g['status']}**: {g['topic'][:70]}")
            md.append(f"  - Fontes: {', '.join(g['sources'][:4])} | Score: {g['trending_score']}")
            if g.get("matching_post"):
                md.append(f"  - Match: \"{g['matching_post'][:60]}\" (sim={g['similarity']:.2f})")
        md.append("")

    md.append("## Métricas de Frescor")
    md.append(f"| Métrica | Valor |")
    md.append(f"|---------|-------|")
    manchete_age = metrics.get("manchete_age_min")
    md.append(f"| Idade da manchete | {manchete_age} min |" if manchete_age else "| Idade da manchete | N/A |")
    avg_age = metrics.get("homepage_avg_age_min")
    md.append(f"| Idade média da home | {avg_age} min |" if avg_age else "| Idade média da home | N/A |")
    md.append(f"| Posts na homepage | {metrics.get('posts_on_homepage', 0)} / {metrics.get('total_posts_recent', 0)} |")
    md.append(f"| Matérias consolidadas | {metrics.get('consolidadas_count', 0)} |")
    md.append("")

    md.append("## Diversidade Editorial")
    md.append(f"- **Editorias na home:** {metrics.get('editorias_count', 0)}")
    editorias = metrics.get("editorias_on_homepage", [])
    if editorias:
        md.append(f"  - {', '.join(editorias)}")
    missing_ed = metrics.get("editorias_missing_from_home", [])
    if missing_ed:
        md.append(f"- **Editorias ausentes da home:** {', '.join(missing_ed[:5])}")
    md.append("")

    if llm_review:
        score = llm_review.get("score", "?")
        md.append(f"## Avaliação Editorial LLM: {score}/100")
        md.append("")

        resumo = llm_review.get("resumo", "")
        if resumo:
            md.append(f"> {resumo}")
            md.append("")

        fortes = llm_review.get("pontos_fortes", [])
        if fortes:
            md.append("### Pontos Fortes")
            for f in fortes:
                md.append(f"- ✅ {f}")
            md.append("")

        fracos = llm_review.get("pontos_fracos", [])
        if fracos:
            md.append("### Pontos Fracos")
            for f in fracos:
                md.append(f"- ⚠️ {f}")
            md.append("")

        acoes = llm_review.get("acoes_recomendadas", [])
        if acoes:
            md.append("### Ações Recomendadas")
            for i, a in enumerate(acoes, 1):
                md.append(f"{i}. {a}")
            md.append("")

    md_text = "\n".join(md)

    # ── JSON Report ──
    report_json = {
        "timestamp": timestamp,
        "coverage": {
            "total_trending": total_trending,
            "covered": covered,
            "published_not_highlighted": published_no_highlight,
            "missing": missing,
            "coverage_rate": round(coverage_rate, 1),
        },
        "gaps": gaps,
        "metrics": metrics,
        "llm_review": llm_review,
        "homepage_state": {
            "manchete": homepage.get("manchete", []),
            "submanchete": homepage.get("submanchete", []),
            "editorias_count": len(homepage.get("editorias", {})),
            "total_recent": homepage["stats"].get("total_recent", 0),
        },
    }

    # Salvar
    md_path = BENCHMARK_DIR / f"{file_prefix}.md"
    json_path = BENCHMARK_DIR / f"{file_prefix}.json"

    md_path.write_text(md_text, encoding="utf-8")
    json_path.write_text(json.dumps(report_json, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    logger.info("Relatórios salvos: %s, %s", md_path, json_path)

    return md_text, report_json


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def run_benchmark(quick: bool = False) -> dict:
    """Executa benchmark completo."""
    start = time.time()

    logger.info("=" * 60)
    logger.info("AVALIADOR DE HOMEPAGE — BENCHMARK")
    logger.info("Horário: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    # Phase 1: Scrape
    logger.info("----- PHASE 1: Scraping -----")
    homepage = fetch_brasileira_homepage()
    logger.info("brasileira.news: %d posts recentes, %d na home",
                homepage["stats"].get("total_recent", 0),
                homepage["stats"].get("on_homepage", 0))

    tier1_titles = fetch_tier1_titles()
    logger.info("TIER 1: %d títulos raspados", len(tier1_titles))

    # Phase 2: Coverage Gap
    logger.info("----- PHASE 2: Coverage Analysis -----")
    trending = fetch_tier1_trending(tier1_titles)
    logger.info("Trending detectados: %d", len(trending))

    gaps = analyze_coverage(trending, homepage)
    covered = sum(1 for g in gaps if g["status"] == "COVERED")
    missing = sum(1 for g in gaps if g["status"] == "MISSING")
    logger.info("Cobertura: %d cobertos, %d ausentes (de %d)", covered, missing, len(gaps))

    # Phase 3: Metrics
    logger.info("----- PHASE 3: Metrics -----")
    metrics = calculate_metrics(homepage)
    logger.info("Idade manchete: %s min | Editorias na home: %d",
                metrics.get("manchete_age_min", "N/A"),
                metrics.get("editorias_count", 0))

    # Phase 4: LLM Review (skip if --quick)
    llm_review = None
    if not quick:
        logger.info("----- PHASE 4: LLM Review -----")
        llm_review = llm_editorial_review(gaps, metrics, homepage)
        if llm_review:
            logger.info("Score LLM: %s/100", llm_review.get("score", "?"))
    else:
        logger.info("----- PHASE 4: SKIPPED (--quick) -----")

    # Phase 5: Report
    logger.info("----- PHASE 5: Report -----")
    md_text, report_json = generate_report(gaps, metrics, llm_review, homepage)

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info("BENCHMARK CONCLUÍDO em %.1fs", elapsed)
    if llm_review:
        logger.info("SCORE: %s/100", llm_review.get("score", "?"))
    logger.info("Cobertura: %.0f%% (%d/%d trending)",
                report_json["coverage"]["coverage_rate"],
                covered, len(gaps))
    logger.info("=" * 60)

    # Print resumo no stdout
    print(f"\n{'='*60}")
    print(md_text)
    print(f"{'='*60}\n")

    return report_json


def main():
    _setup_logging()
    quick = "--quick" in sys.argv
    try:
        db.ensure_control_table()
    except Exception:
        pass
    run_benchmark(quick=quick)


if __name__ == "__main__":
    main()
