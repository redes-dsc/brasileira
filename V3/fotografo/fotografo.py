"""Agente Fotógrafo com pipeline de 4 tiers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fotografo.clip_validator import CLIPValidator
from fotografo.query_generator import QueryGenerator
from fotografo.tier1_original import Tier1Original
from fotografo.tier2_stocks import Tier2Stocks
from fotografo.tier3_generative import Tier3Generative
from fotografo.tier4_placeholder import Tier4Placeholder


@dataclass(slots=True)
class ImageAttachedEvent:
    post_id: int
    article_id: str
    media_id: int | None
    tier_used: str
    api_used: str | None
    query_used: str | None
    clip_score: float | None
    image_url: str | None
    attribution: str
    ai_generated: bool
    total_time_ms: int
    rounds_attempted: int
    timestamp: datetime
    fotografo_id: str


class FotografoAgent:
    """Processa eventos article-published e garante featured image."""

    def __init__(self, router, wp_uploader, instance_id: str = "fotografo-01"):
        self.router = router
        self.wp_uploader = wp_uploader
        self.instance_id = instance_id
        self.query_gen = QueryGenerator(router)
        self.clip = CLIPValidator()
        self.tier1 = Tier1Original()
        self.tier2 = Tier2Stocks()
        self.tier3 = Tier3Generative()
        self.tier4 = Tier4Placeholder()

    async def process_event(self, event: dict) -> ImageAttachedEvent:
        import time

        start = time.time()
        post_id = int(event["post_id"])
        article_id = event.get("article_id", str(post_id))
        title = event.get("titulo", "")
        lead = event.get("lead", "")
        editoria = event.get("editoria", "default")
        url_fonte = event.get("url_fonte", "")
        html_fonte = event.get("html_fonte")

        queries = await self.query_gen.generate(title=title, content=lead, editoria=editoria, source_url=url_fonte)
        selected = None
        tier_used = "tier4"
        query_used = None

        result_t1 = await self.tier1.extract(url_fonte, html_fonte)
        if result_t1["success"]:
            candidate = result_t1["candidate"]
            score = await self.clip.score(candidate["url"], f"{title}. {lead}")
            if score >= 0.15:
                candidate["clip_score"] = score
                selected = candidate
                tier_used = "tier1"
                query_used = "og:image extraction"

        if selected is None:
            result_t2 = await self.tier2.search(queries.get("tier2", []))
            if result_t2["success"]:
                candidate = result_t2["candidate"]
                score = await self.clip.score(candidate["url"], f"{title}. {lead}")
                if score >= 0.17:
                    candidate["clip_score"] = score
                    selected = candidate
                    tier_used = "tier2"
                    query_used = result_t2.get("query_used")

        if selected is None:
            candidate = await self.tier3.generate(queries.get("tier3", []), article_title=title, editoria=editoria)
            if candidate is not None:
                selected = candidate
                tier_used = "tier3"
                query_used = candidate.get("ai_prompt")

        if selected is None:
            selected = self.tier4.get_placeholder(editoria)
            tier_used = "tier4"
            query_used = "placeholder"

        success, media_id = await self.wp_uploader.upload_and_attach(
            image_url=selected["url"],
            post_id=post_id,
            article_title=title,
            attribution=selected["attribution"],
            wp_media_id=selected.get("wp_media_id"),
        )

        elapsed = int((time.time() - start) * 1000)
        return ImageAttachedEvent(
            post_id=post_id,
            article_id=article_id,
            media_id=media_id if success else selected.get("wp_media_id"),
            tier_used=tier_used,
            api_used=selected.get("source_api"),
            query_used=query_used,
            clip_score=selected.get("clip_score"),
            image_url=selected.get("url"),
            attribution=selected.get("attribution", "Imagem ilustrativa"),
            ai_generated=bool(selected.get("ai_generated", False)),
            total_time_ms=elapsed,
            rounds_attempted=0,
            timestamp=datetime.utcnow(),
            fotografo_id=self.instance_id,
        )
