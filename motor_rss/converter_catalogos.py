
# -*- coding: utf-8 -*-

"""

Converte os catálogos existentes para feeds.json do motor_rss_v2

"""

import json

import sys

sys.path.insert(0, '/home/bitnami')



# Mapeamento de cat_id para tema

GOV_CATS = [

    'CAT_POLITICA','CAT_JUSTICA','CAT_EDUCACAO','CAT_SAUDE',

    'CAT_SOCIEDADE','CAT_MEIOAMBIENTE','CAT_AGRO','CAT_INFRAESTRUTURA',

    'CAT_TURISMO','CAT_ESTADOS','CAT_ECONOMIA','CAT_INTERNACIONAL',

    'CAT_TECNOLOGIA','CAT_CULTURA','CAT_ESPORTES','CAT_ENTRETENIMENTO',

]



def tema_por_grupo(grupo, nome_catalogo):

    """Define tema baseado no catálogo de origem."""

    if nome_catalogo in ('catalogo_gov', 'catalogo_fontes'):

        gov_grupos = [

            'agencia_brasil','govcentral','ministerios_autarquias',

            'legislativo','judiciario_controle','estados_br','radioagencia'

        ]

        if grupo in gov_grupos:

            return 'governo'

    return 'imprensa'



feeds = []

vistos = set()



def adicionar(itens, grupo, catalogo_nome):

    for item in itens:

        url = item.get('url','').strip()

        if not url or url in vistos:

            continue

        # Só adiciona se parece RSS (tem feed.xml, rss, RSS, .xml, /feed)

        url_lower = url.lower()

        is_rss = any(p in url_lower for p in [

            'feed.xml','rss','feed/','feeds/','.xml','/rss',

            'rss2','atom','syndication'

        ])

        if not is_rss:

            continue

        vistos.add(url)

        feeds.append({

            'nome': item.get('nome', url),

            'url': url,

            'tema': tema_por_grupo(grupo, catalogo_nome),

            'ativo': True

        })



# Importar catalogo_fontes

try:

    from catalogo_fontes import CATALOGO_FONTES

    for grupo, itens in CATALOGO_FONTES.items():

        adicionar(itens, grupo, 'catalogo_fontes')

    print(f'catalogo_fontes: OK')

except Exception as e:

    print(f'catalogo_fontes: ERRO — {e}')



# Importar catalogo_gov

try:

    from catalogo_gov import CATALOGO_GOV

    for grupo, itens in CATALOGO_GOV.items():

        adicionar(itens, grupo, 'catalogo_gov')

    print(f'catalogo_gov: OK')

except Exception as e:

    print(f'catalogo_gov: ERRO — {e}')



# Importar catalogo_midia

try:

    from catalogo_midia import CATALOGO_MIDIA

    for grupo, itens in CATALOGO_MIDIA.items():

        adicionar(itens, grupo, 'catalogo_midia')

    print(f'catalogo_midia: OK')

except Exception as e:

    print(f'catalogo_midia: ERRO — {e}')



# Salvar feeds.json

output = {'feeds': feeds}

with open('/home/bitnami/motor_rss/feeds.json', 'w', encoding='utf-8') as f:

    json.dump(output, f, ensure_ascii=False, indent=2)



print(f'\nTotal de feeds RSS extraidos: {len(feeds)}')

print(f'feeds.json salvo em /home/bitnami/motor_rss/feeds.json')

