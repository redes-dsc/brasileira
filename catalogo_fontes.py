# -*- coding: utf-8 -*-

from config_categorias import *



CATALOGO_FONTES = {

    # ==========================================

    # BLOCO 1: FONTES DO GOVERNO E ESTADO

    # ==========================================

    "agencia_brasil": [

        {"nome": "Agência Brasil (Últimas)", "url": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml", "cat_id": CAT_POLITICA},

        {"nome": "Agência Brasil (Economia)", "url": "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml", "cat_id": CAT_ECONOMIA},

        {"nome": "Agência Brasil (Política)", "url": "https://agenciabrasil.ebc.com.br/rss/politica/feed.xml", "cat_id": CAT_POLITICA},

        {"nome": "Agência Brasil (Internacional)", "url": "https://agenciabrasil.ebc.com.br/rss/internacional/feed.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Agência Brasil (Justiça)", "url": "https://agenciabrasil.ebc.com.br/rss/justica/feed.xml", "cat_id": CAT_JUSTICA},

        {"nome": "Agência Brasil (Educação)", "url": "https://agenciabrasil.ebc.com.br/rss/educacao/feed.xml", "cat_id": CAT_EDUCACAO},

        {"nome": "Agência Brasil (Saúde)", "url": "https://agenciabrasil.ebc.com.br/rss/saude/feed.xml", "cat_id": CAT_SAUDE},

        {"nome": "Agência Brasil (Dir Humanos)", "url": "https://agenciabrasil.ebc.com.br/rss/direitos-humanos/feed.xml", "cat_id": CAT_SOCIEDADE},

        {"nome": "Agência Brasil (Esportes)", "url": "https://agenciabrasil.ebc.com.br/rss/esportes/feed.xml", "cat_id": CAT_ESPORTES},

        {"nome": "Agência Brasil (Geral)", "url": "https://agenciabrasil.ebc.com.br/rss/geral/feed.xml", "cat_id": CAT_SOCIEDADE},

        {"nome": "Radioagência (Últimas)", "url": "https://agenciabrasil.ebc.com.br/radioagencia-nacional/rss/ultimasnoticias/feed.xml", "cat_id": CAT_POLITICA},

        {"nome": "Radioagência (Política)", "url": "https://agenciabrasil.ebc.com.br/radioagencia-nacional/rss/politica/feed.xml", "cat_id": CAT_POLITICA},

        {"nome": "Radioagência (Intl)", "url": "https://agenciabrasil.ebc.com.br/radioagencia-nacional/rss/internacional/feed.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Radioagência (Justiça)", "url": "https://agenciabrasil.ebc.com.br/radioagencia-nacional/rss/justica/feed.xml", "cat_id": CAT_JUSTICA},

        {"nome": "Radioagência (Cultura)", "url": "https://agenciabrasil.ebc.com.br/radioagencia-nacional/rss/cultura/feed.xml", "cat_id": CAT_CULTURA}

    ],

    "gov_central": [

        {"nome": "Gov.br (Todas)", "url": "https://www.gov.br/pt-br/noticias/RSS", "cat_id": CAT_POLITICA},

        {"nome": "Gov.br (Agro)", "url": "https://www.gov.br/pt-br/noticias/agricultura-e-pecuaria/RSS", "cat_id": CAT_AGRO},

        {"nome": "Gov.br (Assistência)", "url": "https://www.gov.br/pt-br/noticias/assistencia-social/RSS", "cat_id": CAT_SOCIEDADE},

        {"nome": "Gov.br (Ciência/Tech)", "url": "https://www.gov.br/pt-br/noticias/ciencia-e-tecnologia/RSS", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Gov.br (Comunicação)", "url": "https://www.gov.br/pt-br/noticias/comunicacao/RSS", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Gov.br (Defesa/Segurança)", "url": "https://www.gov.br/pt-br/noticias/defesa-e-seguranca/RSS", "cat_id": CAT_JUSTICA},

        {"nome": "Gov.br (Educação/Pesquisa)", "url": "https://www.gov.br/pt-br/noticias/educacao-e-pesquisa/RSS", "cat_id": CAT_EDUCACAO},

        {"nome": "Gov.br (Finanças/Gestão)", "url": "https://www.gov.br/pt-br/noticias/financas-impostos-e-gestao-publica/RSS", "cat_id": CAT_ECONOMIA},

        {"nome": "Gov.br (Justiça/Segurança)", "url": "https://www.gov.br/pt-br/noticias/justica-e-seguranca/RSS", "cat_id": CAT_JUSTICA},

        {"nome": "Gov.br (Meio Ambiente)", "url": "https://www.gov.br/pt-br/noticias/meio-ambiente-e-clima/RSS", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Gov.br (Serviços Cidadão)", "url": "https://www.gov.br/pt-br/noticias/servicos-para-o-cidadao/RSS", "cat_id": CAT_SOCIEDADE},

        {"nome": "Gov.br (Trabalho/Prev)", "url": "https://www.gov.br/pt-br/noticias/trabalho-e-previdencia/RSS", "cat_id": CAT_SOCIEDADE},

        {"nome": "Gov.br (Transportes)", "url": "https://www.gov.br/pt-br/noticias/transito-e-transportes/RSS", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Gov.br (Turismo)", "url": "https://www.gov.br/pt-br/noticias/viagens-e-turismo/RSS", "cat_id": CAT_TURISMO}

    ],

    "ministerios_autarquias": [

        {"nome": "Min. da Saúde", "url": "https://www.gov.br/saude/pt-br/assuntos/noticias/RSS", "cat_id": CAT_SAUDE},

        {"nome": "Min. da Defesa", "url": "https://www.gov.br/defesa/pt-br/centrais-de-conteudo/noticias/RSS", "cat_id": CAT_POLITICA},

        {"nome": "IBAMA", "url": "https://www.gov.br/ibama/pt-br/assuntos/noticias/RSS", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Receita Federal", "url": "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/RSS", "cat_id": CAT_ECONOMIA},

        {"nome": "ANS", "url": "https://www.gov.br/ans/pt-br/assuntos/noticias/RSS", "cat_id": CAT_SAUDE},

        {"nome": "CAPES", "url": "https://www.gov.br/capes/pt-br/assuntos/noticias/RSS", "cat_id": CAT_EDUCACAO},

        {"nome": "IPEA", "url": "https://www.ipea.gov.br/portal/index.php?option=com_content&view=featured&Itemid=68&format=feed&type=rss", "cat_id": CAT_ECONOMIA},

        {"nome": "Polícia Federal", "url": "https://www.gov.br/pf/pt-br/assuntos/noticias/RSS", "cat_id": CAT_JUSTICA},

        {"nome": "PRF", "url": "https://www.gov.br/prf/pt-br/assuntos/noticias/RSS", "cat_id": CAT_JUSTICA},

        {"nome": "CGU", "url": "https://www.gov.br/cgu/pt-br/assuntos/noticias/RSS", "cat_id": CAT_POLITICA},

        {"nome": "AGU", "url": "https://www.gov.br/agu/pt-br/comunicacao/noticias/RSS", "cat_id": CAT_JUSTICA}

    ],

    "legislativo": [

        {"nome": "Câmara (Últimas)", "url": "https://www.camara.leg.br/noticias/rss/ultimas-noticias", "cat_id": CAT_POLITICA},

        {"nome": "Câmara (Adm Pública)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/ADMINISTRACAO-PUBLICA", "cat_id": CAT_POLITICA},

        {"nome": "Câmara (Agropecuária)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/AGROPECUARIA", "cat_id": CAT_AGRO},

        {"nome": "Câmara (Assist. Social)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/ASSISTENCIA-SOCIAL", "cat_id": CAT_SOCIEDADE},

        {"nome": "Câmara (Cidades)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/CIDADES", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Câmara (Ciência/Tech)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/CIENCIA-E-TECNOLOGIA", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Câmara (Comunicação)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/COMUNICACAO", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Câmara (Consumidor)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/CONSUMIDOR", "cat_id": CAT_ECONOMIA},

        {"nome": "Câmara (Direito/Justiça)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/DIREITO-E-JUSTICA", "cat_id": CAT_JUSTICA},

        {"nome": "Câmara (Dir Humanos)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/DIREITOS-HUMANOS", "cat_id": CAT_SOCIEDADE},

        {"nome": "Câmara (Economia)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/ECONOMIA", "cat_id": CAT_ECONOMIA},

        {"nome": "Câmara (Educação)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/EDUCACAO-E-CULTURA", "cat_id": CAT_EDUCACAO},

        {"nome": "Câmara (Eleições)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/ELEICOES", "cat_id": CAT_POLITICA},

        {"nome": "Câmara (Esportes)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/ESPORTES", "cat_id": CAT_ESPORTES},

        {"nome": "Câmara (Indústria)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/INDUSTRIA-E-COMERCIO", "cat_id": CAT_ECONOMIA},

        {"nome": "Câmara (Meio Ambiente)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/MEIO-AMBIENTE", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Câmara (Política)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/POLITICA", "cat_id": CAT_POLITICA},

        {"nome": "Câmara (Relações Ext)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/RELACOES-EXTERIORES", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Câmara (Saúde)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/SAUDE", "cat_id": CAT_SAUDE},

        {"nome": "Câmara (Segurança)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/SEGURANCA", "cat_id": CAT_JUSTICA},

        {"nome": "Câmara (Trabalho)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/TRABALHO-E-PREVIDENCIA", "cat_id": CAT_SOCIEDADE},

        {"nome": "Câmara (Transporte)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/TRANSPORTE-E-TRANSITO", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Câmara (Turismo)", "url": "https://www.camara.leg.br/noticias/rss/dinamico/TURISMO", "cat_id": CAT_TURISMO},

        {"nome": "Senado Federal", "url": "https://www12.senado.leg.br/noticias/RSS", "cat_id": CAT_POLITICA},

        {"nome": "Senado (Matérias)", "url": "https://www12.senado.leg.br/noticias/materias/RSS", "cat_id": CAT_POLITICA},

        {"nome": "Senado (Blog)", "url": "https://www12.senado.leg.br/blog/blog-do-senado-rss-feed", "cat_id": CAT_POLITICA}

    ],

    "judiciario_controle": [

        {"nome": "STJ Pesquisa Pronta", "url": "https://scon.stj.jus.br/SCON/PesquisaProntaFeed", "cat_id": CAT_JUSTICA},

        {"nome": "STJ Jurisprudência", "url": "https://scon.stj.jus.br/SCON/JurisprudenciaEmTesesFeed", "cat_id": CAT_JUSTICA},

        {"nome": "STJ Informativo", "url": "https://processo.stj.jus.br/jurisprudencia/externo/InformativoFeed", "cat_id": CAT_JUSTICA},

        {"nome": "TRF4", "url": "https://www.trf4.jus.br/trf4/noticias.xml", "cat_id": CAT_JUSTICA},

        {"nome": "MP-RS", "url": "http://www.mp.rs.gov.br/rss/noticias/", "cat_id": CAT_JUSTICA},

        {"nome": "ConJur", "url": "https://www.conjur.com.br/rss.xml", "cat_id": CAT_JUSTICA},

        {"nome": "Jota", "url": "https://www.jota.info/feed/", "cat_id": CAT_JUSTICA}

    ],

    "estados_br": [

        {"nome": "Acre (Gov)", "url": "https://agencia.ac.gov.br/feed/", "cat_id": CAT_ESTADOS},

        {"nome": "Ceará (Gov)", "url": "https://www.ceara.gov.br/feed/", "cat_id": CAT_ESTADOS},

        {"nome": "Espírito Santo (Gov)", "url": "https://www.es.gov.br/rss", "cat_id": CAT_ESTADOS},

        {"nome": "Goiás (Gov)", "url": "https://goias.gov.br/?feed=rss2", "cat_id": CAT_ESTADOS},

        {"nome": "Minas Gerais (Gov)", "url": "https://www.agenciaminas.mg.gov.br/feed/", "cat_id": CAT_ESTADOS},

        {"nome": "Piauí (Gov)", "url": "https://www.pi.gov.br/feed/", "cat_id": CAT_ESTADOS},

        {"nome": "Rondônia (Gov)", "url": "https://rondonia.ro.gov.br/feed/", "cat_id": CAT_ESTADOS},

        {"nome": "Roraima (Gov)", "url": "https://portal.rr.gov.br/feed/", "cat_id": CAT_ESTADOS}

    ],



    # ==========================================

    # BLOCO 2: MEIO AMBIENTE E TECNOLOGIA

    # ==========================================

    "meio_ambiente_br": [

        {"nome": "((o))eco", "url": "https://oeco.org.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Observatório do Clima", "url": "https://www.oc.eco.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "ClimaInfo", "url": "https://climainfo.org.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Política por Inteiro", "url": "https://politicaporinteiro.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "SEEG", "url": "https://seeg.eco.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Eco21", "url": "https://eco21.eco.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Folha Ambiente", "url": "https://feeds.folha.uol.com.br/ambiente/rss091.xml", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Amazônia Real", "url": "https://amazoniareal.com.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "InfoAmazônia", "url": "https://infoamazonia.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Mongabay Brasil", "url": "https://brasil.mongabay.com/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Sumaúma", "url": "https://sumauma.com/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Agência Amazônia", "url": "https://agenciaamazonia.com.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Eco Nordeste", "url": "https://agenciaeconordeste.com.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Greenpeace Brasil", "url": "https://www.greenpeace.org/brasil/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "IDS", "url": "https://idsbrasil.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Instituto Talanoa", "url": "https://www.institutotalanoa.org/feed/", "cat_id": CAT_MEIO_AMBIENTE}

    ],

    "meio_ambiente_intl": [

        {"nome": "Carbon Brief", "url": "https://www.carbonbrief.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Inside Climate News", "url": "https://insideclimatenews.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Climate Home News", "url": "https://www.climatechangenews.com/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Grist", "url": "https://grist.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "DeSmog", "url": "https://www.desmog.com/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Mongabay Global", "url": "https://news.mongabay.com/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Guardian Environment", "url": "https://www.theguardian.com/environment/rss", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Covering Climate Now", "url": "https://coveringclimatenow.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Earth.Org", "url": "https://earth.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Anthropocene", "url": "https://www.anthropocenemagazine.org/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Ensia", "url": "https://ensia.com/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "CleanTechnica", "url": "https://cleantechnica.com/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "IUCN", "url": "https://www.iucn.org/rss.xml", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "UNEP", "url": "https://www.unep.org/rss.xml", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "IPCC", "url": "https://www.ipcc.ch/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "UNFCCC", "url": "https://unfccc.int/rss.xml", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "NOAA Climate", "url": "https://www.climate.gov/rss.xml", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Nature Climate", "url": "https://www.nature.com/nclimate.rss", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "ScienceDaily Clima", "url": "https://www.sciencedaily.com/rss/earth_climate/environmental_awareness.xml", "cat_id": CAT_MEIO_AMBIENTE}

    ],

    "esg_sustentabilidade": [

        {"nome": "Capital Reset", "url": "https://www.capitalreset.com/feed/", "cat_id": CAT_ESG},

        {"nome": "Página 22", "url": "https://pagina22.com.br/feed/", "cat_id": CAT_ESG},

        {"nome": "Instituto Ethos", "url": "https://www.ethos.org.br/feed/", "cat_id": CAT_ESG},

        {"nome": "Ideia Sustentável", "url": "https://ideiasustentavel.com.br/feed/", "cat_id": CAT_ESG},

        {"nome": "CicloVivo", "url": "https://ciclovivo.com.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Portal Resíduos", "url": "https://portalresiduossolidos.com/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "EcoDebate", "url": "https://www.ecodebate.com.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Pensamento Verde", "url": "https://www.pensamentoverde.com.br/feed/", "cat_id": CAT_MEIO_AMBIENTE},

        {"nome": "Projeto Colabora", "url": "https://projetocolabora.com.br/feed/", "cat_id": CAT_SOCIEDADE},

        {"nome": "Agência Bori", "url": "https://abori.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Nexo Políticas Pub", "url": "https://pp.nexojornal.com.br/rss.xml", "cat_id": CAT_POLITICA},

        {"nome": "Por Dentro África", "url": "https://www.pordentrodaafrica.com/feed/", "cat_id": CAT_INTERNACIONAL},

        {"nome": "ESG Today", "url": "https://www.esgtoday.com/feed/", "cat_id": CAT_ESG},

        {"nome": "Responsible Investor", "url": "https://www.responsible-investor.com/feed/", "cat_id": CAT_ESG},

        {"nome": "ESG Investor", "url": "https://www.esginvestor.net/feed/", "cat_id": CAT_ESG},

        {"nome": "ImpactAlpha", "url": "https://impactalpha.com/feed/", "cat_id": CAT_ESG},

        {"nome": "Just Capital", "url": "https://justcapital.com/feed/", "cat_id": CAT_ESG},

        {"nome": "Triple Pundit", "url": "https://www.triplepundit.com/feed/", "cat_id": CAT_ESG},

        {"nome": "CSRWire", "url": "https://www.csrwire.com/rss", "cat_id": CAT_ESG}

    ],

    "infra_telecom_logistica": [

        {"nome": "Telesíntese", "url": "https://www.telesintese.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Teletime", "url": "https://teletime.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Mobile Time", "url": "https://www.mobiletime.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "TelComp", "url": "https://www.telcomp.org.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Light Reading", "url": "https://www.lightreading.com/rss.xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Fierce Telecom", "url": "https://www.fiercetelecom.com/rss/xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Total Telecom", "url": "https://www.totaltele.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Megawhat", "url": "https://megawhat.energy/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Absolar", "url": "https://www.absolar.org.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "PV Magazine", "url": "https://www.pv-magazine.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Wind Power", "url": "https://www.windpowermonthly.com/rss", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Utility Dive", "url": "https://www.utilitydive.com/feeds/news/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Petronotícias", "url": "https://petronoticias.com.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Click Petróleo", "url": "https://clickpetroleoegas.com.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Valor Empresas", "url": "https://pox.globo.com/rss/valor/empresas/", "cat_id": CAT_ECONOMIA},

        {"nome": "OilPrice", "url": "https://oilprice.com/rss/main", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Rigzone", "url": "https://www.rigzone.com/news/rss/rigzone_latest.aspx", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Diário Transporte", "url": "https://diariodotransporte.com.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Portal NTC", "url": "https://www.portalntc.org.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "MundoGEO", "url": "https://mundogeo.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Supply Chain Dive", "url": "https://www.supplychaindive.com/feeds/news/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "FreightWaves", "url": "https://www.freightwaves.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "The Loadstar", "url": "https://theloadstar.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Mining.com", "url": "https://www.mining.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Mining Tech", "url": "https://www.mining-technology.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "IBRAM", "url": "https://ibram.org.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "CBIC", "url": "https://cbic.org.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "SindusCon-SP", "url": "https://sindusconsp.com.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Monitor Mercantil", "url": "https://monitormercantil.com.br/feed/", "cat_id": CAT_ECONOMIA},

        {"nome": "Construction Dive", "url": "https://www.constructiondive.com/feeds/news/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Aeroflap", "url": "https://www.aeroflap.com.br/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Splash247", "url": "https://splash247.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Railway Tech", "url": "https://www.railway-technology.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Intl Railway", "url": "https://www.railjournal.com/feed/", "cat_id": CAT_INFRAESTRUTURA},

        {"nome": "Canal Rural", "url": "https://www.canalrural.com.br/feed/", "cat_id": CAT_AGRO},

        {"nome": "De Olho Ruralistas", "url": "https://deolhonosruralistas.com.br/feed/", "cat_id": CAT_AGRO}

    ],

    "tecnologia_br": [

        {"nome": "Tecnoblog", "url": "https://tecnoblog.net/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Canaltech", "url": "https://canaltech.com.br/rss/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Olhar Digital", "url": "https://olhardigital.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "TecMundo", "url": "https://rss.tecmundo.com.br/feed", "cat_id": CAT_TECNOLOGIA},

        {"nome": "MacMagazine", "url": "https://macmagazine.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Showmetech", "url": "https://www.showmetech.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Tudocelular", "url": "https://www.tudocelular.com/rss/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Mundo Conectado", "url": "https://mundoconectado.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Convergência Digital", "url": "https://www.convergenciadigital.com.br/rss", "cat_id": CAT_TECNOLOGIA},

        {"nome": "IT Forum", "url": "https://itforum.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Meio Bit", "url": "https://meiobit.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Adrenaline", "url": "https://www.adrenaline.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Startupi", "url": "https://startupi.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "B9", "url": "https://www.b9.com.br/feed/", "cat_id": CAT_TECNOLOGIA}

    ],

    "tecnologia_intl": [

        {"nome": "TechCrunch", "url": "https://techcrunch.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Wired", "url": "https://www.wired.com/feed/rss", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Engadget", "url": "https://www.engadget.com/rss.xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "ZDNET", "url": "https://www.zdnet.com/news/rss.xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "CNET", "url": "https://www.cnet.com/rss/all/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Mashable", "url": "https://mashable.com/feeds/rss/all", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Gizmodo US", "url": "https://gizmodo.com/rss", "cat_id": CAT_TECNOLOGIA},

        {"nome": "TechRadar", "url": "https://www.techradar.com/rss", "cat_id": CAT_TECNOLOGIA},

        {"nome": "The Next Web", "url": "https://thenextweb.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "VentureBeat", "url": "https://venturebeat.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "9to5Mac", "url": "https://9to5mac.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "9to5Google", "url": "https://9to5google.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Tom's Hardware", "url": "https://www.tomshardware.com/feeds/all", "cat_id": CAT_TECNOLOGIA},

        {"nome": "The Register", "url": "https://www.theregister.com/headlines.atom", "cat_id": CAT_TECNOLOGIA},

        {"nome": "IEEE Spectrum", "url": "https://spectrum.ieee.org/feeds/feed.rss", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Rest of World", "url": "https://restofworld.org/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Hacker News", "url": "https://hnrss.org/frontpage", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Slashdot", "url": "http://rss.slashdot.org/Slashdot/slashdotMain", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Product Hunt", "url": "https://www.producthunt.com/feed", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Hacker Noon", "url": "https://hackernoon.com/feed", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Information Age", "url": "https://www.information-age.com/feed/", "cat_id": CAT_TECNOLOGIA}

    ],

    "ia_ciencia": [

        {"nome": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "AI Journal", "url": "https://aijourn.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "AI News", "url": "https://www.artificialintelligence-news.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Import AI", "url": "https://importai.substack.com/feed", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Last Week in AI", "url": "https://lastweekin.ai/feed", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Towards Data Science", "url": "https://towardsdatascience.com/feed", "cat_id": CAT_TECNOLOGIA},

        {"nome": "KDnuggets", "url": "https://www.kdnuggets.com/feed", "cat_id": CAT_TECNOLOGIA},

        {"nome": "ML Mastery", "url": "https://machinelearningmastery.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "SyncedReview", "url": "https://syncedreview.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "The Gradient", "url": "https://thegradient.pub/rss/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "AI Weirdness", "url": "https://www.aiweirdness.com/rss/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Simon Willison", "url": "https://simonwillison.net/atom/everything/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Google AI", "url": "https://blog.google/technology/ai/rss/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "DeepMind", "url": "https://deepmind.google/blog/rss.xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Microsoft AI", "url": "https://blogs.microsoft.com/ai/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "NVIDIA", "url": "https://blogs.nvidia.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "arXiv cs.AI", "url": "https://rss.arxiv.org/rss/cs.AI", "cat_id": CAT_TECNOLOGIA},

        {"nome": "arXiv cs.LG", "url": "https://rss.arxiv.org/rss/cs.LG", "cat_id": CAT_TECNOLOGIA},

        {"nome": "arXiv cs.CL", "url": "https://rss.arxiv.org/rss/cs.CL", "cat_id": CAT_TECNOLOGIA}

    ],

    "ciberseguranca": [

        {"nome": "CISO Advisor", "url": "https://www.cisoadvisor.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "The Hack", "url": "https://thehack.com.br/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Krebs Security", "url": "https://krebsonsecurity.com/feed/", "cat_id": CAT_TECNOLOGIA},

        {"nome": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews", "cat_id": CAT_TECNOLOGIA},

        {"nome": "Dark Reading", "url": "https://www.darkreading.com/rss.xml", "cat_id": CAT_TECNOLOGIA},

        {"nome": "SecurityWeek", "url": "https://www.securityweek.com/feed/", "cat_id": CAT_TECNOLOGIA}

    ],



    # ==========================================

    # BLOCO 3: MÍDIA, ENTRETENIMENTO E ESPORTES

    # ==========================================

    "grandes_portais_br": [

        {"nome": "G1", "url": "https://g1.globo.com/rss/g1/", "cat_id": CAT_POLITICA},

        {"nome": "G1 Política", "url": "https://g1.globo.com/rss/g1/politica/", "cat_id": CAT_POLITICA},

        {"nome": "G1 Economia", "url": "https://g1.globo.com/rss/g1/economia/", "cat_id": CAT_ECONOMIA},

        {"nome": "G1 Mundo", "url": "https://g1.globo.com/rss/g1/mundo/", "cat_id": CAT_INTERNACIONAL},

        {"nome": "G1 Jornal Nac", "url": "https://g1.globo.com/rss/g1/jornal-nacional/", "cat_id": CAT_POLITICA},

        {"nome": "O Globo", "url": "https://oglobo.globo.com/rss.xml", "cat_id": CAT_POLITICA},

        {"nome": "Extra", "url": "https://extra.globo.com/rss.xml", "cat_id": CAT_SOCIEDADE},

        {"nome": "UOL Notícias", "url": "https://rss.uol.com.br/feed/noticias.xml", "cat_id": CAT_POLITICA},

        {"nome": "Folha S.Paulo", "url": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml", "cat_id": CAT_POLITICA},

        {"nome": "Folha Poder", "url": "https://feeds.folha.uol.com.br/poder/rss091.xml", "cat_id": CAT_POLITICA},

        {"nome": "CNN Brasil", "url": "https://www.cnnbrasil.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Jovem Pan", "url": "https://jovempan.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Veja", "url": "https://veja.abril.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "IstoÉ", "url": "https://istoe.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "CartaCapital", "url": "https://www.cartacapital.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Correio Braziliense", "url": "https://www.correiobraziliense.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Jornal do Brasil", "url": "https://www.jb.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "O Dia", "url": "https://odia.ig.com.br/rss.xml", "cat_id": CAT_SOCIEDADE},

        {"nome": "IG", "url": "https://ultimosegundo.ig.com.br/rss.xml", "cat_id": CAT_POLITICA}

    ],

    "nativos_br": [

        {"nome": "Metrópoles", "url": "https://www.metropoles.com/feed", "cat_id": CAT_POLITICA},

        {"nome": "Poder360", "url": "https://www.poder360.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Brasil de Fato", "url": "https://www.brasildefato.com.br/rss2.xml", "cat_id": CAT_POLITICA},

        {"nome": "Nexo Jornal", "url": "https://www.nexojornal.com.br/rss.xml", "cat_id": CAT_POLITICA},

        {"nome": "The Intercept BR", "url": "https://www.intercept.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Agência Pública", "url": "https://apublica.org/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Repórter Brasil", "url": "https://reporterbrasil.org.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Revista Fórum", "url": "https://revistaforum.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "DCM", "url": "https://www.diariodocentrodomundo.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "O Antagonista", "url": "https://oantagonista.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Crusoé", "url": "https://crusoe.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Revista Oeste", "url": "https://revistaoeste.com/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Marco Zero", "url": "https://marcozero.org/feed/", "cat_id": CAT_SOCIEDADE},

        {"nome": "Jornal de Brasília", "url": "https://jornaldebrasilia.com.br/feed/", "cat_id": CAT_POLITICA},

        {"nome": "Tribuna do Norte", "url": "https://tribunadonorte.com.br/feed/", "cat_id": CAT_ESTADOS},

        {"nome": "Diário PE", "url": "https://www.diariodepernambuco.com.br/feed/", "cat_id": CAT_ESTADOS}

    ],

    "economia_financas": [

        {"nome": "Valor Econômico", "url": "https://pox.globo.com/rss/valor/", "cat_id": CAT_ECONOMIA},

        {"nome": "InfoMoney", "url": "https://www.infomoney.com.br/feed/", "cat_id": CAT_ECONOMIA},

        {"nome": "Exame", "url": "https://exame.com/feed/", "cat_id": CAT_ECONOMIA},

        {"nome": "Investing BR", "url": "https://br.investing.com/rss/news.rss", "cat_id": CAT_ECONOMIA},

        {"nome": "UOL Economia", "url": "https://rss.uol.com.br/feed/economia.xml", "cat_id": CAT_ECONOMIA}

    ],

    "entretenimento_br": [

        {"nome": "Gshow", "url": "https://gshow.globo.com/rss/gshow/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "G1 Pop & Arte", "url": "https://g1.globo.com/rss/g1/pop-arte/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Extra Famosos", "url": "https://extra.globo.com/famosos/rss.xml", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "UOL Entretenimento", "url": "https://rss.uol.com.br/feed/entretenimento.xml", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Metrópoles Entret", "url": "https://www.metropoles.com/entretenimento/feed", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Metrópoles Famosos", "url": "https://www.metropoles.com/famosos/feed", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Leo Dias", "url": "https://www.metropoles.com/colunas/leo-dias/feed", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "IG Gente", "url": "https://gente.ig.com.br/rss.xml", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Hugo Gloss", "url": "https://hugogloss.uol.com.br/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Contigo!", "url": "https://contigo.uol.com.br/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "TV Foco", "url": "https://www.otvfoco.com.br/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Papel Pop", "url": "https://www.papelpop.com/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Claudia", "url": "https://claudia.abril.com.br/feed/", "cat_id": CAT_SOCIEDADE},

        {"nome": "Capricho", "url": "https://capricho.abril.com.br/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Boa Forma", "url": "https://boaforma.abril.com.br/feed/", "cat_id": CAT_SAUDE},

        {"nome": "Elle Brasil", "url": "https://elle.com.br/feed/", "cat_id": CAT_CULTURA},

        {"nome": "Superinteressante", "url": "https://super.abril.com.br/feed/", "cat_id": CAT_CULTURA},

        {"nome": "Aventuras História", "url": "https://aventurasnahistoria.uol.com.br/feed/", "cat_id": CAT_CULTURA},

        {"nome": "Vida Simples", "url": "https://vidasimples.co/feed/", "cat_id": CAT_SOCIEDADE},

        {"nome": "Rolling Stone BR", "url": "https://rollingstone.uol.com.br/feed/", "cat_id": CAT_CULTURA},

        {"nome": "Legião Heróis", "url": "https://www.legiaodosherois.com.br/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Cinema Rapadura", "url": "https://cinemacomrapadura.com.br/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Pipoca Moderna", "url": "https://pipocamoderna.com.br/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "CinePOP", "url": "https://cinepop.com.br/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Meio & Mensagem", "url": "https://www.meioemensagem.com.br/feed/", "cat_id": CAT_ECONOMIA}

    ],

    "entretenimento_intl": [

        {"nome": "TMZ", "url": "https://www.tmz.com/rss.xml", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "E! Online", "url": "https://www.eonline.com/syndication/feeds/rssfeeds/topstories.xml", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Page Six", "url": "https://pagesix.com/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Variety", "url": "https://variety.com/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Hollywood Reporter", "url": "https://www.hollywoodreporter.com/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Deadline", "url": "https://deadline.com/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "BuzzFeed", "url": "https://www.buzzfeed.com/index.xml", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "IndieWire", "url": "https://www.indiewire.com/feed/", "cat_id": CAT_ENTRETENIMENTO},

        {"nome": "Pitchfork", "url": "https://pitchfork.com/feed/feed-news/rss", "cat_id": CAT_CULTURA},

        {"nome": "NME", "url": "https://www.nme.com/feed/", "cat_id": CAT_CULTURA},

        {"nome": "Consequence Sound", "url": "https://consequence.net/feed/", "cat_id": CAT_CULTURA}

    ],

    "esportes_br": [

        {"nome": "GE", "url": "https://ge.globo.com/rss/ge/", "cat_id": CAT_ESPORTES},

        {"nome": "GE Futebol", "url": "https://ge.globo.com/rss/ge/futebol/", "cat_id": CAT_ESPORTES},

        {"nome": "GE Fut Intl", "url": "https://ge.globo.com/rss/ge/futebol/futebol-internacional/", "cat_id": CAT_ESPORTES},

        {"nome": "GE F1", "url": "https://ge.globo.com/rss/ge/formula-1/", "cat_id": CAT_ESPORTES},

        {"nome": "GE Auto", "url": "https://ge.globo.com/rss/ge/automobilismo/", "cat_id": CAT_ESPORTES},

        {"nome": "GE Basquete", "url": "https://ge.globo.com/rss/ge/basquete/", "cat_id": CAT_ESPORTES},

        {"nome": "GE Vôlei", "url": "https://ge.globo.com/rss/ge/volei/", "cat_id": CAT_ESPORTES},

        {"nome": "GE Tênis", "url": "https://ge.globo.com/rss/ge/tenis/", "cat_id": CAT_ESPORTES},

        {"nome": "GE Lutas", "url": "https://ge.globo.com/rss/ge/lutas/", "cat_id": CAT_ESPORTES},

        {"nome": "GE SporTV", "url": "https://ge.globo.com/rss/ge/sportv/", "cat_id": CAT_ESPORTES},

        {"nome": "UOL Esporte", "url": "https://rss.uol.com.br/feed/esporte.xml", "cat_id": CAT_ESPORTES},

        {"nome": "ESPN Brasil", "url": "https://www.espn.com.br/rss/", "cat_id": CAT_ESPORTES},

        {"nome": "ESPN BR Futebol", "url": "https://www.espn.com.br/rss/futebol", "cat_id": CAT_ESPORTES},

        {"nome": "Gazeta Esportiva", "url": "https://www.gazetaesportiva.com/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Trivela", "url": "https://trivela.com.br/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Footure", "url": "https://footure.com.br/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Torcedores", "url": "https://www.torcedores.com/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "90min Brasil", "url": "https://www.90min.com/pt-BR/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Esporte News", "url": "https://esportenewsmundo.com.br/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Doentes Futebol", "url": "https://www.doentesporfutebol.com.br/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Netflu", "url": "https://www.netflu.com.br/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "FogãoNET", "url": "https://www.fogaonet.com/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Grande Prêmio", "url": "https://www.grandepremio.com.br/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Olimpíada TD", "url": "https://www.olimpiadatododia.com.br/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "Waves", "url": "https://www.waves.com.br/feed/", "cat_id": CAT_ESPORTES},

        {"nome": "CONMEBOL", "url": "https://www.conmebol.com/feed/", "cat_id": CAT_ESPORTES}

    ],

    "esportes_intl": [

        {"nome": "ESPN US", "url": "https://www.espn.com/espn/rss/news", "cat_id": CAT_ESPORTES},

        {"nome": "ESPN Soccer", "url": "https://www.espn.com/espn/rss/soccer/news", "cat_id": CAT_ESPORTES},

        {"nome": "ESPN NBA", "url": "https://www.espn.com/espn/rss/nba/news", "cat_id": CAT_ESPORTES},

        {"nome": "ESPN NFL", "url": "https://www.espn.com/espn/rss/nfl/news", "cat_id": CAT_ESPORTES},

        {"nome": "ESPN F1", "url": "https://www.espn.com/espn/rss/f1/news", "cat_id": CAT_ESPORTES},

        {"nome": "ESPN MMA", "url": "https://www.espn.com/espn/rss/mma/news", "cat_id": CAT_ESPORTES},

        {"nome": "ESPN MLB", "url": "https://www.espn.com/espn/rss/mlb/news", "cat_id": CAT_ESPORTES},

        {"nome": "BBC Sport", "url": "https://feeds.bbci.co.uk/sport/rss.xml", "cat_id": CAT_ESPORTES},

        {"nome": "BBC Football", "url": "https://feeds.bbci.co.uk/sport/football/rss.xml", "cat_id": CAT_ESPORTES},

        {"nome": "BBC F1", "url": "https://feeds.bbci.co.uk/sport/formula1/rss.xml", "cat_id": CAT_ESPORTES},

        {"nome": "Sky Sports", "url": "https://www.skysports.com/rss/12040", "cat_id": CAT_ESPORTES},

        {"nome": "Guardian Sport", "url": "https://www.theguardian.com/uk/sport/rss", "cat_id": CAT_ESPORTES},

        {"nome": "Guardian Football", "url": "https://www.theguardian.com/football/rss", "cat_id": CAT_ESPORTES},

        {"nome": "Marca", "url": "https://e00-marca.uecdn.es/rss/portada.xml", "cat_id": CAT_ESPORTES},

        {"nome": "AS", "url": "https://as.com/rss/diarioas/portada.xml", "cat_id": CAT_ESPORTES},

        {"nome": "Gazzetta", "url": "https://www.gazzetta.it/rss/home.xml", "cat_id": CAT_ESPORTES},

        {"nome": "Kicker", "url": "https://newsfeed.kicker.de/news/aktuell", "cat_id": CAT_ESPORTES},

        {"nome": "Yahoo Sports", "url": "https://sports.yahoo.com/rss/", "cat_id": CAT_ESPORTES},

        {"nome": "CBS Sports", "url": "https://www.cbssports.com/rss/headlines/", "cat_id": CAT_ESPORTES},

        {"nome": "Olé", "url": "https://www.ole.com.ar/rss/ultimas-noticias/", "cat_id": CAT_ESPORTES},

        {"nome": "Transfermarkt", "url": "https://www.transfermarkt.com/rss/news", "cat_id": CAT_ESPORTES},

        {"nome": "Autosport F1", "url": "https://www.autosport.com/rss/feed/f1", "cat_id": CAT_ESPORTES},

        {"nome": "RTP Desporto", "url": "https://www.rtp.pt/noticias/rss/desporto", "cat_id": CAT_ESPORTES},

        {"nome": "Record (PT)", "url": "https://www.record.pt/rss", "cat_id": CAT_ESPORTES}

    ],

    "internacional_pt": [

        {"nome": "BBC Brasil", "url": "https://feeds.bbci.co.uk/portuguese/rss.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "DW Brasil", "url": "https://rss.dw.com/xml/rss-br-top", "cat_id": CAT_INTERNACIONAL},

        {"nome": "RFI Brasil", "url": "https://www.rfi.fr/br/rss", "cat_id": CAT_INTERNACIONAL},

        {"nome": "RTP Notícias", "url": "https://www.rtp.pt/noticias/rss", "cat_id": CAT_INTERNACIONAL},



        {"nome": "RFI Portugal", "url": "https://www.rfi.fr/pt/rss", "cat_id": CAT_INTERNACIONAL},

        {"nome": "AIM", "url": "https://aimnews.org/feed/", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Tatoli", "url": "https://tatoli.tl/feed/", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Téla Nón", "url": "https://www.telanon.info/feed/", "cat_id": CAT_INTERNACIONAL}

    ],

    "internacional_global": [

        {"nome": "AP News", "url": "https://feedx.net/rss/ap.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "ANSA Itália", "url": "https://www.ansa.it/sito/ansait_rss.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Anadolu (AA)", "url": "https://www.aa.com.tr/en/rss/default?cat=world", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Yonhap", "url": "https://en.yna.co.kr/RSS/news.xml", "cat_id": CAT_INTERNACIONAL},



        {"nome": "Prensa Latina", "url": "https://www.prensa-latina.cu/feed/", "cat_id": CAT_INTERNACIONAL},

        {"nome": "TAP Tunísia", "url": "https://www.tap.info.tn/en/rss", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "France 24 EN", "url": "https://www.france24.com/en/rss", "cat_id": CAT_INTERNACIONAL},

        {"nome": "France 24 FR", "url": "https://www.france24.com/fr/rss", "cat_id": CAT_INTERNACIONAL},

        {"nome": "France 24 ES", "url": "https://www.france24.com/es/rss", "cat_id": CAT_INTERNACIONAL},

        {"nome": "RAI News", "url": "https://www.rainews.it/rss/tutti", "cat_id": CAT_INTERNACIONAL},

        {"nome": "RTVE", "url": "https://api2.rtve.es/rss/temas_noticias.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "Tagesschau", "url": "https://www.tagesschau.de/xml/rss2", "cat_id": CAT_INTERNACIONAL},

        {"nome": "ORF", "url": "https://rss.orf.at/news.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "NOS", "url": "https://feeds.nos.nl/nosnieuwsalgemeen", "cat_id": CAT_INTERNACIONAL},

        {"nome": "YLE", "url": "https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_UUTISET", "cat_id": CAT_INTERNACIONAL},

        {"nome": "RTÉ", "url": "https://www.rte.ie/feeds/rss/?index=/news/", "cat_id": CAT_INTERNACIONAL},

        {"nome": "NHK", "url": "https://www3.nhk.or.jp/rss/news/cat0.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "ABC Australia", "url": "https://www.abc.net.au/news/feed/2942460/rss.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "CBC", "url": "https://rss.cbc.ca/lineup/world.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "NPR", "url": "https://feeds.npr.org/1001/rss.xml", "cat_id": CAT_INTERNACIONAL},

        {"nome": "PBS NewsHour", "url": "https://www.pbs.org/newshour/feeds/rss/headlines", "cat_id": CAT_INTERNACIONAL},





        {"nome": "CNA Singapore", "url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml", "cat_id": CAT_INTERNACIONAL},



    ]

}
