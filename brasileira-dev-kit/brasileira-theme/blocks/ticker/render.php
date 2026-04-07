<?php
/**
 * Bloco: Ticker financeiro / mercado
 * Tipo: ticker
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$ativos = array();
if ( ! empty( $config['sources'] ) && is_array( $config['sources'] ) ) {
	$ativos = array_map( 'sanitize_text_field', $config['sources'] );
} elseif ( ! empty( $config['ativos'] ) && is_array( $config['ativos'] ) ) {
	$ativos = array_map( 'sanitize_text_field', $config['ativos'] );
}
$style   = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'bar_dark';
$blk_id  = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';
$refresh = isset( $config['auto_refresh_seconds'] ) ? absint( $config['auto_refresh_seconds'] ) : ( isset( $config['refresh_seconds'] ) ? absint( $config['refresh_seconds'] ) : 60 );

if ( empty( $ativos ) ) {
	$ativos = array( 'USD', 'EUR', 'IBOV', 'BTC' );
}

$data_ativos = implode( ',', $ativos );
?>
<section
	class="blk-ticker blk-ticker--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="ticker"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
	data-ativos="<?php echo esc_attr( $data_ativos ); ?>"
	<?php if ( $refresh > 0 ) : ?>
		data-refresh="<?php echo esc_attr( (string) $refresh ); ?>"
	<?php endif; ?>
>
	<div class="container">
		<div class="blk-ticker__track" aria-live="polite">
			<?php
			// Placeholder até integração com API — valores fictícios para layout.
			foreach ( array_merge( $ativos, $ativos ) as $sym ) {
				?>
				<span class="blk-ticker__item">
					<span class="blk-ticker__sym"><?php echo esc_html( $sym ); ?></span>
					<span class="blk-ticker__val">—</span>
					<span class="blk-ticker__chg blk-ticker__alta">0,00%</span>
				</span>
				<?php
			}
			?>
		</div>
	</div>
</section>
