from base64 import b64encode

import httpx


class WordPressClient:
    def __init__(self, base_url: str, user: str, app_password: str) -> None:
        self.base_url = base_url.rstrip('/')
        token = b64encode(f"{user}:{app_password}".encode('utf-8')).decode('utf-8')
        self.headers = {'Authorization': f'Basic {token}'}

    async def publish_post(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.base_url}/wp-json/wp/v2/posts", json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()
