import hashlib
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from newsroom_v3.integrations.redis_client import RedisClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DedupKey:
    normalized_url: str
    url_hash: str
    content_hash: str
    simhash: Optional[str] = None
    sim_lsh_bands: tuple[str, ...] = ()
    etag: Optional[str] = None


class Deduplicator:
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.ttl = 72 * 3600  # 72h retention as per V3 requirements

    async def is_duplicate(self, key: DedupKey) -> bool:
        client = await self.redis.get_client()

        # Layer 1: ETag fingerprint (HTTP cache semantics)
        if key.etag and await client.exists(f"dedup:etag:{key.etag}"):
            logger.info("Duplicate found (ETag): %s", key.etag)
            return True

        # Layer 2: Normalized URL guard in Redis (fast hot-path)
        if await client.exists(f"dedup:url:{key.normalized_url}"):
            logger.info("Duplicate found (URL): %s", key.normalized_url)
            return True

        # Layer 3: Content hash (title+date+url)
        if await client.exists(f"dedup:hash:{key.content_hash}"):
            logger.info("Duplicate found (Content Hash): %s", key.content_hash)
            return True

        # Layer 4: SimHash LSH bands (near-duplicate)
        for band in key.sim_lsh_bands:
            if await client.exists(f"dedup:simband:{band}"):
                logger.info("Near-duplicate found (SimHash band): %s", band)
                return True

        if key.simhash and await client.exists(f"dedup:sim:{key.simhash}"):
            logger.info("Duplicate found (SimHash exact): %s", key.simhash)
            return True

        return False

    async def mark_seen(self, key: DedupKey) -> None:
        """Marks the item as seen in Redis."""
        client = await self.redis.get_client()
        async with client.pipeline() as pipe:
            if key.etag:
                await pipe.set(f"dedup:etag:{key.etag}", "1", ex=self.ttl)
            await pipe.set(f"dedup:url:{key.normalized_url}", "1", ex=self.ttl)
            await pipe.set(f"dedup:hash:{key.content_hash}", "1", ex=self.ttl)
            if key.simhash:
                await pipe.set(f"dedup:sim:{key.simhash}", "1", ex=self.ttl)
            for band in key.sim_lsh_bands:
                await pipe.set(f"dedup:simband:{band}", "1", ex=self.ttl)
            await pipe.execute()


def normalize_url(url: str) -> str:
    stripped = url.strip()
    parsed = urlsplit(stripped)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    filtered_query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ]
    query = urlencode(filtered_query, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _simhash_hex(text: str) -> str:
    tokens = [t for t in text.lower().split() if t]
    if not tokens:
        tokens = ["_empty_"]
    bits = [0] * 64
    for token in tokens:
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            bits[i] += 1 if (h >> i) & 1 else -1
    value = 0
    for i, score in enumerate(bits):
        if score > 0:
            value |= 1 << i
    return f"{value:016x}"


def _simhash_bands(simhash_hex: str, bands: int = 4) -> tuple[str, ...]:
    band_size = len(simhash_hex) // bands
    return tuple(simhash_hex[i * band_size : (i + 1) * band_size] for i in range(bands))


def build_hash(title: str, published_at: str, url: str, etag: str | None = None) -> DedupKey:
    normalized = normalize_url(url)
    url_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    content_payload = f"{title.strip()}|{published_at.strip()}|{normalized}"
    content_hash = hashlib.sha256(content_payload.encode("utf-8")).hexdigest()
    sim_payload = f"{title.strip()} {published_at.strip()}"
    simhash = _simhash_hex(sim_payload)
    bands = _simhash_bands(simhash)

    return DedupKey(
        normalized_url=normalized,
        url_hash=url_hash,
        content_hash=content_hash,
        simhash=simhash,
        sim_lsh_bands=bands,
        etag=etag,
    )
