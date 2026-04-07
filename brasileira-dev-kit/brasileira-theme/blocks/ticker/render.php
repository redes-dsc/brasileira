<?php
/**
 * Bloco editorial — marcação mínima (UI completa no Stream C).
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

$b    = isset( $block ) && is_array( $block ) ? $block : array();
$bid  = isset( $b['id'] ) ? esc_attr( (string) $b['id'] ) : '';
$type = isset( $b['type'] ) ? sanitize_key( (string) $b['type'] ) : 'block';
$class = 'blk-' . esc_attr( str_replace( '_', '-', $type ) );
?>
<section class="<?php echo $class; ?>" data-block-id="<?php echo $bid; ?>" data-block-type="<?php echo esc_attr( $type ); ?>" aria-label="<?php echo esc_attr( $type ); ?>"></section>

