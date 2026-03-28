"""Compositor das zonas editoriais da homepage."""

from __future__ import annotations


class HomepageCompositor:
    """Monta as 6 zonas editoriais respeitando diversidade mínima."""

    def compor(self, ranked: list[dict], layout: str, breaking_post_id: int | None = None) -> dict:
        """Retorna payload estruturado para aplicação em ACF options."""

        used: set[int] = set()

        def take(where: list[dict], n: int, editoria: str | None = None) -> list[int]:
            out: list[int] = []
            for item in where:
                post_id = int(item["post_id"])
                if post_id in used:
                    continue
                if editoria is not None and item.get("editoria") != editoria:
                    continue
                used.add(post_id)
                out.append(post_id)
                if len(out) >= n:
                    break
            return out

        manchete = breaking_post_id if layout == "breaking" and breaking_post_id else (ranked[0]["post_id"] if ranked else None)
        if manchete is not None:
            used.add(int(manchete))

        destaques = take(ranked, 4)
        mais_lidas = [int(i["post_id"]) for i in ranked[:6]]
        opiniao = take(ranked, 3, editoria="opiniao_analise")
        regional = take(ranked, 3, editoria="regionais")

        por_editoria: dict[str, list[int]] = {}
        for item in ranked:
            editoria = str(item.get("editoria", "geral"))
            if editoria not in por_editoria:
                por_editoria[editoria] = []
            pid = int(item["post_id"])
            if pid not in por_editoria[editoria] and len(por_editoria[editoria]) < 3:
                por_editoria[editoria].append(pid)

        return {
            "layout": layout,
            "manchete_principal": manchete,
            "breaking_post_id": breaking_post_id if layout == "breaking" else None,
            "destaques": [{"post_id": pid, "tamanho": "normal", "label": "Destaque"} for pid in destaques],
            "editorias": por_editoria,
            "mais_lidas_posts": mais_lidas,
            "opiniao_posts": opiniao,
            "regional_posts": regional,
        }
