<?php
/**
 * Bloco: Macrotema
 * Tipo: macrotema
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config  = $block['config'];
$tag_id  = isset( $config['tag_id'] ) ? absint( $config['tag_id'] ) : 0;
$label   = isset( $config['label'] ) ? (string) $config['label'] : '';
$style   = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'highlight_band';
$blk_id  = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';
$icon    = isset( $config['icon'] ) ? (string) $config['icon'] : '🌍';
$temp    = ! empty( $config['temporary'] );
$subhome = isset( $config['subhome_page_id'] ) ? absint( $config['subhome_page_id'] ) : 0;

if ( $tag_id < 1 || $label === '' ) {
	return;
}

$posts = array();
if ( ! empty( $config['posts'] ) && is_array( $config['posts'] ) ) {
	foreach ( $config['posts'] as $pid ) {
		$p = get_post( absint( $pid ) );
		if ( $p && $p->post_status === 'publish' ) {
			$posts[] = $p;
		}
		if ( count( $posts ) >= 4 ) {
			break;
		}
	}
}

if ( empty( $posts ) ) {
	$posts = get_posts(
		array(
			'tag_id'           => $tag_id,
			'posts_per_page'   => 4,
			'post_status'      => 'publish',
			'orderby'          => 'date',
			'order'            => 'DESC',
			'no_found_rows'    => true,
		)
	);
}

if ( empty( $posts ) ) {
	return;
}

$wrap_classes = 'blk-macrotema__band-wrap';
if ( 'highlight_band' === $style ) {
	$wrap_classes .= ' blk-macrotema__band';
}
?>
<section
	class="blk-macrotema blk-macrotema--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="macrotema"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="<?php echo esc_attr( $wrap_classes ); ?>">
		<div class="container">
			<header class="blk-macrotema__header">
				<div class="blk-macrotema__identity">
					<span class="blk-macrotema__icon" aria-hidden="true"><?php echo esc_html( $icon ); ?></span>
					<h2 class="blk-macrotema__label"><?php echo esc_html( $label ); ?></h2>
					<?php if ( $temp ) : ?>
						<span class="blk-macrotema__badge"><?php esc_html_e( 'Em desenvolvimento', 'brasileira-theme' ); ?></span>
					<?php endif; ?>
				</div>
				<?php if ( $subhome > 0 ) : ?>
					<?php
					$sp = get_post( $subhome );
					if ( $sp && $sp->post_status === 'publish' ) :
						?>
					<a class="blk-macrotema__follow" href="<?php echo esc_url( get_permalink( $sp ) ); ?>">
						<?php esc_html_e( 'Acompanhe', 'brasileira-theme' ); ?> →
					</a>
					<?php endif; ?>
				<?php endif; ?>
			</header>

			<div class="blk-macrotema__posts">
				<?php
				foreach ( $posts as $p ) {
					$thumb = get_the_post_thumbnail(
						$p->ID,
						'brasileira-thumb',
						array(
							'class'   => 'blk-macrotema__thumb-img',
							'loading' => 'lazy',
							'alt'     => esc_attr( get_the_title( $p ) ),
						)
					);
					$time = human_time_diff( get_post_time( 'U', false, $p ), current_time( 'timestamp' ) );
					?>
					<article class="blk-macrotema__card">
						<a class="blk-macrotema__card-link" href="<?php echo esc_url( get_permalink( $p ) ); ?>">
							<?php if ( $thumb ) : ?>
								<figure class="blk-macrotema__thumb"><?php echo $thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
							<?php endif; ?>
							<div class="blk-macrotema__card-body">
								<h3 class="blk-macrotema__card-title"><?php echo esc_html( get_the_title( $p ) ); ?></h3>
								<span class="blk-macrotema__meta"><?php echo esc_html( $time ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
							</div>
						</a>
					</article>
					<?php
				}
				?>
			</div>
		</div>
	</div>
</section>
