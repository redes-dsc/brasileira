<?php
/**
 * Bloco: Últimas notícias
 * Tipo: ultimas
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$count  = isset( $config['count'] ) ? max( 1, absint( $config['count'] ) ) : 10;
$style  = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'feed_list';
$blk_id = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$refresh = isset( $config['auto_refresh_seconds'] ) ? absint( $config['auto_refresh_seconds'] ) : 0;

$posts = get_posts(
	array(
		'posts_per_page' => $count,
		'post_status'    => 'publish',
		'orderby'        => 'date',
		'order'          => 'DESC',
		'no_found_rows'  => true,
	)
);

if ( empty( $posts ) ) {
	return;
}

$data_refresh = ( $refresh > 0 ) ? ' data-auto-refresh="' . esc_attr( (string) $refresh ) . '"' : '';
?>
<section
	class="blk-ultimas blk-ultimas--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="ultimas"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
	<?php echo $data_refresh ? $data_refresh : ''; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
>
	<div class="container">
		<header class="blk-ultimas__header">
			<h2 class="blk-ultimas__titulo"><?php esc_html_e( 'Últimas', 'brasileira-theme' ); ?></h2>
			<span class="blk-ultimas__live-dot" aria-hidden="true"></span>
		</header>

		<?php if ( 'feed_cards' === $style ) : ?>
			<div class="blk-ultimas__cards">
				<?php
				foreach ( $posts as $p ) {
					$thumb = get_the_post_thumbnail(
						$p->ID,
						'brasileira-thumb',
						array(
							'class'   => 'blk-ultimas__card-img',
							'loading' => 'lazy',
							'alt'     => esc_attr( get_the_title( $p ) ),
						)
					);
					$cats = get_the_category( $p->ID );
					$cat  = ! empty( $cats ) ? $cats[0]->name : '';
					$time = human_time_diff( get_post_time( 'U', false, $p ), current_time( 'timestamp' ) );
					?>
					<article class="blk-ultimas__card">
						<a class="blk-ultimas__card-link" href="<?php echo esc_url( get_permalink( $p ) ); ?>">
							<?php if ( $thumb ) : ?>
								<figure class="blk-ultimas__card-fig"><?php echo $thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
							<?php endif; ?>
							<div class="blk-ultimas__card-body">
								<?php if ( $cat !== '' ) : ?>
									<span class="blk-ultimas__cat"><?php echo esc_html( $cat ); ?></span>
								<?php endif; ?>
								<h3 class="blk-ultimas__card-title"><?php echo esc_html( get_the_title( $p ) ); ?></h3>
								<time class="blk-ultimas__tempo" datetime="<?php echo esc_attr( get_the_date( 'c', $p ) ); ?>"><?php echo esc_html( $time ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></time>
							</div>
						</a>
					</article>
					<?php
				}
				?>
			</div>
		<?php else : ?>
			<ol class="blk-ultimas__lista">
				<?php
				foreach ( $posts as $p ) {
					$cats = get_the_category( $p->ID );
					$cat  = ! empty( $cats ) ? $cats[0]->name : '';
					$time = human_time_diff( get_post_time( 'U', false, $p ), current_time( 'timestamp' ) );
					?>
					<li class="blk-ultimas__item">
						<time class="blk-ultimas__tempo" datetime="<?php echo esc_attr( get_the_date( 'c', $p ) ); ?>"><?php echo esc_html( $time ); ?></time>
						<?php if ( $cat !== '' ) : ?>
							<span class="blk-ultimas__cat"><?php echo esc_html( $cat ); ?></span>
						<?php endif; ?>
						<a href="<?php echo esc_url( get_permalink( $p ) ); ?>" class="blk-ultimas__titulo-link"><?php echo esc_html( get_the_title( $p ) ); ?></a>
					</li>
					<?php
				}
				?>
			</ol>
		<?php endif; ?>
	</div>
</section>
