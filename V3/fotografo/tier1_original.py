"""Tier 1: Extração de imagem original da fonte com hierarchy de 5 níveis."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# CDNs de publicidade a serem filtradas
AD_CDNS = frozenset({
    "doubleclick.net", "googlesyndication.com", "taboola.com", "outbrain.com",
    "adnxs.com", "criteo.com", "facebook.com/tr", "amazon-adsystem.com",
    "googleadservices.com", "ads.yahoo.com", "serving-sys.com",
})

NON_EDITORIAL = frozenset({
    "logo", "icon", "sprite", "avatar", "banner", "widget", "badge",
    "button", "arrow", "share", "social", "whatsapp", "facebook", "twitter",
    "instagram", "youtube", "linkedin", "pinterest", "tiktok",
    "1x1", "pixel", "tracking", "ad-", "ads-", "advert",
})

MIN_DIMENSION = 300


def is_ad_image(url: str) -> bool:
    """Verifica se URL é de CDN publicitária ou padrão não-editorial."""
    url_lower = url.lower()
    for cdn in AD_CDNS:
        if cdn in url_lower:
            return True
    for pattern in NON_EDITORIAL:
        if pattern in url_lower:
            return True
    return False


class Tier1Extractor:
    """Extrai imagem original da página fonte com 5 níveis de fallback."""

    async def extract(self, html_content: Optional[str], url_fonte: str, og_image: Optional[str] = None) -> dict[str, Any]:
        """Tenta extrair imagem original.

        Hierarchy:
        1. JSON-LD (schema.org image)
        2. og:image
        3. twitter:image
        4. Primeira <img> dentro de <article>
        5. Maior imagem na página
        """
        if not html_content:
            # Se temos og_image do RSS, usar direto
            if og_image and not is_ad_image(og_image):
                return {"success": True, "url": og_image, "source": "rss_og_image", "tier": 1}
            return {"success": False, "reason": "sem HTML disponível"}

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "lxml")

        # Nível 1: JSON-LD
        img = self._extract_jsonld(soup)
        if img and not is_ad_image(img):
            return {"success": True, "url": self._normalize_url(img, url_fonte), "source": "json_ld", "tier": 1}

        # Nível 2: og:image (se não veio do RSS ou é diferente)
        img = self._extract_og_image(soup)
        if img and not is_ad_image(img):
            return {"success": True, "url": self._normalize_url(img, url_fonte), "source": "og_image", "tier": 1}

        # og_image do RSS como fallback
        if og_image and not is_ad_image(og_image):
            return {"success": True, "url": og_image, "source": "rss_og_image", "tier": 1}

        # Nível 3: twitter:image
        img = self._extract_twitter_image(soup)
        if img and not is_ad_image(img):
            return {"success": True, "url": self._normalize_url(img, url_fonte), "source": "twitter_image", "tier": 1}

        # Nível 4: Primeira <img> em <article>
        img = self._extract_article_image(soup)
        if img and not is_ad_image(img):
            return {"success": True, "url": self._normalize_url(img, url_fonte), "source": "article_img", "tier": 1}

        # Nível 5: Maior imagem na página
        img = self._extract_largest_image(soup)
        if img and not is_ad_image(img):
            return {"success": True, "url": self._normalize_url(img, url_fonte), "source": "largest_img", "tier": 1}

        return {"success": False, "reason": "nenhuma imagem editorial encontrada"}

    def _extract_jsonld(self, soup) -> Optional[str]:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, list):
                    data = data[0]
                img = data.get("image") or data.get("thumbnailUrl") or data.get("primaryImageOfPage")
                if isinstance(img, dict):
                    img = img.get("url") or img.get("contentUrl")
                if isinstance(img, list):
                    img = img[0] if img else None
                if isinstance(img, str) and img:
                    return img
            except Exception:
                continue
        return None

    def _extract_og_image(self, soup) -> Optional[str]:
        tag = soup.find("meta", property="og:image")
        return tag["content"] if tag and tag.get("content") else None

    def _extract_twitter_image(self, soup) -> Optional[str]:
        tag = soup.find("meta", attrs={"name": "twitter:image"})
        if not tag:
            tag = soup.find("meta", attrs={"property": "twitter:image"})
        return tag["content"] if tag and tag.get("content") else None

    def _extract_article_image(self, soup) -> Optional[str]:
        article = soup.find("article") or soup.find(attrs={"role": "main"})
        if not article:
            return None
        for img in article.find_all("img", src=True):
            src = img.get("src", "")
            width = img.get("width", "0")
            height = img.get("height", "0")
            try:
                if int(width) >= MIN_DIMENSION or int(height) >= MIN_DIMENSION:
                    return src
            except (ValueError, TypeError):
                # Se não tem dimensões, aceita se não é tiny (sem dimensão informada)
                if not any(skip in src.lower() for skip in ("1x1", "pixel", "spacer")):
                    return src
        return None

    def _extract_largest_image(self, soup) -> Optional[str]:
        best = None
        best_area = 0
        for img in soup.find_all("img", src=True):
            if is_ad_image(img.get("src", "")):
                continue
            try:
                w = int(img.get("width", 0))
                h = int(img.get("height", 0))
                area = w * h
                if area > best_area and w >= MIN_DIMENSION:
                    best_area = area
                    best = img["src"]
            except (ValueError, TypeError):
                continue
        return best

    def _normalize_url(self, url: str, base_url: str) -> str:
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http"):
            return urljoin(base_url, url)
        return url
