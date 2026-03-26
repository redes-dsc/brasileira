from __future__ import annotations

from worker_pool.collector import DeduplicationEngine


def test_normalize_url() -> None:
    dedup = DeduplicationEngine()
    assert (
        dedup.normalize_url("https://www.example.com/news/?utm_source=twitter")
        == "https://example.com/news"
    )
    assert dedup.normalize_url("https://example.com/news/") == "https://example.com/news"
    assert dedup.normalize_url("http://WWW.Example.COM/Path") == "http://example.com/Path"


def test_normalize_title() -> None:
    dedup = DeduplicationEngine()
    assert (
        dedup.normalize_title("Governo Anuncia Pacote de Investimentos")
        == "governo anuncia pacote de investimentos"
    )
    assert (
        dedup.normalize_title("Inflação cai para 3,5% em março")
        == "inflacao cai para 35 em marco"
    )


def test_simhash_similar_texts() -> None:
    dedup = DeduplicationEngine()
    hash1 = dedup.compute_simhash("governo anuncia novo pacote de investimentos em infraestrutura")
    hash2 = dedup.compute_simhash("governo anuncia novo pacote de investimentos em infra-estrutura federal")
    assert dedup.hamming_distance(hash1, hash2) <= 12


def test_simhash_different_texts() -> None:
    dedup = DeduplicationEngine()
    hash1 = dedup.compute_simhash("governo anuncia novo pacote de investimentos")
    hash2 = dedup.compute_simhash("time de futebol vence campeonato estadual")
    assert dedup.hamming_distance(hash1, hash2) > 10


def test_content_hash_ignores_case_and_time() -> None:
    dedup = DeduplicationEngine()
    hash1 = dedup.compute_content_hash(
        "Governo anuncia pacote", "agenciabrasil.ebc.com.br", "2026-03-26"
    )
    hash2 = dedup.compute_content_hash(
        "governo anuncia pacote", "agenciabrasil.ebc.com.br", "2026-03-26T10:30:00"
    )
    assert hash1 == hash2
