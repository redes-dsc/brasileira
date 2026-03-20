
# -*- coding: utf-8 -*-

"""

MEGA CATÁLOGO MESTRE DE SCRAPERS - Brasileira.news

Une todos os sub-catálogos modulares (Gov, Mídia e Nicho).

"""

from catalogo_gov import CATALOGO_GOV

from catalogo_midia import CATALOGO_MIDIA

from catalogo_nicho import CATALOGO_NICHO



# Aglutinando todos os dicionários num único objeto para o Motor ler

CATALOGO_SCRAPERS = {**CATALOGO_GOV, **CATALOGO_MIDIA, **CATALOGO_NICHO}

