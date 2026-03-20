#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONSTRUTOR DO KNOWLEDGE BASE - Newspaper Theme (tagDiv)
Cria e popula banco SQLite com documentação, componentes, ações e configurações.
"""

import sqlite3
import os
import subprocess
import json

DB_PATH = '/home/bitnami/newspaper_knowledge.db'

def criar_banco():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''CREATE TABLE doc_sections (
        id INTEGER PRIMARY KEY,
        parent_id INTEGER,
        section_name TEXT NOT NULL,
        doc_url TEXT,
        category TEXT,
        summary TEXT,
        instructions TEXT,
        FOREIGN KEY (parent_id) REFERENCES doc_sections(id)
    )''')

    c.execute('''CREATE TABLE theme_components (
        id INTEGER PRIMARY KEY,
        component_name TEXT NOT NULL,
        component_type TEXT,
        wp_location TEXT,
        db_table TEXT,
        db_key TEXT,
        db_sample_value TEXT,
        notes TEXT
    )''')

    c.execute('''CREATE TABLE action_paths (
        id INTEGER PRIMARY KEY,
        action_verb TEXT NOT NULL,
        target TEXT NOT NULL,
        wp_admin_path TEXT,
        api_endpoint TEXT,
        db_path TEXT,
        python_script TEXT,
        method TEXT,
        instructions TEXT
    )''')

    c.execute('''CREATE TABLE wp_categories (
        id INTEGER PRIMARY KEY,
        wp_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        slug TEXT,
        parent_wp_id INTEGER,
        category_type TEXT,
        post_count INTEGER
    )''')

    c.execute('''CREATE TABLE theme_settings (
        id INTEGER PRIMARY KEY,
        setting_key TEXT NOT NULL,
        setting_value TEXT,
        setting_group TEXT,
        data_type TEXT,
        description TEXT
    )''')

    c.execute('''CREATE TABLE change_log (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        briefing TEXT,
        action_taken TEXT,
        target_component TEXT,
        old_value TEXT,
        new_value TEXT,
        status TEXT,
        rollback_sql TEXT
    )''')

    # Índices
    c.execute('CREATE INDEX idx_doc_cat ON doc_sections(category)')
    c.execute('CREATE INDEX idx_doc_parent ON doc_sections(parent_id)')
    c.execute('CREATE INDEX idx_comp_type ON theme_components(component_type)')
    c.execute('CREATE INDEX idx_action_verb ON action_paths(action_verb)')
    c.execute('CREATE INDEX idx_action_target ON action_paths(target)')
    c.execute('CREATE INDEX idx_cat_wpid ON wp_categories(wp_id)')
    c.execute('CREATE INDEX idx_settings_group ON theme_settings(setting_group)')
    c.execute('CREATE INDEX idx_changelog_ts ON change_log(timestamp)')

    conn.commit()
    return conn


def popular_doc_sections(conn):
    """Popula hierarquia completa da documentação tagDiv com instruções detalhadas."""
    c = conn.cursor()
    # (id, parent_id, name, url, category, summary, instructions)
    docs = [
        # === GENERAL ===
        (1, None, 'General', None, 'general', 'Seção raiz de informações gerais do tema', None),
        (2, 1, 'Newspaper Theme Documentation', 'https://forum.tagdiv.com/newspaper-theme-documentation/', 'general',
         'Página principal da documentação. Newspaper é o tema WordPress mais versátil para news/magazine/publishing.',
         'Tema versátil para news, newspaper, magazine, publishing, online store ou review sites. Design elegante, código limpo, layouts responsivos, ads inteligentes e sistema de grid.'),
        (3, 1, 'Requirements for Newspaper', 'https://forum.tagdiv.com/requirements-for-newspaper/', 'general',
         'Requisitos de servidor e WordPress para rodar o tema.', None),
        (4, 1, "What's Included", 'https://forum.tagdiv.com/whats-included/', 'general',
         'Conteúdo incluído no pacote do tema.', None),
        (5, 1, 'Newspaper Theme Support', 'https://forum.tagdiv.com/newspaper-theme-support/', 'general',
         'Informações de suporte técnico.', None),

        # === INSTALLATION ===
        (6, None, 'Installation', None, 'installation', 'Seção de instalação do tema', None),
        (7, 6, 'Install via WordPress', 'https://forum.tagdiv.com/install-via-wordpress/', 'installation',
         'Instalação pelo painel WordPress.', 'Appearance > Themes > Add New > Upload Theme > Selecionar .zip > Install Now > Activate.'),
        (8, 6, 'Install via FTP', 'https://forum.tagdiv.com/install-via-ftp/', 'installation',
         'Instalação via FileZilla/FTP.', 'Upload pasta do tema para /wp-content/themes/ via FTP > Ativar no WP Admin.'),
        (9, 6, 'Activate Theme', 'https://forum.tagdiv.com/newspaper-6-how-to-activate-the-theme/', 'installation',
         'Ativação da licença.', 'Newspaper > Activate Theme > Inserir API key do Envato.'),
        (10, 6, 'Update Theme', 'https://forum.tagdiv.com/how-to-update-the-theme-2/', 'installation',
         'Atualização do tema.', 'Dashboard > Updates ou via FTP substituindo arquivos.'),

        # === PRE-BUILT WEBSITES ===
        (11, None, 'Pre-Built Websites', None, 'demos', 'Demos pré-construídas', None),
        (12, 11, 'Pre-built Websites Introduction', 'https://forum.tagdiv.com/demos_introduction/', 'demos',
         'Introdução às demos prontas.', None),
        (13, 11, 'Installing Pre-built Websites', 'https://forum.tagdiv.com/installing-demos/', 'demos',
         'Instalação de demos completas.', 'Newspaper > Install demos > Escolher demo > Install (full ou content only).'),

        # === TAGDIV PLUGINS ===
        (14, None, 'tagDiv Plugins', None, 'plugins', 'Plugins incluídos com o tema', None),
        (15, 14, 'tagDiv Composer', 'https://forum.tagdiv.com/tagdiv-composer-tutorial/', 'plugins',
         'Page builder frontend do Newspaper. OBRIGATÓRIO estar ativo.',
         'Plugin obrigatório. Edita páginas no frontend com drag-and-drop. Estrutura: Rows > Columns > Elements. '
         'Não usar simultaneamente com outros page builders. Botão "Edit with tagDiv Composer" na frontend. '
         'Settings: General tab (row layout, background, YouTube BG, stretch), Divider tab, Layout tab, CSS tab (margin/padding/border). '
         'Para homepage: Pages > Add New > Edit com Composer > Settings > Reading = static page.'),
        (16, 14, 'tagDiv Cloud Library', 'https://forum.tagdiv.com/tagdiv-cloud-library-plugin/', 'plugins',
         'Biblioteca de templates pré-desenhados na nuvem.',
         'Plugin que fornece templates prontos: headers, footers, single posts, categorias, 404, search, author pages. '
         'Importação com 1 clique. Requer tagDiv Cloud Library plugin instalado.'),
        (17, 16, 'How to Use Cloud Library', 'https://forum.tagdiv.com/how-use-tagdiv-cloud-library-templates/', 'plugins',
         'Tutorial de uso da Cloud Library.', 'Step 1: Instalar plugin. Step 2: Abrir template específico. Step 3: Clicar Cloud Library. Step 4: Selecionar e importar.'),
        (18, 14, 'tagDiv Social Counter', 'https://forum.tagdiv.com/tagdiv-social-counter-intro/', 'plugins',
         'Widget de contadores sociais.', None),
        (19, 14, 'tagDiv Mobile Theme', 'https://forum.tagdiv.com/mobile-theme-introduction/', 'plugins',
         'Tema mobile dedicado com AMP.', 'Settings em Newspaper > Mobile Theme. Suporta AMP via tagDiv AMP plugin.'),
        (20, 14, 'tagDiv Opt-In Builder', 'https://forum.tagdiv.com/tagdiv-opt-in-builder/', 'plugins',
         'Paywall, lockers, leads, subscriptions.', 'Cria lockers, popups, subscriptions. Integra PayPal. Suporta cupons e créditos.'),
        (21, 14, 'tagDiv Shop', 'https://forum.tagdiv.com/tagdiv-shop/', 'plugins',
         'Integração WooCommerce.', None),
        (22, 14, 'tagDiv Newsletter', 'https://forum.tagdiv.com/the-newsletter-plugin/', 'plugins',
         'Plugin de newsletter integrado.', None),

        # === HEADER ===
        (23, None, 'Header', None, 'header', 'Configurações do cabeçalho', None),
        (24, 23, 'Header Builder', 'https://forum.tagdiv.com/header-manager/', 'header',
         '100+ templates de header pré-desenhados. Cada página pode ter header diferente.',
         'Step 1: Frontend > Edit with tagDiv Composer. Step 2: Clicar ícone Manager (canto sup esquerdo) ou Website Manager. '
         'Step 3: Ver headers importados, definir Global. Step 4: Import Header > escolher da Cloud Library > OK > Done. '
         'Step 7: Website Manager permite customizar por zonas: Main Menu, Mobile Menu, Main Menu Sticky, Mobile Menu Sticky. '
         'On/Off para sticky. Headers diferentes por página: editar header em página específica SEM marcar Global.'),
        (25, 23, 'Logo', 'https://forum.tagdiv.com/add-logo-newspaper/', 'header',
         'Adicionar/trocar logo (imagem, SVG, texto ou URL).',
         'Abrir com tagDiv Composer > Header Logo element. Pode colocar em header, conteúdo ou footer. '
         'Para trocar em template existente: Homepage > Edit with Composer > clicar logo > Upload Logo Image + Logo Retina > Show Image. '
         'Formatos: .png, .jpg. SVG no tab SVG (sobrescreve imagem). Se prebuilt site não mostra logo, verificar tab SVG. Salvar.'),
        (26, 23, 'Favicon & iOS Bookmarklet', 'https://forum.tagdiv.com/logo-favicon/', 'header',
         'Favicon e ícone iOS.', 'Settings > General > Site Icon (512x512px).'),
        (27, 23, 'Main Menu', 'https://forum.tagdiv.com/main-menu/', 'header',
         'Menu principal com múltiplos níveis de dropdown.',
         'Criar: WP Dashboard > Appearance > Menus > Create New Menu > Nomear > Create Menu. '
         'Customizar: Step 1: Adicionar items (Pages, Links, Categories). Step 2: Drag-and-drop para reordenar. '
         'Step 3: Scroll até Theme Locations > Header Main. Step 4: Save Menu.'),
        (28, 23, 'Mega Menu', 'https://forum.tagdiv.com/mega-menu/', 'header',
         'Menu mega com posts de categorias e suporte a subcategorias.',
         'Com subcategorias: Appearance > Menu > Adicionar item > Clicar > Selecionar Category do dropdown. '
         'Sem subcategorias: adicionar item de categoria normal, o mega menu mostra posts automaticamente.'),
        (29, 23, 'Page Mega Menu', 'https://forum.tagdiv.com/page-menu/', 'header',
         'Mega menu baseado em páginas.', None),
        (30, 23, 'User Registration', 'https://forum.tagdiv.com/login-how-to-enable-user-registration/', 'header',
         'Habilitar login/registro de usuários.', 'Settings > General > Membership > Anyone can register.'),

        # === FOOTER ===
        (31, None, 'Footer', None, 'footer', 'Configurações do rodapé', None),
        (32, 31, 'Footer Builder', 'https://forum.tagdiv.com/footer-templates/', 'footer',
         '86+ templates de footer editáveis. Cada página pode ter footer diferente.',
         'Step 1: Frontend > Edit with tagDiv Composer. Step 2: Website Manager (ícone ou botão). '
         'Step 3: Import Footer > Cloud Library abre. Step 4: Escolher template > Import Footer > OK > Done. '
         'Step 5: Customizar Footer Zone (background, gradients, YouTube video, elementos). '
         'Marcar checkbox para tornar Global. Pode usar Blank Footer para começar do zero.'),

        # === ADS ===
        (33, None, 'Ads', None, 'ads', 'Sistema de publicidade', None),
        (34, 33, 'Ad Box Element', 'https://forum.tagdiv.com/ads-adsense-overview/', 'ads',
         'Sistema inteligente de ads. 3 métodos: Image Ad, AdSense, Theme Panel.',
         'Step 1: Edit with tagDiv Composer. Step 2: Drag Ad Box element para qualquer área. '
         '3 modos: (1) Image Ad: upload imagem por device (tablet landscape/portrait/phone) + Ad URL + rel (nofollow/noreferrer). '
         '(2) AdSense: colar código no Custom Ad tab > Custom ad code box. NÃO usar em floating/sticky. '
         '(3) Theme Panel: Newspaper > Theme Panel > Ads.'),
        (35, 33, 'Article Ad', 'https://forum.tagdiv.com/article-ads/', 'ads',
         'Ads inline dentro de artigos.', None),
        (36, 33, 'Background Ads', 'https://forum.tagdiv.com/background-ads/', 'ads',
         'Ads no background do site.', None),

        # === TEMPLATE SETTINGS ===
        (37, None, 'Template Settings', None, 'templates', 'Configurações de templates', None),
        (38, 37, 'Cloud Library Templates', 'https://forum.tagdiv.com/cloud-library-templates/', 'templates',
         'Templates para: 404, Archive, Attachment, Author, Search, Tag, Category, Single Post.',
         'Step 1: Instalar tagDiv Cloud Library. Step 2: Abrir template específico. Step 3: Cloud Library button. Step 4: Importar. '
         'Tipos: 404, Archive (mensal/anual), Attachment, Author Page (global ou individual), Search Page, Tag, Category, Single Post. '
         'Pode importar Blank template e adicionar shortcodes manualmente.'),
        (39, 37, 'Website Manager', 'https://forum.tagdiv.com/tagdiv-composer-website-manager/', 'templates',
         'Ferramenta central de gestão de headers, footers e templates.', None),
        (40, 37, 'Smart Sidebar', 'https://forum.tagdiv.com/smart-sidebar-2/', 'templates',
         'Sidebar sticky/flutuante que acompanha scroll.',
         'Dividir row em 2 colunas > selecionar coluna para sidebar > General settings > marcar Sticky. '
         'Funciona em páginas e templates. A sticky sidebar viaja com o conteúdo até encontrar nova row.'),
        (41, 37, 'Breadcrumbs', 'https://forum.tagdiv.com/breadcrumbs/', 'templates',
         'Navegação em breadcrumbs.', None),
        (42, 37, 'LazyLoad & Image Effects', 'https://forum.tagdiv.com/loading-image-effects/', 'templates',
         'Carregamento lazy de imagens.', None),

        # === CATEGORIES SETTINGS ===
        (43, None, 'Categories Settings', None, 'categories', 'Configurações de categorias', None),
        (44, 43, 'Category Templates', 'https://forum.tagdiv.com/cloud-library-category-templates/', 'categories',
         'Templates específicos por categoria via Cloud Library.', None),
        (45, 43, 'Category Background', 'https://forum.tagdiv.com/set-background-category-page/', 'categories',
         'Background por página de categoria.', None),

        # === POST SETTINGS ===
        (46, None, 'Post Settings', None, 'posts', 'Configurações de posts', None),
        (47, 46, 'Single Post Templates', 'https://forum.tagdiv.com/design-post-pages-using-cloud-library-templates/', 'posts',
         'Templates de post via Cloud Library. Múltiplos templates, atribuir a posts específicos.',
         'Criar quantos templates quiser. Atribuir a múltiplos posts ou um específico. '
         'Editar com tagDiv Composer sem CSS manual. Drag-and-drop de elementos, blocos e seções. '
         'Pode adicionar Social Counter, Popular Articles, sidebar/footer específicos.'),
        (48, 46, 'Single Post Shortcodes', 'https://forum.tagdiv.com/single-post-shortcodes/', 'posts',
         'Shortcodes específicos para posts.', None),
        (49, 46, 'Infinite Loading', 'https://forum.tagdiv.com/infinite-loading-single-posts/', 'posts',
         'Carregamento infinito de posts.', None),
        (50, 46, 'Ajax View Count', 'https://forum.tagdiv.com/ajax-view-count/', 'posts',
         'Contagem de views via Ajax.', None),

        # === BLOCK SETTINGS ===
        (51, None, 'Block Settings', None, 'blocks', 'Configurações de blocos', None),
        (52, 51, 'Flex Block Settings', 'https://forum.tagdiv.com/flex-block-settings-guide/', 'blocks',
         '5 tipos de Flex Block. Abas: General, Filter, Layout, Style, CSS.',
         'General: título, URL, header template (18 estilos), cores, content length, limit posts, offset, open in new tab, cache. '
         'Filter: Post ID, Category Filter, Multiple terms (IDs separados por vírgula, - para excluir), Tag slug, Author IDs, Post type (CPT). '
         'Filtros especiais: Single (author/category/tags/taxonomy/siblings), Category/Author/Tag/Date/Search/Taxonomy templates. '
         'Layout: colunas, imagem, meta info. Style: fonts block/module, cores. CSS: customização avançada.'),
        (53, 51, 'Big Grid Flex', 'https://forum.tagdiv.com/big-grid-flex-settings/', 'blocks',
         'Grid grande para destaques.', None),
        (54, 51, 'Posts Loop Element', 'https://forum.tagdiv.com/posts-loop/', 'blocks',
         'Elemento de loop de posts.', None),
        (55, 51, 'Flex Block Builder', 'https://forum.tagdiv.com/flex-block-builder-flex-loop-builder/', 'blocks',
         'Builder de Flex Blocks e Flex Loops.', None),
        (56, 51, 'Modules Builder', 'https://forum.tagdiv.com/modules-builder-newspaper-theme/', 'blocks',
         'Builder de módulos.', None),
        (57, 51, 'Theme Thumbs', 'https://forum.tagdiv.com/theme-thumbs/', 'blocks',
         'Thumbnails do tema.', None),
        (58, 51, 'Offset Feature', 'https://forum.tagdiv.com/offset-feature/', 'blocks',
         'Offset para pular posts já exibidos.', 'Offset 5 = começa do 6º post. Útil para evitar duplicação entre blocos.'),

        # === APPEARANCE ===
        (59, None, 'Background', None, 'appearance', 'Background do site', None),
        (60, 59, 'Background Introduction', 'https://forum.tagdiv.com/background-introduction/', 'appearance',
         'Configuração de background.', None),
        (61, None, 'Excerpts', None, 'appearance', 'Excerpts/resumos', None),
        (62, 61, 'Excerpts Introduction', 'https://forum.tagdiv.com/excerpts-introduction/', 'appearance',
         'Configuração de excerpts.', None),
        (63, None, 'Theme Colors', None, 'colors', 'Cores do tema', None),
        (64, 63, 'Theme Colors Introduction', 'https://forum.tagdiv.com/theme-colors-introduction/', 'colors',
         '2 métodos: Theme Panel (global) e tagDiv Composer (por página).',
         'Theme Panel: Newspaper > Theme Panel > Theme Color. 3 áreas: '
         '(1) General: Theme accent (hover/links/buttons/Ajax), Background. '
         '(2) Header: Mobile Menu & Search, Sign In/Join modal. '
         '(3) Content: titles, text, H1-H6. Background color ativa versão boxed automaticamente.'),
        (65, None, 'Theme Fonts', None, 'fonts', 'Fontes do tema', None),
        (66, 65, 'Font Customization', 'https://forum.tagdiv.com/font-customization/', 'fonts',
         '4 métodos: Composer element, Website Manager, Theme Panel global, Custom .woff files.',
         'Composer: Style tab de cada elemento. Website Manager: análise de fontes em uso + troca dinâmica. '
         'Theme Panel: Newspaper > Theme Panel > Theme Fonts (Google, custom, standard) global. '
         'Custom: upload .woff via botão, aparece no dropdown de seleção.'),

        # === TRANSLATIONS ===
        (67, None, 'Translations', None, 'translations', 'Traduções do tema', None),
        (68, 67, 'Loading Translations', 'https://forum.tagdiv.com/loading-translations/', 'translations',
         'Carregar traduções automáticas (90 idiomas pré-feitos ou Google Translate).',
         'Step 1: Theme Panel > Translations > Load an available translation. '
         'Step 2: Choose a language > Load translation. '
         'Step 3: Painel abre para ajustar cada string traduzida.'),
        (69, 67, 'Customize Translation', 'https://forum.tagdiv.com/customize-a-translation/', 'translations',
         'Personalizar strings traduzidas.', None),

        # === CPT & TAXONOMY ===
        (70, None, 'CPT & Taxonomy', None, 'cpt', 'Custom Post Types e Taxonomias', None),
        (71, 70, 'CPT and ACF', 'https://forum.tagdiv.com/introduction-cpt-acf-newspaper-theme/', 'cpt',
         'Suporte a Custom Post Types com ACF.', None),
        (72, 70, 'Custom Post Type Support', 'https://forum.tagdiv.com/custom-post-type-support/', 'cpt',
         'Suporte nativo a CPTs.', None),

        # === IMPORT/EXPORT ===
        (73, None, 'Import / Export', None, 'import_export', 'Import/Export de configurações', None),
        (74, 73, 'Import/Export Theme Settings', 'https://forum.tagdiv.com/import-export-theme-settings/', 'import_export',
         'Importar/exportar configurações do tema.', None),

        # === PAGE SETTINGS ===
        (75, None, 'Page Settings', None, 'pages', 'Configurações de páginas', None),
        (76, 75, 'Homepage', 'https://forum.tagdiv.com/homepage-how-to-build-and-set-it/', 'pages',
         'Criar e definir homepage.',
         'Step 1: Pages > Add New. Step 2: Editar com tagDiv Composer, adicionar elementos, selecionar template. '
         'Step 3: Settings > Reading > Static page > selecionar página criada.'),
        (77, 75, 'Unique Articles', 'https://forum.tagdiv.com/unique-articles/', 'pages',
         'Artigos únicos (não repetir entre blocos).', None),

        # === POSTS SETTINGS ===
        (78, None, 'Posts Settings (Content)', None, 'post_content', 'Configurações de conteúdo de posts', None),
        (79, 78, 'Author Card', 'https://forum.tagdiv.com/author-card/', 'post_content', 'Card de autor.', None),
        (80, 78, 'Featured Posts', 'https://forum.tagdiv.com/featured-posts-2/', 'post_content', 'Posts em destaque.', None),
        (81, 78, 'Featured Image/Video/Audio', 'https://forum.tagdiv.com/featured-image-or-video/', 'post_content', 'Mídia destacada.', None),
        (82, 78, 'Primary Category', 'https://forum.tagdiv.com/primary-category/', 'post_content', 'Categoria primária do post.', None),

        # === TUTORIALS ===
        (83, None, 'Tutorials', None, 'tutorials', 'Tutoriais diversos', None),
        (84, 83, 'Social Sharing', 'https://forum.tagdiv.com/social-sharing/', 'tutorials', 'Compartilhamento social.', None),
        (85, 83, 'Social Icons', 'https://forum.tagdiv.com/social-icons/', 'tutorials', 'Ícones sociais.', None),
        (86, 83, 'Weather Block', 'https://forum.tagdiv.com/weather-widget/', 'tutorials', 'Bloco de clima.', None),
        (87, 83, 'Exchange Block', 'https://forum.tagdiv.com/exchange-widget/', 'tutorials', 'Bloco de câmbio.', None),
        (88, 83, 'Modal Popup', 'https://forum.tagdiv.com/modal-popup/', 'tutorials', 'Popup modal.', None),
        (89, 83, 'Sidebars Tutorial', 'https://forum.tagdiv.com/sidebars-tutorial/', 'tutorials', 'Tutorial de sidebars.', None),

        # === GUIDES ===
        (90, None, 'Guides', None, 'guides', 'Guias de otimização e integração', None),
        (91, 90, 'Child Theme Support', 'https://forum.tagdiv.com/the-child-theme-support-tutorial/', 'guides', 'Suporte a child theme.', None),
        (92, 90, 'Pagespeed Guide', 'https://forum.tagdiv.com/how-to-make-the-site-faster/', 'guides', 'Otimização de velocidade.', None),
        (93, 90, 'Cache Plugin', 'https://forum.tagdiv.com/cache-plugin-install-and-configure/', 'guides', 'Instalar e configurar cache.', None),
        (94, 90, 'Cloudflare', 'https://forum.tagdiv.com/cloudflare-cdn/', 'guides', 'Tutorial Cloudflare CDN.', None),
    ]

    c.executemany(
        'INSERT INTO doc_sections (id, parent_id, section_name, doc_url, category, summary, instructions) VALUES (?,?,?,?,?,?,?)',
        docs
    )
    conn.commit()
    print(f"[OK] {len(docs)} seções de documentação inseridas.")


def popular_componentes(conn):
    """Popula componentes manipuláveis do tema."""
    c = conn.cursor()
    comps = [
        ('header', 'template', 'tagDiv Composer > Website Manager', 'wp_7_posts', 'tdb_templates (post_type)', None, 'Cada header é um tdb_templates post. Global via Website Manager.'),
        ('header_logo', 'element', 'tagDiv Composer > Header Logo element', 'wp_7_postmeta', 'tdc_content', None, 'Elemento Header Logo no Composer. SVG sobrescreve imagem.'),
        ('footer', 'template', 'tagDiv Composer > Website Manager', 'wp_7_posts', 'tdb_templates (post_type)', None, 'Footer templates importados da Cloud Library.'),
        ('main_menu', 'layout', 'WP Dashboard > Appearance > Menus', 'wp_7_posts', 'nav_menu_item (post_type)', None, 'Theme Location: Header Main.'),
        ('mega_menu', 'layout', 'WP Dashboard > Appearance > Menus', 'wp_7_postmeta', 'td_mega_menu_cat', None, 'Associa item de menu a categoria para mostrar posts.'),
        ('sidebar', 'layout', 'tagDiv Composer > Column > General > Sticky', 'wp_7_postmeta', 'tdc_content', None, 'Marcar Sticky na coluna para Smart Sidebar.'),
        ('flex_block', 'shortcode', 'tagDiv Composer > Add Element', 'wp_7_postmeta', 'tdc_content', '[td_flex_block_1 ...]', '5 tipos (1-5). Abas: General, Filter, Layout, Style, CSS.'),
        ('big_grid', 'shortcode', 'tagDiv Composer > Add Element', 'wp_7_postmeta', 'tdc_content', '[td_block_big_grid_flex_1 ...]', 'Grid grande para destaques na homepage.'),
        ('ad_box', 'element', 'tagDiv Composer > Ad Box', 'wp_7_postmeta', 'tdc_content', None, 'Image Ad, AdSense code, ou Theme Panel custom ads.'),
        ('theme_colors', 'setting', 'Newspaper > Theme Panel > Theme Color', 'wp_7_options', 'td_011', None, '3 áreas: General (accent/bg), Header (mobile/signin), Content (titles/text/H1-H6).'),
        ('theme_fonts', 'setting', 'Newspaper > Theme Panel > Theme Fonts', 'wp_7_options', 'td_011', None, 'Google Fonts, custom .woff, standard. Também via Composer Style tab.'),
        ('translations', 'setting', 'Newspaper > Theme Panel > Translations', 'wp_7_options', 'td_011', None, '90 idiomas pré-feitos. Google Translate disponível.'),
        ('homepage_layout', 'layout', 'Frontend > Edit with tagDiv Composer', 'wp_7_postmeta', 'tdc_content', None, 'Post ID 18135 na Brasileira.news. Layout encoded em tdc_content.'),
        ('single_post_template', 'template', 'tagDiv Cloud Library > Single Post', 'wp_7_posts', 'tdb_templates (post_type)', None, 'Atribuir a posts específicos ou múltiplos. tdc_template_name meta.'),
        ('category_template', 'template', 'tagDiv Cloud Library > Category', 'wp_7_posts', 'tdb_templates (post_type)', None, 'Template por categoria via Cloud Library.'),
        ('404_template', 'template', 'tagDiv Cloud Library > 404', 'wp_7_posts', 'tdb_templates (post_type)', None, 'Página 404 customizável.'),
        ('search_template', 'template', 'tagDiv Cloud Library > Search', 'wp_7_posts', 'tdb_templates (post_type)', None, 'Página de busca customizável.'),
        ('author_template', 'template', 'tagDiv Cloud Library > Author', 'wp_7_posts', 'tdb_templates (post_type)', None, 'Página de autor. Global ou individual.'),
        ('weather_block', 'widget', 'tagDiv Composer > Weather widget', 'wp_7_postmeta', 'tdc_content', None, 'Bloco de previsão do tempo.'),
        ('social_counter', 'widget', 'tagDiv Social Counter plugin', 'wp_7_options', 'td_011', None, 'Contadores de redes sociais.'),
        ('newsletter', 'widget', 'tagDiv Newsletter plugin', 'wp_7_options', 'td_011', None, 'Formulário de newsletter integrado.'),
        ('breadcrumbs', 'element', 'tagDiv Composer > Breadcrumbs element', 'wp_7_postmeta', 'tdc_content', None, 'Navegação breadcrumbs.'),
        ('opt_in_locker', 'plugin', 'tagDiv Opt-In Builder', 'wp_7_posts', 'tds_locker (post_type)', None, 'Lockers, popups, subscriptions, paywall.'),
        ('background', 'setting', 'Theme Panel ou Row settings no Composer', 'wp_7_options', 'td_011', None, 'Background global ou por row (imagem, gradient, vídeo).'),
        ('lazy_load', 'setting', 'Newspaper > Theme Panel', 'wp_7_options', 'td_011', None, 'Carregamento preguiçoso de imagens.'),
        ('child_theme', 'setting', 'wp-content/themes/Starter-starter/', None, None, None, 'Recomendado para customizações que sobrevivam atualizações.'),
    ]
    c.executemany(
        'INSERT INTO theme_components (component_name, component_type, wp_location, db_table, db_key, db_sample_value, notes) VALUES (?,?,?,?,?,?,?)',
        comps
    )
    conn.commit()
    print(f"[OK] {len(comps)} componentes inseridos.")


def popular_action_paths(conn):
    """Popula mapeamento de ações → caminhos."""
    c = conn.cursor()
    actions = [
        # LOGO
        ('alterar', 'logo', '/wp-admin/ > Edit with tagDiv Composer', None, 'wp_7_postmeta.tdc_content (header template)', None, 'wp_admin',
         'Edit with tagDiv Composer na homepage > clicar no logo > Upload Logo Image + Retina > Show Image > Save. Para SVG: tab SVG.'),
        # MENU
        ('alterar', 'menu', '/wp-admin/nav-menus.php', '/wp-json/wp/v2/menus', 'wp_7_posts (nav_menu_item), wp_7_terms', 'atualizar_menu.py', 'wp_admin',
         'Appearance > Menus > selecionar menu > arrastar items > Theme Locations: Header Main > Save Menu.'),
        ('adicionar', 'item_menu', '/wp-admin/nav-menus.php', '/wp-json/wp/v2/menu-items', 'wp_7_posts (nav_menu_item)', 'atualizar_menu_items.py', 'script',
         'Adicionar Pages/Categories/Links no painel esquerdo > arrastar para posição desejada > Save Menu.'),
        # CATEGORIAS
        ('adicionar', 'categoria', '/wp-admin/edit-tags.php?taxonomy=category', '/wp-json/wp/v2/categories', 'wp_7_terms, wp_7_term_taxonomy', None, 'api',
         'Posts > Categories > Nome + Slug + Parent > Add New Category. Via API: POST /wp-json/wp/v2/categories {"name":"...", "parent":ID}'),
        ('alterar', 'categoria', '/wp-admin/edit-tags.php?taxonomy=category', '/wp-json/wp/v2/categories/{id}', 'wp_7_terms', None, 'api',
         'PUT /wp-json/wp/v2/categories/{id} {"name":"...", "slug":"..."}'),
        # HOMEPAGE
        ('alterar', 'homepage_layout', None, None, 'wp_7_postmeta.tdc_content WHERE post_id=18135', 'reorganizar_homepage.py', 'script',
         'Editar tdc_content do post 18135. Usar reorganizar_homepage.py para mapear categorias. aplicar_homepage.py para salvar no DB.'),
        ('alterar', 'homepage_bloco', None, None, 'wp_7_postmeta.tdc_content WHERE post_id=18135', None, 'database',
         'Alterar shortcode no tdc_content: category_id, limit, offset, button_url, description (base64).'),
        # HEADER
        ('alterar', 'header', None, None, 'wp_7_posts (tdb_templates), wp_7_postmeta.tdc_header_template_id', None, 'wp_admin',
         'Edit with tagDiv Composer > Website Manager > Import/selecionar Header > Customizar zonas > Save.'),
        ('alterar', 'header_global', None, None, 'wp_7_postmeta.tdc_header_template_id', None, 'wp_admin',
         'Website Manager > marcar header como Global. Afeta todas as páginas.'),
        # FOOTER
        ('alterar', 'footer', None, None, 'wp_7_posts (tdb_templates), wp_7_postmeta.tdc_footer_template_id', None, 'wp_admin',
         'Edit with tagDiv Composer > Website Manager > Import Footer > Customizar > Marcar Global se desejado.'),
        # CORES
        ('alterar', 'cor_primaria', '/wp-admin/admin.php?page=td_theme_panel', None, 'wp_7_options.td_011', None, 'wp_admin',
         'Theme Panel > Theme Color > General > Theme accent. Afeta hover, links, buttons, Ajax.'),
        ('alterar', 'cor_background', '/wp-admin/admin.php?page=td_theme_panel', None, 'wp_7_options.td_011', None, 'wp_admin',
         'Theme Panel > Theme Color > General > Background. Ativa versão boxed automaticamente.'),
        ('alterar', 'cores_header', '/wp-admin/admin.php?page=td_theme_panel', None, 'wp_7_options.td_011', None, 'wp_admin',
         'Theme Panel > Theme Color > Header section > Mobile Menu, Sign In/Join.'),
        ('alterar', 'cores_conteudo', '/wp-admin/admin.php?page=td_theme_panel', None, 'wp_7_options.td_011', None, 'wp_admin',
         'Theme Panel > Theme Color > Content > titles, text, H1-H6.'),
        # FONTES
        ('alterar', 'fonte_global', '/wp-admin/admin.php?page=td_theme_panel', None, 'wp_7_options.td_011', None, 'wp_admin',
         'Theme Panel > Theme Fonts > Google/custom/standard. Refresh painel após adicionar.'),
        ('alterar', 'fonte_elemento', None, None, 'wp_7_postmeta.tdc_content', None, 'wp_admin',
         'tagDiv Composer > selecionar elemento > Style tab > Font settings.'),
        # TRADUÇÕES
        ('alterar', 'traducao', '/wp-admin/admin.php?page=td_theme_panel', None, 'wp_7_options.td_011', None, 'wp_admin',
         'Theme Panel > Translations > Load available translation > Idioma > Load > Ajustar strings.'),
        # POSTS
        ('publicar', 'post', None, '/wp-json/wp/v2/posts', 'wp_7_posts', 'gestor_wp.py', 'script',
         'Via gestor_wp.py: publicar_no_wordpress(dados, autor_id, cat_id, veiculo). Cria post com título, conteúdo, excerpt, categorias, tags, autor, imagem.'),
        ('alterar', 'template_post', None, None, 'wp_7_postmeta.td_post_theme_settings', None, 'database',
         'Serialized array em td_post_theme_settings. Inclui template ID atribuído ao post.'),
        # ADS
        ('adicionar', 'ad', None, None, 'wp_7_postmeta.tdc_content', None, 'wp_admin',
         'tagDiv Composer > drag Ad Box element > Configurar: Image Ad (upload), AdSense (colar código), ou Theme Panel (Newspaper > Ads).'),
        # SIDEBAR
        ('criar', 'sidebar_sticky', None, None, 'wp_7_postmeta.tdc_content', None, 'wp_admin',
         'tagDiv Composer > Row > dividir em 2 colunas > selecionar coluna > General > Sticky checkbox.'),
        # TEMPLATES
        ('importar', 'template_cloud', None, None, 'wp_7_posts (tdb_templates)', None, 'wp_admin',
         'tagDiv Composer > Cloud Library button > selecionar tipo > escolher template > Import > Done.'),
        # CONSULTAS
        ('consultar', 'posts_por_categoria', None, '/wp-json/wp/v2/posts?categories={id}', 'wp_7_posts + wp_7_term_relationships', None, 'api',
         'GET /wp-json/wp/v2/posts?categories={cat_id}&per_page=10'),
        ('consultar', 'configuracoes_tema', None, None, 'wp_7_options WHERE option_name="td_011"', None, 'database',
         'SELECT option_value FROM wp_7_options WHERE option_name="td_011". Valor serializado PHP (564 configurações).'),
        ('consultar', 'templates_ativos', None, None, 'wp_7_posts WHERE post_type="tdb_templates"', None, 'database',
         'SELECT ID, post_title FROM wp_7_posts WHERE post_type="tdb_templates" AND post_status="publish".'),
    ]
    c.executemany(
        'INSERT INTO action_paths (action_verb, target, wp_admin_path, api_endpoint, db_path, python_script, method, instructions) VALUES (?,?,?,?,?,?,?,?)',
        actions
    )
    conn.commit()
    print(f"[OK] {len(actions)} caminhos de ação inseridos.")


def popular_categorias(conn):
    """Popula categorias a partir do config_categorias.py."""
    c = conn.cursor()
    cats = [
        (71, 'Política & Poder', 'politica-poder', None, 'macro', None),
        (72, 'Economia & Negócios', 'economia-negocios', None, 'macro', None),
        (73, 'Justiça & Direito', 'justica-direito', None, 'macro', None),
        (74, 'Saúde', 'saude', None, 'macro', None),
        (75, 'Educação', 'educacao', None, 'macro', None),
        (76, 'Sociedade & Direitos Humanos', 'sociedade-direitos-humanos', None, 'macro', None),
        (78, 'Infraestrutura & Cidades', 'infraestrutura-cidades', None, 'macro', None),
        (79, 'Cultura', 'cultura', None, 'macro', None),
        (80, 'Turismo', 'turismo', None, 'macro', None),
        (81, 'Esportes', 'esportes-modalidades', None, 'macro', None),
        (88, 'Internacional', 'internacional', None, 'macro', None),
        (94, 'Estados do Brasil', 'estados', None, 'macro', None),
        (122, 'Entretenimento & Famosos', 'entretenimento-famosos', None, 'macro', None),
        (129, 'Tecnologia & Ciência', 'segmentos-tecnologia', None, 'macro', None),
        (135, 'Agronegócio', 'agronegocio', None, 'macro', None),
        (136, 'Meio Ambiente & ESG', 'meio-ambiente', None, 'macro', None),
        # Subcategorias - Esportes
        (82, 'Futebol Brasileiro', 'futebol-brasileiro', 81, 'sub', None),
        (83, 'Futebol Internacional', 'futebol-internacional', 81, 'sub', None),
        (84, 'Fórmula 1 & Automobilismo', 'formula-1', 81, 'sub', None),
        (85, 'Basquete & NBA', 'basquete-nba', 81, 'sub', None),
        (86, 'Lutas & MMA', 'lutas-mma', 81, 'sub', None),
        (87, 'Esportes Olímpicos', 'olimpicos', 81, 'sub', None),
        # Subcategorias - Internacional
        (89, 'Américas', 'americas', 88, 'sub', None),
        (90, 'Europa', 'europa', 88, 'sub', None),
        (91, 'Ásia & Pacífico', 'asia-pacifico', 88, 'sub', None),
        (92, 'África', 'africa', 88, 'sub', None),
        (93, 'Oriente Médio', 'oriente-medio', 88, 'sub', None),
        # Subcategorias - Entretenimento
        (123, 'Segmentos Entretenimento', 'segmentos-entretenimento', 122, 'sub', None),
        (124, 'Fofoca & Celebridades', 'fofoca-celebridades', 122, 'sub', None),
        (125, 'Cinema & Séries', 'cinema-series', 122, 'sub', None),
        (126, 'Música', 'musica', 122, 'sub', None),
        (127, 'Lifestyle', 'lifestyle', 122, 'sub', None),
        (128, 'Cultura Pop', 'cultura-pop', 122, 'sub', None),
        # Subcategorias - Tecnologia
        (130, 'Inteligência Artificial', 'inteligencia-artificial', 129, 'sub', None),
        (131, 'Cibersegurança', 'ciberseguranca', 129, 'sub', None),
        (132, 'Startups & Inovação', 'startups-inovacao', 129, 'sub', None),
        (133, 'Gadgets & Hardware', 'gadgets-hardware', 129, 'sub', None),
        (134, 'Ciência & Pesquisa', 'ciencia-pesquisa', 129, 'sub', None),
        (137, 'Telecomunicações', 'telecomunicacoes', 129, 'sub', None),
        # Subcategorias - Meio Ambiente
        (141, 'Clima & Mudanças Climáticas', 'clima', 136, 'sub', None),
        (142, 'ESG & Sustentabilidade', 'esg', 136, 'sub', None),
        (143, 'Amazônia', 'amazonia', 136, 'sub', None),
        (144, 'Economia Circular', 'economia-circular', 136, 'sub', None),
        (145, 'ONGs & Terceiro Setor', 'ongs', 136, 'sub', None),
        # Subcategorias - Infraestrutura
        (138, 'Logística & Transportes', 'logistica', 78, 'sub', None),
        (139, 'Petróleo & Gás', 'petroleo', 78, 'sub', None),
        (140, 'Energia & Mineração', 'energia', 78, 'sub', None),
    ]
    c.executemany(
        'INSERT INTO wp_categories (wp_id, name, slug, parent_wp_id, category_type, post_count) VALUES (?,?,?,?,?,?)',
        cats
    )
    conn.commit()
    print(f"[OK] {len(cats)} categorias inseridas.")


def popular_theme_settings(conn):
    """Popula configurações conhecidas do tema a partir do banco WordPress."""
    c = conn.cursor()
    settings = [
        ('theme_version', '12.7.5', 'general', 'string', 'Versão atual do tema Newspaper'),
        ('demo_installed', 'downtown_pro', 'general', 'string', 'Demo pré-construída instalada'),
        ('demo_install_type', 'full', 'general', 'string', 'Tipo de instalação da demo'),
        ('homepage_post_id', '18135', 'general', 'integer', 'ID do post que contém o layout da homepage'),
        ('default_author_id', '4', 'general', 'integer', 'ID do autor padrão (Redação)'),
        ('wp_url', 'https://brasileira.news', 'general', 'string', 'URL do site'),
        ('table_prefix', 'wp_7_', 'general', 'string', 'Prefixo das tabelas WordPress'),
        ('td_options_key', 'td_011', 'general', 'string', 'Option name com todas as configurações do tema'),
        ('td_options_count', '564', 'general', 'integer', 'Número de configurações no td_011'),
        ('header_menu_id', '11725', 'header', 'integer', 'ID do menu principal (header-menu)'),
        ('tdb_templates_count', '9', 'templates', 'integer', 'Número de templates tagDiv ativos'),
        ('total_published_posts', '9180', 'content', 'integer', 'Total de posts publicados'),
        ('main_category_ids', '71,72,73,74,75,76,78,79,80,81,88,94,122,129,135,136', 'categories', 'string', 'IDs das categorias macro'),
        ('tdc_content_key', 'tdc_content', 'templates', 'string', 'Meta key para conteúdo de layout do Composer'),
        ('tdc_header_template_key', 'tdc_header_template_id', 'header', 'string', 'Meta key para template de header'),
        ('tdc_footer_template_key', 'tdc_footer_template_id', 'footer', 'string', 'Meta key para template de footer'),
        ('td_post_theme_key', 'td_post_theme_settings', 'posts', 'string', 'Meta key para configurações de tema por post'),
        ('td_mega_menu_key', 'td_mega_menu_cat', 'header', 'string', 'Meta key para mega menu por categoria'),
    ]
    c.executemany(
        'INSERT INTO theme_settings (setting_key, setting_value, setting_group, data_type, description) VALUES (?,?,?,?,?)',
        settings
    )
    conn.commit()
    print(f"[OK] {len(settings)} configurações inseridas.")


def atualizar_post_counts(conn):
    """Tenta atualizar contagem de posts por categoria via MariaDB."""
    try:
        cmd = [
            '/opt/bitnami/mariadb/bin/mariadb',
            '-u', 'bn_wordpress',
            f'-p{os.getenv("DB_PASS")}',
            '-h', '127.0.0.1', '-P', '3306', 'bitnami_wordpress', '-N', '-e',
            "SELECT tt.term_id, tt.count FROM wp_7_term_taxonomy tt WHERE tt.taxonomy='category';"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            c = conn.cursor()
            updated = 0
            for line in result.stdout.strip().split('\n'):
                if '\t' in line:
                    parts = line.split('\t')
                    term_id, count = int(parts[0]), int(parts[1])
                    c.execute('UPDATE wp_categories SET post_count = ? WHERE wp_id = ?', (count, term_id))
                    if c.rowcount > 0:
                        updated += 1
            conn.commit()
            print(f"[OK] Contagem de posts atualizada para {updated} categorias.")
    except Exception as e:
        print(f"[AVISO] Não foi possível atualizar contagem de posts: {e}")


# ============================
# EXECUÇÃO PRINCIPAL
# ============================
if __name__ == '__main__':
    print("=" * 60)
    print("CONSTRUINDO KNOWLEDGE BASE - Newspaper Theme")
    print("=" * 60)

    conn = criar_banco()
    print(f"\n[OK] Banco criado: {DB_PATH}")

    popular_doc_sections(conn)
    popular_componentes(conn)
    popular_action_paths(conn)
    popular_categorias(conn)
    popular_theme_settings(conn)
    atualizar_post_counts(conn)

    # Resumo final
    c = conn.cursor()
    for table in ['doc_sections', 'theme_components', 'action_paths', 'wp_categories', 'theme_settings']:
        c.execute(f'SELECT COUNT(*) FROM {table}')
        print(f"  {table}: {c.fetchone()[0]} registros")

    conn.close()
    print(f"\n{'=' * 60}")
    print(f"Knowledge Base pronto: {DB_PATH}")
    print(f"{'=' * 60}")
