"""Catálogo de portais concorrentes monitorados."""

from pydantic import BaseModel, ConfigDict


class PortalConfig(BaseModel):
    """Config de portal com seletores de capa para scanner browser-first."""

    model_config = ConfigDict(strict=True)

    nome: str
    url: str
    requires_browser: bool = True
    selectors: list[str]


PORTAIS_PADRAO = [
    PortalConfig(
        nome="g1",
        url="https://g1.globo.com",
        selectors=["a.feed-post-link", "a.bstn-hl-titlelnk", "h2 a"],
    ),
    PortalConfig(
        nome="uol",
        url="https://www.uol.com.br",
        selectors=["a.headlineMain__link", "h3 a", "a[href*='/noticias/']"],
    ),
    PortalConfig(
        nome="folha",
        url="https://www.folha.uol.com.br",
        selectors=["h2.c-headline__title a", "a.c-main-headline__url", "h2 a"],
    ),
    PortalConfig(
        nome="estadao",
        url="https://www.estadao.com.br",
        selectors=["h3.title a", "a.link-title", "h2 a"],
    ),
    PortalConfig(
        nome="cnn_brasil",
        url="https://www.cnnbrasil.com.br",
        selectors=["h3.home__title a", "a.block__news__title", "h2 a"],
    ),
    PortalConfig(
        nome="r7",
        url="https://www.r7.com",
        selectors=["h3 a", "a.news__title", "h2 a"],
    ),
    PortalConfig(
        nome="terra",
        url="https://www.terra.com.br",
        selectors=["h3 a", "a.card-news__text--title", "h2 a"],
    ),
    PortalConfig(
        nome="metropoles",
        url="https://www.metropoles.com",
        selectors=["h2.CardTitle a", "a.m-title", "h3 a"],
    ),
]
