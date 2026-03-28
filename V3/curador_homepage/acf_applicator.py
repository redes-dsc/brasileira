"""Aplicador atômico de opções ACF para homepage."""

from __future__ import annotations

import json
import logging
from typing import Any

from curador_homepage.wp_fallback_applicator import WPFallbackApplicator

logger = logging.getLogger(__name__)


class ACFAplicator:
    """Aplica apenas diff de campos para evitar janela de homepage vazia."""

    OPTIONS_ENDPOINTS = (
        "/wp-json/acf/v3/options/homepage-settings",
        "/wp-json/acf/v3/options/options",
    )

    def __init__(self, fallback: WPFallbackApplicator | None = None) -> None:
        self._resolved_endpoint: str | None = None
        self._fallback = fallback

    async def _resolve_endpoint(self, wp_client) -> str:
        """Resolve endpoint ACF válido no ambiente e mantém em cache."""

        if self._resolved_endpoint is not None:
            return self._resolved_endpoint

        last_error: Exception | None = None
        for endpoint in self.OPTIONS_ENDPOINTS:
            try:
                await wp_client.get(endpoint)
                self._resolved_endpoint = endpoint
                return endpoint
            except RuntimeError as exc:
                last_error = exc
                if "404" not in str(exc):
                    raise
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError("Nenhum endpoint ACF configurado para options")

    async def aplicar_atomico(self, wp_client, payload: dict[str, Any]) -> dict[str, Any]:
        """Lê estado atual, calcula diff e aplica somente alterações."""

        try:
            endpoint = await self._resolve_endpoint(wp_client)
        except RuntimeError as exc:
            logger.warning("ACF indisponível: mantendo homepage atual sem alterações (%s)", exc)
            if self._fallback is not None:
                fallback_result = await self._fallback.aplicar_fallback(wp_client, payload)
                return {
                    "updated": fallback_result.get("updated", False),
                    "changed_fields": [],
                    "skipped": False,
                    "fallback_used": True,
                    "fallback_method": fallback_result.get("fallback_method"),
                    "fallback_details": fallback_result.get("details"),
                }
            return {"updated": False, "changed_fields": [], "skipped": True, "reason": "acf_unavailable", "fallback_used": False}
        current = await wp_client.get(endpoint)
        current_fields = current.get("acf", {}) if isinstance(current, dict) else {}

        acf_payload = {
            "layout_home": payload["layout"],
            "manchete_principal": payload["manchete_principal"],
            "breaking_post_id": payload.get("breaking_post_id"),
            "destaques": payload["destaques"],
            "mais_lidas_posts": json.dumps(payload["mais_lidas_posts"]),
            "curador_atualizado_em": payload["timestamp"],
            "curador_ciclo_id": payload["ciclo_id"],
        }

        for editoria, ids in payload.get("editorias", {}).items():
            acf_payload[f"editoria_{editoria}_posts"] = json.dumps(ids)

        diff = {k: v for k, v in acf_payload.items() if current_fields.get(k) != v}
        if not diff:
            return {"updated": False, "changed_fields": [], "fallback_used": False}

        try:
            updated = await wp_client.post(endpoint, json={"fields": diff})
            return {"updated": True, "changed_fields": list(diff.keys()), "raw": updated, "fallback_used": False}
        except Exception as exc:
            logger.error("Falha ao aplicar ACF: %s", exc)
            if self._fallback is not None:
                fallback_result = await self._fallback.aplicar_fallback(wp_client, payload)
                return {
                    "updated": fallback_result.get("updated", False),
                    "changed_fields": [],
                    "error": str(exc),
                    "fallback_used": True,
                    "fallback_method": fallback_result.get("fallback_method"),
                    "fallback_details": fallback_result.get("details"),
                }
            return {"updated": False, "changed_fields": [], "error": str(exc), "fallback_used": False}
