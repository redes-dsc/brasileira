"""Agente Reporter: extrai, redige, otimiza SEO e publica."""

from __future__ import annotations

import json
from dataclasses import dataclass

from reporter.content_extractor import extrair_conteudo_fonte
from reporter.publisher import publicar_no_wordpress
from reporter.seo_optimizer import otimizar_seo
from reporter.writer import redigir_artigo


@dataclass(slots=True)
class ReporterResult:
    post_id: int | None
    publicado: bool
    modelo_redacao: str | None
    modelo_seo: str | None


class ReporterAgent:
    """Pipeline principal do Reporter V3."""

    def __init__(self, router, wp_client):
        self.router = router
        self.wp_client = wp_client

    async def processar(self, raw_article: dict) -> ReporterResult:
        extraction = await extrair_conteudo_fonte(
            url=raw_article.get("url", ""),
            resumo_original=raw_article.get("resumo", ""),
        )

        redacao = await redigir_artigo(
            router=self.router,
            titulo=raw_article.get("titulo", ""),
            conteudo=extraction["conteudo"],
            categoria=raw_article.get("categoria", "ultimas_noticias"),
        )
        redacao_json = _parse_json_safe(redacao["raw"], fallback_title=raw_article.get("titulo", ""))

        seo = await otimizar_seo(
            router=self.router,
            titulo=redacao_json.get("titulo", raw_article.get("titulo", "")),
            resumo=redacao_json.get("resumo", raw_article.get("resumo", "")),
        )
        seo_json = _parse_json_safe(seo["raw"], fallback_title=redacao_json.get("titulo", ""))

        wp_payload = {
            "title": redacao_json.get("titulo") or raw_article.get("titulo", ""),
            "content": redacao_json.get("corpo") or extraction["conteudo"],
            "excerpt": redacao_json.get("resumo") or raw_article.get("resumo", ""),
            "slug": seo_json.get("slug"),
            "meta": {"seo_title": seo_json.get("title_seo"), "meta_description": seo_json.get("meta_description")},
            "categories": [raw_article.get("categoria_wp_id", 1)],
            "tags": raw_article.get("wp_tags", []),
        }

        published = await publicar_no_wordpress(self.wp_client, wp_payload)

        return ReporterResult(
            post_id=published.get("id"),
            publicado=bool(published.get("id")),
            modelo_redacao=redacao.get("modelo"),
            modelo_seo=seo.get("modelo"),
        )


def _parse_json_safe(raw: str, fallback_title: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        return {"titulo": fallback_title, "corpo": raw, "resumo": raw[:240]}
