from newsroom_v3.llm.tier_config import resolve_tier


def test_resolve_tier_redacao_artigo() -> None:
    assert resolve_tier('redacao_artigo') == 'premium'


def test_resolve_tier_default() -> None:
    assert resolve_tier('unknown_task') == 'padrao'
