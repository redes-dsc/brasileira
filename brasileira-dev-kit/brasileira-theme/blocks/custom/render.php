<?php
/**
 * Bloco: custom — HTML controlado pelo curador (KSES).
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

$b    = isset( $block ) && is_array( $block ) ? $block : array();
$cfg  = isset( $b['config'] ) && is_array( $b['config'] ) ? $b['config'] : array();
$html = isset( $cfg['html'] ) ? (string) $cfg['html'] : '';
$bid  = isset( $b['id'] ) ? esc_attr( (string) $b['id'] ) : '';

$extra = isset( $cfg['css_class'] ) ? sanitize_html_class( (string) $cfg['css_class'] ) : '';
$tag   = isset( $cfg['wrapper_tag'] ) ? sanitize_key( (string) $cfg['wrapper_tag'] ) : 'section';
$allow = array( 'section', 'div', 'article', 'aside' );
if ( ! in_array( $tag, $allow, true ) ) {
	$tag = 'section';
}

$class = 'blk-custom';
if ( $extra !== '' ) {
	$class .= ' ' . $extra;
}
?>
<<?php echo esc_attr( $tag ); ?> class="<?php echo esc_attr( $class ); ?>" data-block-id="<?php echo $bid; ?>">
	<?php echo wp_kses_post( $html ); ?>
</<?php echo esc_attr( $tag ); ?>>
