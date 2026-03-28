from newsroom_v3.ingestion.deduplicator import build_hash


def test_build_hash_consistent() -> None:
    a = build_hash('Titulo', '2026-03-26', 'https://site.com/noticia/')
    b = build_hash('Titulo', '2026-03-26', 'https://site.com/noticia')
    assert a.url_hash == b.url_hash
    assert a.content_hash == b.content_hash


def test_build_hash_ignores_utm_params() -> None:
    a = build_hash('Titulo', '2026-03-26', 'https://site.com/noticia?utm_source=x')
    b = build_hash('Titulo', '2026-03-26', 'https://site.com/noticia')
    assert a.url_hash == b.url_hash
