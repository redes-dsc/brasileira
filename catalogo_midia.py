
# -*- coding: utf-8 -*-

"""

CATÁLOGO DE SCRAPERS - MÍDIA GERAL

"""

from config_categorias import *



CATALOGO_MIDIA = {

    "grandes_portais": [

        {"nome": "Estadão", "url": "https://www.estadao.com.br/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "R7 Notícias", "url": "https://noticias.r7.com/", "cat_id": CAT_POLITICA, "tipo_molde": "r7"},

        {"nome": "SBT News", "url": "https://sbtnews.sbt.com.br/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "Band Notícias", "url": "https://www.band.uol.com.br/noticias", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "Gazeta do Povo", "url": "https://www.gazetadopovo.com.br/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "Zero Hora", "url": "https://gauchazh.clicrbs.com.br/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "Terra", "url": "https://www.terra.com.br/noticias/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "Bloomberg Línea", "url": "https://www.bloomberglinea.com.br/", "cat_id": CAT_ECONOMIA, "tipo_molde": "inteligente"},

        {"nome": "Brasil 247", "url": "https://www.brasil247.com/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "Congresso em Foco", "url": "https://congressoemfoco.uol.com.br/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "Revista Piauí", "url": "https://piaui.folha.uol.com.br/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"},

        {"nome": "Migalhas", "url": "https://www.migalhas.com.br/", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "Agência Câmara", "url": "https://www.camara.leg.br/noticias/", "cat_id": CAT_POLITICA, "tipo_molde": "inteligente"}

    ],

    "entretenimento_fofoca": [

        {"nome": "Quem", "url": "https://quem.globo.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Caras", "url": "https://caras.com.br/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Purepeople", "url": "https://www.purepeople.com.br/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Notícias da TV", "url": "https://noticiasdatv.uol.com.br/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Ofuxico", "url": "https://www.ofuxico.com.br/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Observatório Famosos", "url": "https://observatoriodosfamosos.uol.com.br/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Na Telinha", "url": "https://natelinha.uol.com.br/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "R7 Entretenimento", "url": "https://entretenimento.r7.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Vogue Brasil", "url": "https://vogue.globo.com/", "cat_id": CAT_CULTURA, "tipo_molde": "inteligente"},

        {"nome": "GQ Brasil", "url": "https://gq.globo.com/", "cat_id": CAT_CULTURA, "tipo_molde": "inteligente"},

        {"nome": "Marie Claire", "url": "https://marieclaire.globo.com/", "cat_id": CAT_CULTURA, "tipo_molde": "inteligente"},

        {"nome": "Glamour", "url": "https://glamour.globo.com/", "cat_id": CAT_CULTURA, "tipo_molde": "inteligente"},

        {"nome": "Hypeness", "url": "https://www.hypeness.com.br/", "cat_id": CAT_SOCIEDADE, "tipo_molde": "inteligente"},

        {"nome": "Women's Health", "url": "https://womenshealthbrasil.com.br/", "cat_id": CAT_SAUDE, "tipo_molde": "inteligente"},

        {"nome": "Men's Health", "url": "https://menshealth.com.br/", "cat_id": CAT_SAUDE, "tipo_molde": "inteligente"},

        {"nome": "Omelete", "url": "https://www.omelete.com.br/api/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "omelete"},

        {"nome": "Jovem Nerd", "url": "https://jovemnerd.com.br/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "AdoroCinema", "url": "https://www.adorocinema.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "IGN Brasil", "url": "https://br.ign.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Popline", "url": "https://popline.com.br/", "cat_id": CAT_CULTURA, "tipo_molde": "inteligente"},

        {"nome": "Billboard Brasil", "url": "https://www.billboard.com.br/", "cat_id": CAT_CULTURA, "tipo_molde": "inteligente"},

        {"nome": "Splash UOL", "url": "https://www.uol.com.br/splash/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "People Magazine", "url": "https://people.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Entertainment Weekly", "url": "https://ew.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Vanity Fair", "url": "https://www.vanityfair.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Daily Mail", "url": "https://www.dailymail.co.uk/tvshowbiz/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Just Jared", "url": "https://www.justjared.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Hola", "url": "https://www.hola.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Screen Rant", "url": "https://screenrant.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"},

        {"nome": "Collider", "url": "https://collider.com/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "inteligente"}

    ],

    "internacional": [

        {"nome": "ANSA Brasil", "url": "https://ansabrasil.com.br/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "Xinhua PT", "url": "https://portuguese.news.cn/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "VOA Português", "url": "https://www.voaportugues.com/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "NHK World PT", "url": "https://www3.nhk.or.jp/nhkworld/pt/news/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "Lusa", "url": "https://www.lusa.pt/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "ANGOP", "url": "https://www.angop.ao/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "Inforpress", "url": "https://inforpress.cv/pt", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "MercoPress", "url": "https://en.mercopress.com/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "TeleSUR", "url": "https://www.telesurtv.net/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "EFE", "url": "https://efe.com/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "Telam", "url": "https://www.telam.com.ar/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "Pagina 12", "url": "https://www.pagina12.com.ar/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "SwissInfo", "url": "https://www.swissinfo.ch/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "MAP Marrocos", "url": "https://www.map.ma/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"},

        {"nome": "Reuters", "url": "https://www.reuters.com/", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "inteligente"}

    ]

}

