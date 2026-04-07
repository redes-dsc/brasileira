<?php
/**
 * Motor de renderização dinâmica — JSON de layout → HTML.
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

/**
 * Classe Brasileira_Layout_Engine
 */
class Brasileira_Layout_Engine {

	/**
	 * Registro de tipos.
	 *
	 * @var Brasileira_Block_Registry
	 */
	private Brasileira_Block_Registry $registry;

	/**
	 * Cache de fragmentos.
	 *
	 * @var Brasileira_Cache_Manager
	 */
	private Brasileira_Cache_Manager $cache;

	/**
	 * Construtor.
	 */
	public function __construct() {
		$this->registry = new Brasileira_Block_Registry();
		$this->cache    = new Brasileira_Cache_Manager();
	}

	/**
	 * Mapeia tipo lógico (underscore) para pasta em /blocks.
	 *
	 * @param string $type Tipo do JSON.
	 * @return string Subdiretório existente no tema.
	 */
	public static function type_to_subdir( string $type ): string {
		$map = array(
			'newsletter_cta' => 'newsletter-cta',
			'mais_lidas'     => 'mais-lidas',
		);
		return $map[ $type ] ?? $type;
	}

	/**
	 * Lê e decodifica opção de layout bruta.
	 *
	 * @param int $page_id ID da página WP.
	 * @return array<string, mixed>
	 */
	public function get_layout_raw( int $page_id ): array {
		if ( $page_id <= 0 ) {
			return array();
		}
		$raw = get_option( 'brasileira_layout_' . $page_id, '' );
		if ( is_array( $raw ) ) {
			return $raw;
		}
		if ( ! is_string( $raw ) || $raw === '' ) {
			return array();
		}
		$decoded = json_decode( $raw, true );
		return is_array( $decoded ) ? $decoded : array();
	}

	/**
	 * Extrai lista de blocos a partir do layout decodificado.
	 *
	 * @param array<string, mixed> $decoded Layout completo.
	 * @return array<int, array<string, mixed>>
	 */
	public function normalize_blocks( array $decoded ): array {
		if ( isset( $decoded['blocks'] ) && is_array( $decoded['blocks'] ) ) {
			return $decoded['blocks'];
		}
		if ( $decoded !== array() && array_keys( $decoded ) === range( 0, count( $decoded ) - 1 ) ) {
			return $decoded;
		}
		return array();
	}

	/**
	 * Blocos visíveis e não expirados, ordenados por position.
	 *
	 * @param int $page_id ID da página.
	 * @return array<int, array<string, mixed>>
	 */
	public function get_blocks_for_page( int $page_id ): array {
		$blocks = $this->normalize_blocks( $this->get_layout_raw( $page_id ) );
		$out    = array();
		foreach ( $blocks as $block ) {
			if ( ! is_array( $block ) ) {
				continue;
			}
			if ( array_key_exists( 'visible', $block ) && ! $block['visible'] ) {
				continue;
			}
			if ( $this->is_block_expired( $block ) ) {
				continue;
			}
			$type = isset( $block['type'] ) ? sanitize_key( (string) $block['type'] ) : '';
			if ( $type === '' || ! $this->registry->is_registered( $type ) ) {
				continue;
			}
			$out[] = $block;
		}
		usort(
			$out,
			static function ( $a, $b ) {
				$pa = isset( $a['position'] ) ? (int) $a['position'] : 0;
				$pb = isset( $b['position'] ) ? (int) $b['position'] : 0;
				return $pa <=> $pb;
			}
		);
		return $out;
	}

	/**
	 * Tipos únicos presentes na página (para enfileirar CSS antes do wp_head).
	 *
	 * @param int $page_id ID da página.
	 * @return string[]
	 */
	public function get_active_block_types( int $page_id ): array {
		$types = array();
		foreach ( $this->get_blocks_for_page( $page_id ) as $block ) {
			$t = isset( $block['type'] ) ? sanitize_key( (string) $block['type'] ) : '';
			if ( $t !== '' ) {
				$types[ $t ] = true;
			}
		}
		return array_keys( $types );
	}

