<?php
/**
 * Bloco: Opinião
 * Tipo: opiniao
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config   = $block['config'];
$post_ids = isset( $config['posts'] ) && is_array( $config['posts'] ) ? array_map( 'absint', $config['posts'] ) : array();
$style    = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'cards_editorial';
$blk_id   = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$post_ids = array_values( array_filter( $post_ids ) );
if ( empty( $post_ids ) ) {
	return;
}

$posts = array();
foreach ( $post_ids as $pid ) {
	$p = get_post( $pid );
	if ( $p && $p->post_status === 'publish' ) {
		$posts[] = $p;
	}
}

if ( empty( $posts ) ) {
	return;
}
?>
<section
	class="blk-opiniao blk-opiniao--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="opiniao"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<header class="blk-opiniao__header">
			<h2 class="blk-opiniao__titulo"><?php esc_html_e( 'Opinião', 'brasileira-theme' ); ?></h2>
		</header>
		<div class="blk-opiniao__grid">
			<?php
			foreach ( $posts as $p ) {
				$author_id = (int) $p->post_author;
				$nome      = get_the_author_meta( 'display_name', $author_id );
				$bio       = get_the_author_meta( 'description', $author_id );
				$bio_short = $bio ? wp_trim_words( wp_strip_all_tags( $bio ), 12, '…' ) : '';
				$avatar    = get_avatar( $author_id, 56, '', esc_attr( $nome ), array( 'class' => 'blk-opiniao__avatar-img' ) );
				$excerpt   = get_the_excerpt( $p );
				if ( $excerpt === '' ) {
					$excerpt = wp_trim_words( wp_strip_all_tags( $p->post_content ), 22, '…' );
				} else {
					$excerpt = wp_trim_words( wp_strip_all_tags( $excerpt ), 22, '…' );
				}
				$time = human_time_diff( get_post_time( 'U', false, $p ), current_time( 'timestamp' ) );
				?>
				<article class="blk-opiniao__card">
					<div class="blk-opiniao__autor-info">
						<?php echo $avatar; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
						<div class="blk-opiniao__autor-text">
							<span class="blk-opiniao__autor-nome"><?php echo esc_html( $nome ); ?></span>
							<?php if ( $bio_short !== '' ) : ?>
								<span class="blk-opiniao__autor-cargo"><?php echo esc_html( $bio_short ); ?></span>
							<?php endif; ?>
						</div>
					</div>
					<a href="<?php echo esc_url( get_permalink( $p ) ); ?>" class="blk-opiniao__link">
						<h3 class="blk-opiniao__titulo-art"><?php echo esc_html( get_the_title( $p ) ); ?></h3>
						<p class="blk-opiniao__excerpt"><?php echo esc_html( $excerpt ); ?></p>
					</a>
					<span class="blk-opiniao__meta"><?php echo esc_html( $time ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
				</article>
				<?php
			}
			?>
		</div>
	</div>
</section>
