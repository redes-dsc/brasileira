<?php
/**
 * Funções principais do tema brasileira-theme.
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

define( 'BRASILEIRA_VERSION', '1.0.0' );
define( 'BRASILEIRA_DIR', get_template_directory() );
define( 'BRASILEIRA_URL', get_template_directory_uri() );
define( 'BRASILEIRA_ASSETS', BRASILEIRA_URL . '/assets' );

require_once BRASILEIRA_DIR . '/inc/class-block-registry.php';
require_once BRASILEIRA_DIR . '/inc/class-cache-manager.php';
require_once BRASILEIRA_DIR . '/inc/class-ad-manager.php';
require_once BRASILEIRA_DIR . '/inc/class-layout-engine.php';

/**
 * Configuração inicial do tema.
 *
 * @return void
 */
function brasileira_setup(): void {
	add_theme_support( 'post-thumbnails' );
	add_theme_support( 'title-tag' );
	add_theme_support(
		'html5',
		array( 'search-form', 'comment-form', 'gallery', 'caption', 'script', 'style', 'navigation-widgets' )
	);
	add_theme_support(
		'custom-logo',
		array(
			'height'      => 60,
			'width'       => 240,
			'flex-height' => true,
			'flex-width'  => true,
		)
	);
	add_theme_support( 'editor-styles' );
	add_editor_style( 'assets/css/editor.css' );
	add_theme_support( 'wp-block-styles' );
	add_theme_support( 'responsive-embeds' );
	add_theme_support( 'align-wide' );

	add_post_type_support( 'page', 'excerpt' );

	add_image_size( 'brasileira-hero', 1200, 630, true );
	add_image_size( 'brasileira-card', 600, 350, true );
	add_image_size( 'brasileira-thumb', 300, 200, true );
	add_image_size( 'brasileira-square', 300, 300, true );

	register_nav_menus(
		array(
			'primary' => __( 'Menu Principal', 'brasileira-theme' ),
			'footer'  => __( 'Menu Rodapé', 'brasileira-theme' ),
			'mobile'  => __( 'Menu Mobile', 'brasileira-theme' ),
		)
	);
}
add_action( 'after_setup_theme', 'brasileira_setup' );

/**
 * Enfileira fontes, CSS e JS do front.
 *
 * @return void
 */
function brasileira_enqueue_assets(): void {
	wp_enqueue_style(
		'brasileira-fonts',
		'https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Condensed:wght@600&display=swap',
		array(),
		null
	);
	wp_enqueue_style(
		'brasileira-base',
		BRASILEIRA_ASSETS . '/css/base.css',
		array( 'brasileira-fonts' ),
		BRASILEIRA_VERSION
	);
	wp_enqueue_script(
		'brasileira-live-updates',
		BRASILEIRA_ASSETS . '/js/live-updates.js',
		array(),
		BRASILEIRA_VERSION,
		true
	);
	wp_enqueue_script(
		'brasileira-lazy-blocks',
		BRASILEIRA_ASSETS . '/js/lazy-blocks.js',
		array(),
		BRASILEIRA_VERSION,
		true
	);
	wp_localize_script(
		'brasileira-live-updates',
		'BrasileiraSite',
		array(
			'ajaxUrl'    => admin_url( 'admin-ajax.php' ),
			'restUrl'    => rest_url( 'brasileira/v1/' ),
			'nonce'      => wp_create_nonce( 'brasileira_nonce' ),
			'sseEnabled' => (bool) apply_filters( 'brasileira_sse_enabled', false ),
		)
	);
}
add_action( 'wp_enqueue_scripts', 'brasileira_enqueue_assets', 5 );

/**
 * Resolve o page_id cujo layout JSON deve ser usado nesta requisição.
 *
 * @return int
 */
function brasileira_get_layout_page_id(): int {
	if ( is_front_page() ) {
		$fid = (int) get_option( 'page_on_front' );
		if ( $fid > 0 ) {
			return $fid;
		}
	}
	if ( is_singular( 'page' ) ) {
		$qid = get_queried_object_id();
		return $qid > 0 ? $qid : 0;
	}
	return (int) apply_filters( 'brasileira_layout_page_id', 0 );
}

/**
 * Enfileira CSS apenas dos blocos presentes no layout da página atual.
 * Executa antes do fechamento do head (prioridade 15).
 *
 * @return void
 */
function brasileira_enqueue_layout_block_styles(): void {
	if ( is_admin() ) {
		return;
	}
	$page_id = brasileira_get_layout_page_id();
	if ( $page_id <= 0 ) {
		return;
	}
	$engine = new Brasileira_Layout_Engine();
	foreach ( $engine->get_active_block_types( $page_id ) as $type ) {
		$subdir = Brasileira_Layout_Engine::type_to_subdir( $type );
		$path   = BRASILEIRA_DIR . '/blocks/' . $subdir . '/style.css';
		$url    = BRASILEIRA_URL . '/blocks/' . $subdir . '/style.css';
		if ( is_readable( $path ) ) {
			wp_enqueue_style(
				'brasileira-block-' . $subdir,
				$url,
				array( 'brasileira-base' ),
				BRASILEIRA_VERSION
			);
		}
	}
}
add_action( 'wp_enqueue_scripts', 'brasileira_enqueue_layout_block_styles', 15 );

/**
 * Invalida cache de blocos ao salvar post.
 *
 * @param int $post_id ID do post.
 * @return void
 */
function brasileira_invalidate_cache_on_save( int $post_id ): void {
	if ( wp_is_post_revision( $post_id ) ) {
		return;
	}
	Brasileira_Cache_Manager::flush_post_blocks( $post_id );
}
add_action( 'save_post', 'brasileira_invalidate_cache_on_save' );

