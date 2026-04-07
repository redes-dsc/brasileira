<?php
/**
 * Registro dos 18 tipos de bloco editorial — schemas, TTLs e variantes.
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

/**
 * Classe Brasileira_Block_Registry
 */
class Brasileira_Block_Registry {

	/**
	 * Tipos registrados.
	 *
	 * @var array<string, array<string, mixed>>
	 */
	private array $types = array();

	/**
	 * Construtor.
	 */
	public function __construct() {
		$this->register_all();
	}

	/**
	 * Registra todos os tipos (contrato TIER 1 + plano técnico).
	 *
	 * @return void
	 */
	private function register_all(): void {
		$this->register(
			'breaking',
			array(
				'label'             => 'Breaking News',
				'description'       => 'Alerta de última hora em destaque',
				'cache_ttl'         => 60,
				'has_auto_expire'   => true,
				'style_variants'    => array( 'fullwidth_red', 'fullwidth_orange', 'ticker_bar' ),
				'config_schema'     => array(
					'required' => array( 'post_id', 'label', 'style' ),
					'optional' => array( 'auto_expire_minutes', 'auto_expire_at', 'created_at' ),
				),
			)
		);

		$this->register(
			'manchete',
			array(
				'label'             => 'Manchete',
				'description'       => 'Hero principal da homepage',
				'cache_ttl'         => 120,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'hero_large', 'hero_split', 'hero_video' ),
				'config_schema'     => array(
					'required' => array( 'principal', 'style' ),
					'optional' => array( 'submanchetes' ),
				),
			)
		);

		$this->register(
			'macrotema',
			array(
				'label'             => 'Macrotema',
				'description'       => 'Cobertura transversal (ex.: guerra, eleições)',
				'cache_ttl'         => 180,
				'has_auto_expire'   => true,
				'style_variants'    => array( 'highlight_band', 'section_full', 'sidebar_box' ),
				'config_schema'     => array(
					'required' => array( 'tag_id', 'label', 'posts', 'style' ),
					'optional' => array( 'icon', 'subhome_page_id', 'temporary', 'created_at', 'auto_expire_at' ),
				),
			)
		);

