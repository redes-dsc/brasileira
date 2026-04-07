<?php
/**
 * Bloco: HTML personalizado (KSES)
 * Tipo: custom
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$html   = isset( $config['html'] ) ? (string) $config['html'] : '';
if ( $html === '' ) {
	return;
}

$bid = isset( $block['id'] ) ? esc_attr( (string) $block['id'] ) : '';

$extra = isset( $config['css_class'] ) ? sanitize_html_class( (string) $config['css_class'] ) : '';
$tag   = isset( $config['wrapper_tag'] ) ? sanitize_key( (string) $config['wrapper_tag'] ) : 'section';
$allow = array( 'section', 'div', 'article', 'aside' );
if ( ! in_array( $tag, $allow, true ) ) {
	$tag = 'section';
}

$class = 'blk-custom';
if ( $extra !== '' ) {
	$class .= ' ' . $extra;
}
?>
<<?php echo esc_attr( $tag ); ?> class="<?php echo esc_attr( $class ); ?>" data-block-id="<?php echo esc_attr( $bid ); ?>" data-block-type="custom">
	<?php echo wp_kses_post( $html ); ?>
</<?php echo esc_attr( $tag ); ?>>
