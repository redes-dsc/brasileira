<?php
/**
 * Gerenciador de cache de fragmentos HTML dos blocos editoriais.
 * Usa a Object Cache API do WordPress (Redis/Memcached quando disponível).
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

/**
 * Classe Brasileira_Cache_Manager
 */
class Brasileira_Cache_Manager {

	/**
	 * Grupo de cache no Object Cache.
	 */
	public const CACHE_GROUP = 'brasileira_blocks';

	/**
	 * Recupera HTML cacheado de um bloco.
	 *
	 * @param string $block_id ID do bloco no layout JSON.
	 * @param string $type     Tipo do bloco.
	 * @return string|false
	 */
	public function get_block( string $block_id, string $type ): string|false {
		$key = $this->make_key( $block_id, $type );
		$val = wp_cache_get( $key, self::CACHE_GROUP );
		return is_string( $val ) ? $val : false;
	}

	/**
	 * Armazena HTML de um bloco no cache.
	 *
	 * @param string $block_id ID do bloco.
	 * @param string $type     Tipo.
	 * @param string $html     HTML renderizado.
	 * @param int    $ttl      Segundos (0 = não cachear).
	 * @return bool
	 */
	public function set_block( string $block_id, string $type, string $html, int $ttl ): bool {
		if ( $ttl <= 0 ) {
			return false;
		}
		$key = $this->make_key( $block_id, $type );
		return wp_cache_set( $key, $html, self::CACHE_GROUP, $ttl );
	}

	/**
	 * Invalida cache de um bloco (todos os tipos conhecidos).
	 *
	 * @param string $block_id ID do bloco.
	 * @return bool
	 */
	public function flush_block( string $block_id ): bool {
		$registry = new Brasileira_Block_Registry();
		$types    = array_keys( $registry->get_all() );
		$ok       = true;
		foreach ( $types as $type ) {
			$key = $this->make_key( $block_id, $type );
			if ( ! wp_cache_delete( $key, self::CACHE_GROUP ) ) {
				$ok = false;
			}
		}
		return $ok;
	}

	/**
	 * Invalida caches de blocos afetados por alteração de post.
	 *
	 * @param int $post_id ID do post.
	 * @return void
	 */
	public static function flush_post_blocks( int $post_id ): void {
		if ( $post_id <= 0 ) {
			return;
		}
		if ( function_exists( 'wp_cache_delete_group' ) ) {
			wp_cache_delete_group( self::CACHE_GROUP );
			return;
		}
		/**
		 * Sem `wp_cache_delete_group`, limpeza por grupo depende do backend.
		 * Temas/plugins de object cache (Redis) costumam implementar a função.
		 */
		do_action( 'brasileira_flush_block_cache', $post_id );
	}

	/**
	 * Monta chave de cache alinhada ao contrato (tipo + id).
	 *
	 * @param string $block_id ID do bloco.
	 * @param string $type     Tipo.
	 * @return string
	 */
	private function make_key( string $block_id, string $type ): string {
		return 'block_' . sanitize_key( $type ) . '_' . md5( $block_id );
	}
}
