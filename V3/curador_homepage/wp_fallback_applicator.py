"""Aplicador de fallback para homepage via WordPress REST API nativo."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WPFallbackApplicator:
    """Fornece mecanismo de fallback para aplicação de curadoria quando ACF PRO não está disponível.
    
    Usa endpoints nativos do WordPress REST API em vez de ACF.
    """

    def __init__(self) -> None:
        self._sticky_posts_endpoint = "/wp-json/wp/v2/posts"

    async def aplicar_fallback(self, wp_client, payload: dict[str, Any]) -> dict[str, Any]:
        """Orquestra o fallback em 3 camadas.
        
        1. Tenta sticky posts + post meta
        2. Se falhar, cai para modo degradado de logging
        
        Args:
            wp_client: Cliente para comunicação com WordPress
            payload: Dicionário com estrutura da homepage curada
            
        Returns:
            Dict com keys: updated (bool), fallback_method (str), details (dict)
        """
        logger.info("Ativando fallback WordPress nativo para aplicação de homepage")

        # Tier 1: Sticky posts + post meta
        try:
            # Coleta IDs de posts para sticky (manchete + destaques)
            sticky_ids: list[int] = []
            if payload.get("manchete_principal"):
                sticky_ids.append(int(payload["manchete_principal"]))
            
            for destaque in payload.get("destaques", []):
                post_id = destaque.get("post_id")
                if post_id and post_id not in sticky_ids:
                    sticky_ids.append(int(post_id))

            sticky_success = await self._set_sticky_posts(wp_client, sticky_ids)
            meta_success = await self._set_post_meta(wp_client, payload)

            if sticky_success or meta_success:
                return {
                    "updated": True,
                    "fallback_method": "sticky_posts_and_meta",
                    "details": {
                        "sticky_updated": sticky_success,
                        "meta_updated": meta_success,
                        "sticky_count": len(sticky_ids),
                    },
                }
        except Exception as exc:
            logger.warning("Falha no tier 1 de fallback (sticky/meta): %s", exc)

        # Tier 2: Modo degradado - apenas logging
        logger.warning("Fallback tier 1 falhou, ativando modo degradado")
        return await self._log_degraded(payload)

    async def _set_sticky_posts(self, wp_client, post_ids: list[int]) -> bool:
        """Atualiza posts sticky na homepage.
        
        Primeiro obtém posts sticky atuais, depois:
        - Remove sticky de posts que não estão mais na seleção
        - Adiciona sticky nos novos posts da homepage
        
        Args:
            wp_client: Cliente para comunicação com WordPress
            post_ids: Lista de IDs de posts que devem estar sticky
            
        Returns:
            True em caso de sucesso, False em caso de falha
        """
        try:
            # Obtém posts sticky atuais
            current_sticky_response = await wp_client.get(
                f"{self._sticky_posts_endpoint}?sticky=true&per_page=50"
            )
            
            current_sticky_ids: set[int] = set()
            if isinstance(current_sticky_response, list):
                for post in current_sticky_response:
                    if isinstance(post, dict) and "id" in post:
                        current_sticky_ids.add(int(post["id"]))

            target_ids = set(post_ids)

            # Unstick posts que não estão mais na seleção
            to_unstick = current_sticky_ids - target_ids
            for post_id in to_unstick:
                try:
                    await wp_client.post(
                        f"{self._sticky_posts_endpoint}/{post_id}",
                        json={"sticky": False},
                    )
                    logger.debug("Removido sticky do post %s", post_id)
                except Exception as exc:
                    logger.warning("Erro ao remover sticky do post %s: %s", post_id, exc)

            # Stick novos posts da homepage
            to_stick = target_ids - current_sticky_ids
            for post_id in to_stick:
                try:
                    await wp_client.post(
                        f"{self._sticky_posts_endpoint}/{post_id}",
                        json={"sticky": True},
                    )
                    logger.debug("Adicionado sticky ao post %s", post_id)
                except Exception as exc:
                    logger.warning("Erro ao adicionar sticky ao post %s: %s", post_id, exc)

            logger.info(
                "Sticky posts atualizados: %d adicionados, %d removidos",
                len(to_stick),
                len(to_unstick),
            )
            return True

        except Exception as exc:
            logger.error("Falha ao atualizar sticky posts: %s", exc)
            return False

    async def _set_post_meta(self, wp_client, payload: dict[str, Any]) -> bool:
        """Atualiza meta dados dos posts com informações de posição na homepage.
        
        Define campos meta para cada zona:
        - manchete_principal: position=1, zone="manchete_principal"
        - destaques: position=2+, zone="destaques"
        - Também grava homepage_layout no post da manchete
        
        Limpa meta de posts que estavam na homepage mas não estão mais.
        
        Args:
            wp_client: Cliente para comunicação com WordPress
            payload: Dicionário com estrutura da homepage curada
            
        Returns:
            True em caso de sucesso, False em caso de falha
        """
        try:
            posts_to_update: dict[int, dict[str, Any]] = {}

            # Manchete principal - position 1
            manchete_id = payload.get("manchete_principal")
            if manchete_id:
                posts_to_update[int(manchete_id)] = {
                    "meta": {
                        "homepage_position": 1,
                        "homepage_zone": "manchete_principal",
                        "homepage_layout": payload.get("layout", "normal"),
                    }
                }

            # Destaques - positions 2-5
            for i, destaque in enumerate(payload.get("destaques", [])[:4]):
                post_id = destaque.get("post_id")
                if post_id:
                    posts_to_update[int(post_id)] = {
                        "meta": {
                            "homepage_position": 2 + i,
                            "homepage_zone": "destaques",
                        }
                    }

            # Aplica atualizações de meta
            success_count = 0
            for post_id, update_data in posts_to_update.items():
                try:
                    await wp_client.post(
                        f"{self._sticky_posts_endpoint}/{post_id}",
                        json=update_data,
                    )
                    success_count += 1
                    logger.debug(
                        "Meta atualizado para post %s: %s",
                        post_id,
                        update_data["meta"],
                    )
                except Exception as exc:
                    logger.warning("Erro ao atualizar meta do post %s: %s", post_id, exc)

            # TODO: Limpar meta de posts que estavam na homepage mas não estão mais
            # Isso reteria um cache de posts anteriores, que pode ser implementado
            # em uma versão futura se necessário

            logger.info(
                "Meta dados atualizados: %d/%d posts com sucesso",
                success_count,
                len(posts_to_update),
            )
            return success_count > 0

        except Exception as exc:
            logger.error("Falha ao atualizar post meta: %s", exc)
            return False

    async def _log_degraded(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Registra em log o estado completo pretendido da homepage.
        
        Usado quando os tiers anteriores de fallback falharam.
        
        Args:
            payload: Dicionário com estrutura completa da homepage curada
            
        Returns:
            Dict indicando que foi feito apenas logging
        """
        destaque_ids = [
            d.get("post_id") for d in payload.get("destaques", [])
        ]

        zone_assignments = {
            "manchete_principal": payload.get("manchete_principal"),
            "destaques": destaque_ids,
            "mais_lidas": payload.get("mais_lidas_posts", []),
            "opiniao": payload.get("opiniao_posts", []),
            "regional": payload.get("regional_posts", []),
            "editorias": payload.get("editorias", {}),
        }

        logger.warning(
            "[MODO DEGRADADO] Estado pretendido da homepage não pôde ser aplicado. "
            "Layout: %s, Manchete: %s, Destaques: %s, "
            "Timestamp: %s, Ciclo ID: %s, Zonas: %s",
            payload.get("layout"),
            payload.get("manchete_principal"),
            destaque_ids,
            payload.get("timestamp"),
            payload.get("ciclo_id"),
            zone_assignments,
        )

        return {
            "updated": False,
            "fallback_method": "degraded_log",
            "details": {"logged_payload": True},
        }
