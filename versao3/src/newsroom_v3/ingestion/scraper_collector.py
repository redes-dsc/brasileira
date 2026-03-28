from bs4 import BeautifulSoup
import httpx


class ScraperCollector:
    async def collect(self, source_url: str, item_selector: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(source_url)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        out: list[dict] = []
        for node in soup.select(item_selector):
            anchor = node.find('a')
            if not anchor:
                continue
            out.append({'title': anchor.get_text(strip=True), 'url': anchor.get('href', '')})
        return out
