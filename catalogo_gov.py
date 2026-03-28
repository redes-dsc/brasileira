
# -*- coding: utf-8 -*-

"""

CATÁLOGO DE SCRAPERS - SETOR PÚBLICO

"""

from config_categorias import *



CATALOGO_GOV = {

    "gov_ministerios": [

        {"nome": "Min. da Agricultura", "url": "https://www.gov.br/agricultura/pt-br/assuntos/noticias", "cat_id": CAT_AGRO, "tipo_molde": "plone_classico"},

        {"nome": "Min. Cidades", "url": "https://www.gov.br/cidades/pt-br/assuntos/noticias-1", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "plone_classico"},

        {"nome": "Min. MCTI", "url": "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias", "cat_id": CAT_TECNOLOGIA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Comunicações", "url": "https://www.gov.br/mcom/pt-br/assuntos/noticias", "cat_id": CAT_TECNOLOGIA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Cultura", "url": "https://www.gov.br/cultura/pt-br/assuntos/noticias", "cat_id": CAT_CULTURA, "tipo_molde": "plone_classico"},

        {"nome": "Des. Agrário", "url": "https://www.gov.br/mda/pt-br/assuntos/noticias", "cat_id": CAT_AGRO, "tipo_molde": "plone_classico"},

        {"nome": "Min. Direitos Humanos", "url": "https://www.gov.br/mdh/pt-br/assuntos/noticias", "cat_id": CAT_SOCIEDADE, "tipo_molde": "plone_classico"},

        {"nome": "Min. Educação", "url": "https://www.gov.br/mec/pt-br/assuntos/noticias", "cat_id": CAT_EDUCACAO, "tipo_molde": "plone_classico"},

        {"nome": "Min. Microempresa", "url": "https://www.gov.br/memp/pt-br/assuntos/noticias", "cat_id": CAT_ECONOMIA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Fazenda", "url": "https://www.gov.br/fazenda/pt-br/assuntos/noticias", "cat_id": CAT_ECONOMIA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Gestão", "url": "https://www.gov.br/gestao/pt-br/assuntos/noticias", "cat_id": CAT_POLITICA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Igualdade Racial", "url": "https://www.gov.br/igualdaderacial/pt-br/assuntos/noticias", "cat_id": CAT_SOCIEDADE, "tipo_molde": "plone_classico"},

        {"nome": "Min. Justiça", "url": "https://www.gov.br/mj/pt-br/assuntos/noticias", "cat_id": CAT_JUSTICA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Minas e Energia", "url": "https://www.gov.br/mme/pt-br/assuntos/noticias", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Mulheres", "url": "https://www.gov.br/mulheres/pt-br/central-de-conteudos/noticias", "cat_id": CAT_SOCIEDADE, "tipo_molde": "plone_classico"},

        {"nome": "Min. Pesca", "url": "https://www.gov.br/mpa/pt-br/assuntos/noticias", "cat_id": CAT_AGRO, "tipo_molde": "plone_classico"},

        {"nome": "Min. Planejamento", "url": "https://www.gov.br/planejamento/pt-br/assuntos/noticias", "cat_id": CAT_ECONOMIA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Portos", "url": "https://www.gov.br/portos-e-aeroportos/pt-br/assuntos/noticias", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Previdência", "url": "https://www.gov.br/previdencia/pt-br/assuntos/noticias", "cat_id": CAT_SOCIEDADE, "tipo_molde": "plone_classico"},

        {"nome": "Itamaraty", "url": "https://www.gov.br/mre/pt-br/canais_atendimento/imprensa/notas-a-imprensa", "cat_id": CAT_INTERNACIONAL, "tipo_molde": "plone_classico"},

        {"nome": "Min. Trabalho", "url": "https://www.gov.br/trabalho-e-emprego/pt-br/noticias-e-conteudo", "cat_id": CAT_ECONOMIA, "tipo_molde": "plone_classico"},

        {"nome": "Min. Meio Ambiente", "url": "https://www.gov.br/mma/pt-br/assuntos/noticias", "cat_id": CAT_MEIO_AMBIENTE, "tipo_molde": "plone_tiles"},

        {"nome": "Min. Transportes", "url": "https://www.gov.br/transportes/pt-br/assuntos/noticias", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "plone_tiles"},

        {"nome": "Min. Turismo", "url": "https://www.gov.br/turismo/pt-br/assuntos/noticias", "cat_id": CAT_TURISMO, "tipo_molde": "plone_tiles"},

        {"nome": "Planalto", "url": "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias", "cat_id": CAT_POLITICA, "tipo_molde": "plone_classico"},

        {"nome": "MDS (Social)", "url": "https://www.gov.br/mds/pt-br/assuntos/noticias", "cat_id": CAT_SOCIEDADE, "tipo_molde": "inteligente"},

        {"nome": "Min. Esportes", "url": "https://www.gov.br/esportes/pt-br/assuntos/noticias", "cat_id": CAT_ESPORTES, "tipo_molde": "inteligente"},

        {"nome": "Min. Povos Indígenas", "url": "https://www.gov.br/povosindigenas/pt-br/assuntos/noticias", "cat_id": CAT_SOCIEDADE, "tipo_molde": "inteligente"}

    ],

    "reguladores": [

        {"nome": "Anatel", "url": "https://www.gov.br/anatel/pt-br/assuntos/noticias", "cat_id": CAT_TECNOLOGIA, "tipo_molde": "plone_classico"},

        {"nome": "ANP", "url": "https://www.gov.br/anp/pt-br/assuntos/noticias", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "plone_classico"},

        {"nome": "ANEEL", "url": "https://www.gov.br/aneel/pt-br/assuntos/noticias", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "plone_classico"},

        {"nome": "ANTT", "url": "https://www.gov.br/antt/pt-br/assuntos/noticias", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "plone_classico"},

        {"nome": "ANTAQ", "url": "https://www.gov.br/antaq/pt-br/assuntos/noticias", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "plone_classico"},

        {"nome": "ANA", "url": "https://www.gov.br/ana/pt-br/assuntos/noticias", "cat_id": CAT_MEIO_AMBIENTE, "tipo_molde": "plone_classico"}

    ],

    "estados": [

        {"nome": "Agência Brasília", "url": "https://www.agenciabrasilia.df.gov.br/", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov Bahia", "url": "https://www.ba.gov.br/", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov MS", "url": "https://www.ms.gov.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov MT", "url": "https://portal.mt.gov.br/", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Agência Pará", "url": "https://agenciapara.com.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov Paraíba", "url": "https://paraiba.pb.gov.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov Pernambuco", "url": "https://www.pe.gov.br/app/catalog/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Agência Paraná", "url": "https://www.parana.pr.gov.br/aen/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov RJ", "url": "https://www.rj.gov.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Agência RS", "url": "https://www.estado.rs.gov.br/agencia-de-noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov SC", "url": "https://estado.sc.gov.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov Sergipe", "url": "https://www.se.gov.br/", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov SP", "url": "https://www.sp.gov.br/sp/canais-comunicacao/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov Tocantins", "url": "https://www.to.gov.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov Alagoas", "url": "https://alagoas.al.gov.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov Amazonas", "url": "https://www.amazonas.am.gov.br/", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Portal Amapá", "url": "https://www.portal.ap.gov.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov Maranhão", "url": "https://segov.ma.gov.br/noticias", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"},

        {"nome": "Gov RN", "url": "https://www.rn.gov.br/", "cat_id": CAT_ESTADOS, "tipo_molde": "inteligente"}

    ],

    "judiciario_conselhos": [

        {"nome": "STF", "url": "https://noticias.stf.jus.br/", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "STJ", "url": "https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias.aspx", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "TST", "url": "https://www.tst.jus.br/noticias", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "CSJT", "url": "https://www.csjt.jus.br/web/csjt/noticias", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "CJF", "url": "https://www.cjf.jus.br/", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "TCU", "url": "https://portal.tcu.gov.br/imprensa/noticias", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "MPT", "url": "https://mpt.mp.br/pgt/noticias", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "TRF1", "url": "https://portal.trf1.jus.br/portaltrf1/", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "TRF2", "url": "https://www.trf2.jus.br/jf2/noticia-jf2/", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "TRF3", "url": "https://www.trf3.jus.br/", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "TRF5", "url": "https://www.trf5.jus.br/index.php/noticias", "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"},

        {"nome": "CONFEA", "url": "https://www.confea.org.br/noticias", "cat_id": CAT_SOCIEDADE, "tipo_molde": "inteligente"},

        {"nome": "Conselho Farmácia", "url": "https://site.cff.org.br/noticias", "cat_id": CAT_SAUDE, "tipo_molde": "inteligente"},

        {"nome": "CFESS", "url": "https://www.cfess.org.br/noticia", "cat_id": CAT_SOCIEDADE, "tipo_molde": "inteligente"},

        {"nome": "COFFITO", "url": "https://www.coffito.gov.br/", "cat_id": CAT_SAUDE, "tipo_molde": "inteligente"},

        {"nome": "COFECI", "url": "https://www.cofeci.gov.br/portal-de-noticias", "cat_id": CAT_ECONOMIA, "tipo_molde": "inteligente"},

        {"nome": "Conselho Estatística", "url": "https://www.confe.org.br/", "cat_id": CAT_EDUCACAO, "tipo_molde": "inteligente"},

        {"nome": "CAU/BR", "url": "https://caubr.gov.br/", "cat_id": CAT_INFRAESTRUTURA, "tipo_molde": "inteligente"},

        {"nome": "COFECON", "url": "https://cofecon.org.br/", "cat_id": CAT_ECONOMIA, "tipo_molde": "inteligente"},

        {"nome": "CONFEF", "url": "https://confef.org.br/", "cat_id": CAT_EDUCACAO, "tipo_molde": "inteligente"}

    ]

}



# Gerador dinâmico TRTs
_trts = []
for i in range(1, 24): # O TRT24 nao existe mais, ate 23
    url_trt = f"https://www.trt{i}.jus.br/noticias"
    if i == 2: url_trt = "https://ww2.trt2.jus.br/noticias/noticias"
    if i == 3: url_trt = "https://portal.trt3.jus.br/internet/conheca-o-trt/comunicacao/noticias-juridicas"
    if i == 7: url_trt = "https://www.trt7.jus.br/index.php/noticias/todas-as-noticias"
    if i == 9: url_trt = "https://www.trt9.jus.br/portal/noticias.xhtml"
    if i == 14: url_trt = "https://portal.trt14.jus.br/portal/"
    if i == 22: url_trt = "https://www.trt22.jus.br/portal/noticias"
    if i == 23: url_trt = "https://portal.trt23.jus.br/portal/noticias"
    
    _trts.append({
        "nome": f"TRT{i}", "url": url_trt, "cat_id": CAT_JUSTICA, "tipo_molde": "inteligente"
    })

# Injetar evitando re-append em recarregamentos dinâmicos
CATALOGO_GOV["judiciario_conselhos"] = [t for t in CATALOGO_GOV["judiciario_conselhos"] if not t["nome"].startswith("TRT")] + _trts
