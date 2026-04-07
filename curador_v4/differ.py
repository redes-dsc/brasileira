"""Calculadora de diff entre layouts — minimiza operações de escrita."""

from __future__ import annotations

from typing import Any


def calculate_diff(
    current: dict[str, Any] | None,
    proposed: dict[str, Any],
) -> dict[str, Any]:
    """Calcula diff mínimo entre layout atual e proposto.

    Decide entre PUT (substituição completa) e PATCH (alterações incrementais)
    baseado na proporção de mudanças.
    """

    # Sem layout atual → substituição completa
    if current is None or not current.get("blocks"):
        return {
            "method": "PUT",
            "full_layout": proposed,
            "changes": {
                "added": len(proposed.get("blocks", [])),
                "removed": 0,
                "updated": 0,
            },
        }

    current_blocks = {b["id"]: b for b in current.get("blocks", []) if "id" in b}
    proposed_blocks = {b["id"]: b for b in proposed.get("blocks", []) if "id" in b}

    # Blocos adicionados (no proposto, não no atual)
    added = [b for bid, b in proposed_blocks.items() if bid not in current_blocks]

    # Blocos removidos (no atual, não no proposto)
    removed = [bid for bid in current_blocks if bid not in proposed_blocks]

    # Blocos atualizados (existem em ambos, mas mudaram)
    updated = []
    for bid, proposed_block in proposed_blocks.items():
        if bid in current_blocks and current_blocks[bid] != proposed_block:
            updated.append(proposed_block)

    total_changes = len(added) + len(removed) + len(updated)
    total_blocks = max(len(current_blocks), len(proposed_blocks), 1)

    change_ratio = total_changes / total_blocks

    changes_summary = {
        "added": len(added),
        "removed": len(removed),
        "updated": len(updated),
    }

    # Se mais de 50% dos blocos mudaram, substituir tudo (mais eficiente)
    if change_ratio > 0.5 or total_changes == 0:
        return {
            "method": "PUT",
            "full_layout": proposed,
            "changes": changes_summary,
        }

    # Caso contrário, PATCH incremental
    return {
        "method": "PATCH",
        "added": added,
        "removed": removed,
        "updated": updated,
        "changes": changes_summary,
    }
