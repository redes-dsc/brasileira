"""Presets de layout por período do dia (horário de Brasília)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Fuso de Brasília (UTC-3)
BST = timezone(timedelta(hours=-3))


@dataclass
class LayoutPreset:
    """Preset de configuração do layout por período."""

    name: str               # matinal, horario_nobre, vespertino, noturno
    min_blocks: int
    max_blocks: int
    manchete_style: str     # hero_large, hero_split
    opiniao_prominent: bool
    newsletter_prominent: bool
    mais_lidas_prominent: bool
    all_editorias: bool     # mostrar todas editorias ou top N
    ad_frequency: int       # bloco de publicidade a cada N blocos editoriais


# Presets pré-definidos
_MATINAL = LayoutPreset(
    name="matinal",
    min_blocks=12,
    max_blocks=18,
    manchete_style="hero_split",
    opiniao_prominent=False,
    newsletter_prominent=True,
    mais_lidas_prominent=False,
    all_editorias=False,
    ad_frequency=4,
)

_HORARIO_NOBRE = LayoutPreset(
    name="horario_nobre",
    min_blocks=22,
    max_blocks=28,
    manchete_style="hero_large",
    opiniao_prominent=False,
    newsletter_prominent=False,
    mais_lidas_prominent=False,
    all_editorias=True,
    ad_frequency=3,
)

_VESPERTINO = LayoutPreset(
    name="vespertino",
    min_blocks=15,
    max_blocks=20,
    manchete_style="hero_large",
    opiniao_prominent=True,
    newsletter_prominent=False,
    mais_lidas_prominent=False,
    all_editorias=False,
    ad_frequency=4,
)

_NOTURNO = LayoutPreset(
    name="noturno",
    min_blocks=8,
    max_blocks=12,
    manchete_style="hero_split",
    opiniao_prominent=False,
    newsletter_prominent=False,
    mais_lidas_prominent=True,
    all_editorias=False,
    ad_frequency=5,
)


def get_current_preset() -> LayoutPreset:
    """Retorna o preset correspondente à hora atual em Brasília."""

    now = datetime.now(BST)
    hour = now.hour

    if 6 <= hour < 10:
        return _MATINAL
    elif (10 <= hour < 14) or (18 <= hour < 22):
        return _HORARIO_NOBRE
    elif 14 <= hour < 18:
        return _VESPERTINO
    else:
        return _NOTURNO
