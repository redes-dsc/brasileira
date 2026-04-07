<?php
/**
 * Bloco: Breaking News
 * Tipo: breaking
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$post_id = isset( $config['post_id'] ) ? absint( $config['post_id'] ) : 0;
if ( $post_id < 1 ) {
	return;
}

$post = get_post( $post_id );
if ( ! $post || $post->post_status !== 'publish' ) {
	return;
}

$style      = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'fullwidth_red';
$label      = isset( $config['label'] ) ? (string) $config['label'] : __( 'URGENTE', 'brasileira-theme' );
$blk_id     = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';
$is_live    = ( strtoupper( trim( $label ) ) === 'AO VIVO' );
$live_class = $is_live ? ' blk-breaking--live' : '';

$title   = get_the_title( $post );
$url     = get_permalink( $post );
$excerpt = get_the_excerpt( $post );
if ( $excerpt === '' ) {
	$excerpt = wp_trim_words( wp_strip_all_tags( $post->post_content ), 24, '…' );
}
$time_ago = human_time_diff( get_post_time( 'U', false, $post ), current_time( 'timestamp' ) );

$refresh_sec = 60;
if ( ! empty( $config['auto_expire_minutes'] ) ) {
	$refresh_sec = max( 30, (int) $config['auto_expire_minutes'] * 60 );
}

$data_refresh = '';
if ( ! empty( $config['auto_expire_minutes'] ) || ! empty( $config['auto_expire_at'] ) ) {
	$data_refresh = ' data-auto-refresh="' . esc_attr( (string) $refresh_sec ) . '"';
}
?>
<section
	class="blk-breaking blk-breaking--<?php echo esc_attr( $style ); ?><?php echo esc_attr( $live_class ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="breaking"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
	<?php
	if ( $data_refresh !== '' ) {
		echo $data_refresh; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
	}
	?>
>
	<div class="container">
		<div class="blk-breaking__inner">
			<span class="blk-breaking__label">
				<?php if ( $is_live ) : ?>
					<span class="blk-breaking__dot" aria-hidden="true"></span>
				<?php endif; ?>
				<?php echo esc_html( $label ); ?>
			</span>
			<a href="<?php echo esc_url( $url ); ?>" class="blk-breaking__link">
				<h2 class="blk-breaking__title"><?php echo esc_html( $title ); ?></h2>
				<?php if ( $excerpt !== '' ) : ?>
					<p class="blk-breaking__excerpt"><?php echo esc_html( wp_strip_all_tags( $excerpt ) ); ?></p>
				<?php endif; ?>
			</a>
			<span class="blk-breaking__time"><?php echo esc_html( $time_ago ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
		</div>
	</div>
</section>