		$this->register(
			'editoria',
			array(
				'label'             => 'Editoria',
				'description'       => 'Seção por categoria editorial',
				'cache_ttl'         => 180,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'grid_3', 'grid_4_sidebar', 'grid_5', 'grid_6_mosaic', 'list_compact' ),
				'config_schema'     => array(
					'required' => array( 'category_id', 'label', 'posts', 'style' ),
					'optional' => array( 'show_more_link', 'more_link_url', 'sidebar_widget' ),
				),
			)
		);

		$this->register(
			'colunistas',
			array(
				'label'             => 'Colunistas',
				'description'       => 'Destaques de colunistas',
				'cache_ttl'         => 300,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'carousel_horizontal', 'grid_4' ),
				'config_schema'     => array(
					'required' => array( 'colunistas', 'style' ),
					'optional' => array(),
				),
			)
		);

		$this->register(
			'ultimas',
			array(
				'label'             => 'Últimas Notícias',
				'description'       => 'Feed cronológico',
				'cache_ttl'         => 60,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'feed_list', 'feed_cards' ),
				'config_schema'     => array(
					'required' => array( 'count', 'style' ),
					'optional' => array( 'auto_refresh_seconds' ),
				),
			)
		);

		$this->register(
			'mais_lidas',
			array(
				'label'             => 'Mais Lidas',
				'description'       => 'Ranking por período',
				'cache_ttl'         => 300,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'numbered_list', 'sidebar_compact' ),
				'config_schema'     => array(
					'required' => array( 'period', 'count', 'style' ),
					'optional' => array(),
				),
			)
		);

		$this->register(
			'opiniao',
			array(
				'label'             => 'Opinião',
				'description'       => 'Artigos de opinião',
				'cache_ttl'         => 300,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'cards_editorial', 'list_quotes', 'list_byline' ),
				'config_schema'     => array(
					'required' => array( 'posts', 'style' ),
					'optional' => array(),
				),
			)
		);

		$this->register(
			'publicidade',
			array(
				'label'             => 'Publicidade',
				'description'       => 'Slot de anúncio',
				'cache_ttl'         => 0,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'leaderboard', 'rectangle', 'fullwidth' ),
				'config_schema'     => array(
					'required' => array( 'slot', 'size' ),
					'optional' => array( 'fallback', 'style' ),
				),
			)
		);

		$this->register(
			'ticker',
			array(
				'label'             => 'Ticker',
				'description'       => 'Fita de dados (mercado, índices)',
				'cache_ttl'         => 60,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'bar_dark', 'bar_light', 'horizontal_scroll', 'static_grid' ),
				'config_schema'     => array(
					'required' => array( 'sources', 'style' ),
					'optional' => array( 'auto_refresh_seconds', 'refresh_seconds' ),
				),
			)
		);

		$this->register(
			'video',
			array(
				'label'             => 'Vídeo',
				'description'       => 'Seção de vídeos',
				'cache_ttl'         => 300,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'featured_player', 'grid_thumbnails', 'grid_videos' ),
				'config_schema'     => array(
					'required' => array( 'featured_post_id', 'style' ),
					'optional' => array( 'playlist', 'autoplay', 'muted' ),
				),
			)
		);

		$this->register(
			'podcast',
			array(
				'label'             => 'Podcast',
				'description'       => 'Episódios em destaque',
				'cache_ttl'         => 300,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'player_featured', 'list_episodes', 'player_podcast' ),
				'config_schema'     => array(
					'required' => array( 'style' ),
					'optional' => array( 'featured_episode_id', 'episodes', 'show_id' ),
				),
			)
		);

		$this->register(
			'regional',
			array(
				'label'             => 'Regional',
				'description'       => 'Blocos por UF / região',
				'cache_ttl'         => 300,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'map_grid', 'uf_tabs', 'tabs_regional', 'grid_ufs' ),
				'config_schema'     => array(
					'required' => array( 'ufs', 'style' ),
					'optional' => array( 'posts_per_uf', 'highlight_uf' ),
				),
			)
		);

		$this->register(
			'newsletter_cta',
			array(
				'label'             => 'Newsletter CTA',
				'description'       => 'Chamada para newsletter',
				'cache_ttl'         => 3600,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'banner_full', 'inline_form', 'inline_banner', 'popup_trigger', 'sidebar_box', 'modal_trigger' ),
				'config_schema'     => array(
					'required' => array( 'variant' ),
					'optional' => array( 'headline', 'cta_text', 'title', 'subtitle', 'button_text', 'form_id' ),
				),
			)
		);

		$this->register(
			'especial',
			array(
				'label'             => 'Especial',
				'description'       => 'Destaque de reportagem especial',
				'cache_ttl'         => 600,
				'has_auto_expire'   => true,
				'style_variants'    => array( 'fullwidth_cover', 'side_panel', 'banner_especial', 'card_destaque' ),
				'config_schema'     => array(
					'required' => array( 'post_id', 'style' ),
					'optional' => array( 'label', 'subtitle', 'badge_text', 'auto_expire_at' ),
				),
			)
		);

		$this->register(
			'galeria',
			array(
				'label'             => 'Galeria',
				'description'       => 'Galeria de imagens',
				'cache_ttl'         => 300,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'masonry_grid', 'horizontal_carousel', 'slideshow', 'grid_fotos' ),
				'config_schema'     => array(
					'required' => array( 'posts', 'style' ),
					'optional' => array( 'images', 'caption', 'lightbox' ),
				),
			)
		);

		$this->register(
			'trending',
			array(
				'label'             => 'Trending',
				'description'       => 'Assuntos em alta',
				'cache_ttl'         => 300,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'tag_cloud', 'numbered_topics', 'tags_cloud', 'list_trending' ),
				'config_schema'     => array(
					'required' => array( 'style' ),
					'optional' => array( 'topics', 'count', 'period', 'max_items' ),
				),
			)
		);

		$this->register(
			'custom',
			array(
				'label'             => 'Personalizado',
				'description'       => 'HTML livre controlado pelo curador',
				'cache_ttl'         => 600,
				'has_auto_expire'   => false,
				'style_variants'    => array( 'default' ),
				'config_schema'     => array(
					'required' => array( 'html' ),
					'optional' => array( 'css_class', 'wrapper_tag' ),
				),
			)
		);
	}

	/**
	 * Registra um tipo.
	 *
	 * @param string               $type   Slug do tipo.
	 * @param array<string, mixed> $config Configuração.
	 * @return void
	 */
	private function register( string $type, array $config ): void {
		$this->types[ $type ] = $config;
	}

	/**
	 * Indica se o tipo existe.
	 *
	 * @param string $type Tipo.
	 * @return bool
	 */
	public function is_registered( string $type ): bool {
		return isset( $this->types[ $type ] );
	}

	/**
	 * TTL de cache em segundos.
	 *
	 * @param string $type Tipo.
	 * @return int
	 */
	public function get_ttl( string $type ): int {
		return (int) ( $this->types[ $type ]['cache_ttl'] ?? 300 );
	}

	/**
	 * Configuração completa do tipo.
	 *
	 * @param string $type Tipo.
	 * @return array<string, mixed>|null
	 */
	public function get_type( string $type ): ?array {
		return $this->types[ $type ] ?? null;
	}

	/**
	 * Todos os tipos.
	 *
	 * @return array<string, array<string, mixed>>
	 */
	public function get_all(): array {
		return $this->types;
	}

	/**
	 * Variantes de estilo.
	 *
	 * @param string $type Tipo.
	 * @return string[]
	 */
	public function get_variants( string $type ): array {
		$v = $this->types[ $type ]['style_variants'] ?? array();
		return is_array( $v ) ? $v : array();
	}
}
