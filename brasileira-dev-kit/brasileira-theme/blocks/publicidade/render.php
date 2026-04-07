<?php
/**
 * Bloco: Publicidade (slot GAM)
 * Tipo: publicidade
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$slot   = isset( $config['slot'] ) ? (string) $config['slot'] : '';
$size   = isset( $config['size'] ) ? (string) $config['size'] : '728x90';
$style  = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'leaderboard';
$blk_id = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';
$fb     = isset( $config['fallback'] ) ? (string) $config['fallback'] : '';

if ( $slot === '' ) {
	return;
}

$adm   = new Brasileira_Ad_Manager();
$inner = $adm->render_slot( $slot, $size, $fb );
?>
<div
	class="blk-publicidade blk-publicidade--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="publicidade"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<?php
		// O Ad_Manager já inclui wrapper interno; encapsulamos em container do tema.
		echo $inner; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
		?>
	</div>
</div>