/**
 * Sidebars legadas (widgets clássicos).
 *
 * @return void
 */
function brasileira_register_sidebars(): void {
	register_sidebar(
		array(
			'name'          => __( 'Sidebar Principal', 'brasileira-theme' ),
			'id'            => 'sidebar-main',
			'before_widget' => '<div id="%1$s" class="widget %2$s">',
			'after_widget'  => '</div>',
			'before_title'  => '<h3 class="widget-title">',
			'after_title'   => '</h3>',
		)
	);
	register_sidebar(
		array(
			'name'          => __( 'Sidebar Cotações', 'brasileira-theme' ),
			'id'            => 'sidebar-cotacoes',
			'before_widget' => '<div id="%1$s" class="widget %2$s">',
			'after_widget'  => '</div>',
			'before_title'  => '<h3 class="widget-title">',
			'after_title'   => '</h3>',
		)
	);
}
add_action( 'widgets_init', 'brasileira_register_sidebars' );

/**
 * Renderiza bloco dinâmico do motor de layout.
 *
 * @param array<string, mixed> $attributes Atributos do bloco.
 * @return string
 */
function brasileira_render_layout_engine_block( array $attributes ): string {
	$page_id = isset( $attributes['pageId'] ) ? (int) $attributes['pageId'] : 0;
	if ( $page_id <= 0 ) {
		$page_id = brasileira_get_layout_page_id();
	}
	if ( $page_id <= 0 ) {
		return '';
	}
	$engine = new Brasileira_Layout_Engine();
	return $engine->render_page( $page_id );
}

/**
 * Faixa de breaking no single quando a matéria tem tag `breaking`.
 *
 * @return string
 */
function brasileira_render_breaking_notice_block(): string {
	if ( ! is_singular( 'post' ) ) {
		return '';
	}
	$post = get_queried_object();
	if ( ! $post instanceof WP_Post ) {
		return '';
	}
	if ( ! has_tag( 'breaking', $post ) ) {
		return '';
	}
	return '<div class="brasileira-breaking-strip" role="status"><span class="brasileira-breaking-strip__label">' . esc_html__( 'Última hora', 'brasileira-theme' ) . '</span><span class="brasileira-breaking-strip__text">' . esc_html( get_the_title( $post ) ) . '</span></div>';
}

/**
 * Lista simples de relacionadas (mesma categoria).
 *
 * @return string
 */
function brasileira_render_related_posts_block(): string {
	if ( ! is_singular( 'post' ) ) {
		return '';
	}
	$post_id = get_queried_object_id();
	$cats    = wp_get_post_categories( $post_id );
	if ( $cats === array() ) {
		return '';
	}
	$q = new WP_Query(
		array(
			'category__in'   => $cats,
			'post__not_in'   => array( $post_id ),
			'posts_per_page' => 3,
			'orderby'        => 'date',
			'order'          => 'DESC',
			'no_found_rows'  => true,
		)
	);
	if ( ! $q->have_posts() ) {
		return '';
	}
	$html  = '<aside class="brasileira-related" aria-labelledby="brasileira-related-title"><h2 id="brasileira-related-title" class="brasileira-related__title">' . esc_html__( 'Relacionadas', 'brasileira-theme' ) . '</h2><ul class="brasileira-related__list">';
	while ( $q->have_posts() ) {
		$q->the_post();
		$html .= '<li class="brasileira-related__item"><a href="' . esc_url( get_permalink() ) . '">' . esc_html( get_the_title() ) . '</a></li>';
	}
	wp_reset_postdata();
	$html .= '</ul></aside>';
	return $html;
}

/**
 * Registra blocos dinâmicos PHP (FSE não executa PHP em .html).
 *
 * @return void
 */
function brasileira_register_theme_blocks(): void {
	register_block_type(
		'brasileira/layout-engine',
		array(
			'api_version'     => 3,
			'title'           => __( 'Motor de layout (JSON)', 'brasileira-theme' ),
			'description'     => __( 'Renderiza blocos editoriais a partir do layout salvo em wp_options.', 'brasileira-theme' ),
			'category'        => 'brasileira',
			'attributes'      => array(
				'pageId' => array(
					'type'    => 'number',
					'default' => 0,
				),
			),
			'render_callback' => static function ( $attributes ) {
				return brasileira_render_layout_engine_block( is_array( $attributes ) ? $attributes : array() );
			},
		)
	);
	register_block_type(
		'brasileira/breaking-notice',
		array(
			'api_version'     => 3,
			'title'           => __( 'Faixa de breaking (single)', 'brasileira-theme' ),
			'category'        => 'brasileira',
			'render_callback' => static function () {
				return brasileira_render_breaking_notice_block();
			},
		)
	);
	register_block_type(
		'brasileira/related-posts',
		array(
			'api_version'     => 3,
			'title'           => __( 'Relacionadas', 'brasileira-theme' ),
			'category'        => 'brasileira',
			'render_callback' => static function () {
				return brasileira_render_related_posts_block();
			},
		)
	);
}
add_action( 'init', 'brasileira_register_theme_blocks' );

/**
 * Categoria de blocos no inserter.
 *
 * @param array<int, array<string, mixed>> $categories Categorias existentes.
 * @return array<int, array<string, mixed>>
 */
function brasileira_block_categories( array $categories ): array {
	$categories[] = array(
		'slug'  => 'brasileira',
		'title' => __( 'Brasileira', 'brasileira-theme' ),
		'icon'  => null,
	);
	return $categories;
}
add_filter( 'block_categories_all', 'brasileira_block_categories', 10, 1 );
