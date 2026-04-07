<?php
/**
 * Bloco: publicidade — container de slot (Ad Manager).
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

$b        = isset( $block ) && is_array( $block ) ? $block : array();
$cfg      = isset( $b['config'] ) && is_array( $b['config'] ) ? $b['config'] : array();
$slot     = isset( $cfg['slot'] ) ? (string) $cfg['slot'] : '';
$size     = isset( $cfg['size'] ) ? (string) $cfg['size'] : '300x250';
$fallback = isset( $cfg['fallback'] ) ? (string) $cfg['fallback'] : '';
$bid      = isset( $b['id'] ) ? esc_attr( (string) $b['id'] ) : '';

$inner = '';
if ( $slot !== '' ) {
	$adm   = new Brasileira_Ad_Manager();
	$inner = $adm->render_slot( $slot, $size, $fallback );
}
?>
<section class="blk-publicidade" data-block-id="<?php echo $bid; ?>">
	<?php echo $inner; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- HTML já escapado em Ad_Manager::render_slot ?>
</section>
