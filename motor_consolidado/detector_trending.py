"""
Detecção de temas em alta (trending) via clusterização de títulos.
Usa TF-IDF + cosseno (scikit-learn) com fallback para SequenceMatcher.
"""

import logging
import re
import unicodedata
from difflib import SequenceMatcher

from config_consolidado import (
    STOPWORDS_PT, SIMILARITY_THRESHOLD,
    MIN_SOURCES_TRENDING,
)

logger = logging.getLogger("motor_consolidado")

# ── Normalização ─────────────────────────────────────────

def normalize_title(title: str) -> str:
    """Normaliza título: lowercase, sem acentos, sem stopwords."""
    # Lowercase
    text = title.lower().strip()
    # Remover acentos
    text = unicodedata.normalize("NFD", text)
    text = re.sub(r"[\u0300-\u036f]", "", text)
    # Remover pontuação
    text = re.sub(r"[^\w\s]", " ", text)
    # Remover stopwords
    words = [w for w in text.split() if w not in STOPWORDS_PT and len(w) > 2]
    return " ".join(words)


# ── Clusterização com TF-IDF ────────────────────────────

def _cluster_tfidf(titles: list[dict]) -> list[list[int]]:
    """Agrupa títulos por similaridade TF-IDF + cosseno. Retorna lista de clusters (índices)."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        logger.warning("scikit-learn não disponível, usando fallback SequenceMatcher")
        return _cluster_sequencematcher(titles)

    normalized = [normalize_title(t["title"]) for t in titles]

    # Filtrar títulos vazios após normalização
    valid_indices = [i for i, n in enumerate(normalized) if n.strip()]
    if len(valid_indices) < 2:
        return []

    valid_texts = [normalized[i] for i in valid_indices]

    vectorizer = TfidfVectorizer(max_features=5000)
    tfidf_matrix = vectorizer.fit_transform(valid_texts)
    sim_matrix = (tfidf_matrix * tfidf_matrix.T).tocsr()

    # Union-Find para agrupamento
    parent = list(range(len(valid_indices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(valid_indices)):
        row = sim_matrix.getrow(i)
        for j, val in zip(row.indices, row.data):
            if j > i and val >= SIMILARITY_THRESHOLD:
                union(i, j)

    # Montar clusters
    clusters_map = {}
    for i in range(len(valid_indices)):
        root = find(i)
        clusters_map.setdefault(root, []).append(valid_indices[i])

    return list(clusters_map.values())


def _cluster_sequencematcher(titles: list[dict]) -> list[list[int]]:
    """Fallback: agrupa títulos com SequenceMatcher O(n²)."""
    normalized = [normalize_title(t["title"]) for t in titles]

    parent = list(range(len(titles)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            if not normalized[i] or not normalized[j]:
                continue
            ratio = SequenceMatcher(None, normalized[i], normalized[j]).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                union(i, j)

    clusters_map = {}
    for i in range(len(titles)):
        root = find(i)
        clusters_map.setdefault(root, []).append(i)

    return list(clusters_map.values())


# ── Detecção de Trending ─────────────────────────────────
def detect_trending(all_titles: list[dict]) -> list[dict]:
    """
    Pipeline completo de detecção de temas em alta.
    Retorna lista de tópicos trending, ordenados por prioridade.

    Cada tópico: {
        topic_label: str,
        titles: list[dict],
        sources: set[str],
        urls: list[str],
        is_manchete: bool,
        is_mais_lida: bool,
        score: float,
    }
    """
    if len(all_titles) < 5:
        logger.warning("Poucos títulos para detectar trending (%d)", len(all_titles))
        return []

    clusters = _cluster_tfidf(all_titles)

    trending = []
    for cluster_indices in clusters:
        cluster_titles = [all_titles[i] for i in cluster_indices]
        sources = {t["portal_name"] for t in cluster_titles}
        urls = [t["url"] for t in cluster_titles if t.get("url")]
        has_manchete = any(t.get("is_manchete") for t in cluster_titles)
        has_mais_lida = any(t.get("is_mais_lida") for t in cluster_titles)
        mais_lida_count = sum(1 for t in cluster_titles if t.get("is_mais_lida"))

        # Critérios de trending:
        # >= 3 fontes diferentes, OU
        # >= 2 "mais lidas", OU
        # >= 2 manchetes TIER 1
        manchete_count = sum(1 for t in cluster_titles if t.get("is_manchete") and t.get("section") == "tier1")

        is_trending = (
            len(sources) >= MIN_SOURCES_TRENDING
            or mais_lida_count >= 2
            or manchete_count >= 2
        )

        if not is_trending:
            continue

        # Usar o título mais longo como label do tópico
        topic_label = max(cluster_titles, key=lambda t: len(t["title"]))["title"]

        # O tema é aceito sem restrição de proibição

        # Calcular score de prioridade
        score = (
            len(sources) * 10    # mais fontes = mais relevante
            + mais_lida_count * 5
            + manchete_count * 3
            + (5 if has_manchete else 0)
            + (3 if has_mais_lida else 0)
        )

        trending.append({
            "topic_label": topic_label,
            "titles": cluster_titles,
            "sources": sources,
            "urls": list(set(urls)),
            "is_manchete": has_manchete,
            "is_mais_lida": has_mais_lida,
            "score": score,
        })

    # Ordenar por score descrescente
    trending.sort(key=lambda t: t["score"], reverse=True)

    logger.info(
        "Temas trending detectados: %d (de %d clusters)",
        len(trending), len(clusters),
    )
    for t in trending[:5]:
        logger.info(
            "  [score=%d, %d fontes] %s",
            t["score"], len(t["sources"]), t["topic_label"][:60],
        )

    return trending


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from scraper_homes import scrape_all_portals
    titles = scrape_all_portals(cycle_number=1)
    trending = detect_trending(titles)
    print(f"\n{'='*60}")
    print(f"TRENDING: {len(trending)} temas detectados")
    print(f"{'='*60}")
    for t in trending:
        print(f"\n[SCORE {t['score']}] {t['topic_label'][:80]}")
        print(f"  Fontes: {', '.join(t['sources'])}")
        print(f"  URLs: {len(t['urls'])}")
