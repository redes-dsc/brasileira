from __future__ import annotations

from consolidador.consolidador import ConsolidacaoAction, ConsolidadorAgent


def test_decidir_acao_0_1_2() -> None:
    assert ConsolidadorAgent.decidir_acao(0) == ConsolidacaoAction.ACIONAR_REPORTER
    assert ConsolidadorAgent.decidir_acao(1) == ConsolidacaoAction.REESCREVER
    assert ConsolidadorAgent.decidir_acao(2) == ConsolidacaoAction.CONSOLIDAR
    assert ConsolidadorAgent.decidir_acao(5) == ConsolidacaoAction.CONSOLIDAR