	/**
	 * Renderiza página completa.
	 *
	 * @param int $page_id ID da página.
	 * @return string HTML (sem enqueue — feito em wp_enqueue_scripts).
	 */
	public function render_page( int $page_id ): string {
		$blocks = $this->get_blocks_for_page( $page_id );
		if ( $blocks === array() ) {
			return $this->render_fallback( $page_id );
		}
		$output = '';
		foreach ( $blocks as $block ) {
			$type = sanitize_key( (string) $block['type'] );
			$id   = isset( $block['id'] ) ? (string) $block['id'] : '';
			if ( $id === '' ) {
				$id = 'blk_' . uniqid( '', true );
			}
			$cached = $this->cache->get_block( $id, $type );
			if ( $cached !== false ) {
				$output .= $cached;
				continue;
			}
			$html = $this->render_block( $block );
			$ttl  = $this->registry->get_ttl( $type );
			$this->cache->set_block( $id, $type, $html, $ttl );
			$output .= $html;
		}
		return '<div class="brasileira-layout brasileira-layout--dynamic">' . $output . '</div>';
	}

	/**
	 * Inclui render.php do bloco.
	 *
	 * @param array<string, mixed> $block Dados do bloco.
	 * @return string HTML.
	 */
	private function render_block( array $block ): string {
		$type       = sanitize_key( (string) ( $block['type'] ?? '' ) );
		$subdir     = self::type_to_subdir( $type );
		$render_php = BRASILEIRA_DIR . '/blocks/' . $subdir . '/render.php';
		if ( ! is_readable( $render_php ) ) {
			return '<!-- bloco ' . esc_html( $type ) . ' sem render.php -->';
		}
		ob_start();
		// phpcs:ignore WordPressVIPMinimum.Files.IncludingFile.UsingVariable
		include $render_php;
		return (string) ob_get_clean();
	}

	/**
	 * Fallback quando não há layout JSON.
	 *
	 * @param int $page_id ID da página (para possível uso futuro).
	 * @return string HTML.
	 */
	private function render_fallback( int $page_id ): string {
		$categories = get_categories(
			array(
				'number'       => 5,
				'hide_empty'   => true,
				'orderby'      => 'count',
				'order'        => 'DESC',
			)
		);
		$output = '<div class="layout-fallback layout-fallback--auto" data-page-id="' . esc_attr( (string) $page_id ) . '">';
		foreach ( $categories as $cat ) {
			$posts = get_posts(
				array(
					'cat'            => $cat->term_id,
					'posts_per_page' => 4,
					'post_status'    => 'publish',
					'no_found_rows'  => true,
				)
			);
			if ( $posts === array() ) {
				continue;
			}
			$output .= '<section class="fallback-section section-gap" aria-labelledby="fallback-cat-' . esc_attr( (string) $cat->term_id ) . '">';
			$output .= '<h2 id="fallback-cat-' . esc_attr( (string) $cat->term_id ) . '" class="section-title">' . esc_html( $cat->name ) . '</h2>';
			$output .= '<div class="grid grid-4">';
			foreach ( $posts as $post ) {
				setup_postdata( $post );
				$thumb = get_the_post_thumbnail(
					$post->ID,
					'brasileira-card',
					array(
						'loading' => 'lazy',
						'class'   => 'fallback-card__img',
					)
				);
				$url   = get_permalink( $post );
				$output .= '<article class="fallback-card">';
				$output .= '<a class="fallback-card__link" href="' . esc_url( $url ) . '">';
				$output .= $thumb ? $thumb : '';
				$output .= '<h3 class="fallback-card__title">' . esc_html( get_the_title( $post ) ) . '</h3>';
				$output .= '</a></article>';
			}
			wp_reset_postdata();
			$output .= '</div></section>';
		}
		$output .= '</div>';
		return $output;
	}

	/**
	 * Verifica expiração por timestamp ou minutos desde created_at.
	 *
	 * @param array<string, mixed> $block Bloco.
	 * @return bool
	 */
	private function is_block_expired( array $block ): bool {
		$cfg = isset( $block['config'] ) && is_array( $block['config'] ) ? $block['config'] : array();
		if ( ! empty( $cfg['auto_expire_at'] ) ) {
			$t = strtotime( (string) $cfg['auto_expire_at'] );
			return $t && $t < time();
		}
		if ( ! empty( $cfg['auto_expire_minutes'] ) && ! empty( $cfg['created_at'] ) ) {
			$start = strtotime( (string) $cfg['created_at'] );
			if ( ! $start ) {
				return false;
			}
			$end = $start + ( (int) $cfg['auto_expire_minutes'] * 60 );
			return time() > $end;
		}
		return false;
	}

	/**
	 * Invalida cache de um bloco (delegação).
	 *
	 * @param string $block_id ID do bloco.
	 * @return bool
	 */
	public function flush_block_cache( string $block_id ): bool {
		return $this->cache->flush_block( $block_id );
	}
}
