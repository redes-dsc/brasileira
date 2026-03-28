import asyncio
import logging
import feedparser
from typing import Any

logger = logging.getLogger(__name__)


class RSSCollector:
    async def collect(self, feed_url: str) -> list[dict[str, Any]]:
        # feedparser is blocking, so we run it in an executor
        loop = asyncio.get_running_loop()
        parsed = await loop.run_in_executor(None, feedparser.parse, feed_url)
        if parsed.bozo:
            logger.warning("RSS parse reported bozo for %s: %s", feed_url, parsed.bozo_exception)

        items: list[dict[str, Any]] = []
        for entry in parsed.entries:
            items.append(
                {
                    'title': entry.get('title', ''),
                    'url': entry.get('link', ''),
                    'summary': entry.get('summary', ''),
                    'published': entry.get('published', ''),
                    'id': entry.get('id', ''),
                    'author': entry.get('author', ''),
                    'tags': [t.get('term', '') for t in entry.get('tags', [])],
                }
            )
        return items
