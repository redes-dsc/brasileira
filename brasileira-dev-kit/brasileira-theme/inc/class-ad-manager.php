<?php
/**
 * Gerenciador de slots de publicidade (Google Ad Manager / GPT).
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

/**
 * Classe Brasileira_Ad_Manager
 */
class Brasileira_Ad_Manager {

	/**
	 * Tamanhos IAB comuns.
	 */
	public const SIZES = array(
		'728x90'  => array( 'width' => 728, 'height' => 90, 'label' => 'Leaderboard' ),
		'300x250' => array( 'width' => 300, 'height' => 250, 'label' => 'Retângulo Médio' ),
		'970x250' => array( 'width' => 970, 'height' => 250, 'label' => 'Billboard' ),
		'320x50'  => array( 'width' => 320, 'height' => 50, 'label' => 'Mobile Banner' ),
	);

	/**
	 * Renderiza container de slot de anúncio.
	 *
	 * @param string $slot     ID do ad unit.
	 * @param string $size     Chave de tamanho (ex.: 728x90).
	 * @param string $fallback URL de imagem de fallback (opcional).
	 * @return string HTML seguro.
	 */
	public function render_slot( string $slot, string $size, string $fallback = '' ): string {
		$size_data = self::SIZES[ $size ] ?? array( 'width' => 300, 'height' => 250, 'label' => 'Custom' );
		$slot_id   = 'ad-' . sanitize_html_class( str_replace( array( '/', ' ' ), '-', $slot ) ) . '-' . wp_rand( 1000, 9999 );

		$html  = '<div class="blk-publicidade__wrapper">';
		$html .= '<span class="blk-publicidade__label">' . esc_html__( 'PUBLICIDADE', 'brasileira-theme' ) . '</span>';
		$html .= sprintf(
			'<div id="%1$s" class="ad-container" data-ad-slot="%2$s" data-ad-size="%3$s" style="min-height:%4$dpx;min-width:%5$dpx;">',
			esc_attr( $slot_id ),
			esc_attr( $slot ),
			esc_attr( $size ),
			(int) $size_data['height'],
			(int) $size_data['width']
		);

		if ( $fallback !== '' ) {
			$html .= '<noscript><img src="' . esc_url( $fallback ) . '" alt="" loading="lazy" width="' . (int) $size_data['width'] . '" height="' . (int) $size_data['height'] . '" /></noscript>';
		}

		$html .= '</div></div>';
		return $html;
	}
}
