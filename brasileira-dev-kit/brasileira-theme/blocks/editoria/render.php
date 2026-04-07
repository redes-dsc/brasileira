<?php
/**
 * Bloco: Editoria (categoria)
 * Tipo: editoria
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config      = $block['config'];
$category_id = isset( $config['category_id'] ) ? absint( $config['category_id'] ) : 0;
$label       = isset( $config['label'] ) ? (string) $config['label'] : '';
$style       = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'grid_3';
$blk_id      = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

if ( $category_id < 1 || $label === '' ) {
	return;
}

$limit = match ( $style ) {
	'grid_3' => 3,
	'grid_4_sidebar' => 3,
	'grid_5' => 5,
	'grid_6_mosaic' => 6,
	'list_compact' => 8,
	default => 3,
};

$posts = array();
if ( ! empty( $config['posts'] ) && is_array( $config['posts'] ) ) {
	foreach ( $config['posts'] as $pid ) {
		$p = get_post( absint( $pid ) );
		if ( $p && $p->post_status === 'publish' ) {
			$posts[] = $p;
		}
		if ( count( $posts ) >= $limit ) {
			break;
		}
	}
} else {
	$posts = get_posts(
		array(
			'cat'              => $category_id,
			'posts_per_page'   => $limit,
			'post_status'      => 'publish',
			'orderby'          => 'date',
			'order'            => 'DESC',
			'no_found_rows'    => true,
			'suppress_filters' => false,
		)
	);
}

if ( empty( $posts ) ) {
	return;
}

$show_more = array_key_exists( 'show_more_link', $config ) ? (bool) $config['show_more_link'] : true;
$more_url  = isset( $config['more_link_url'] ) && $config['more_link_url'] !== ''
	? (string) $config['more_link_url']
	: get_category_link( $category_id );

$sidebar_widget = isset( $config['sidebar_widget'] ) ? sanitize_key( (string) $config['sidebar_widget'] ) : '';
$has_sidebar    = ( $style === 'grid_4_sidebar' && $sidebar_widget === 'cotacoes' && is_active_sidebar( 'sidebar-cotacoes' ) );

/**
 * Card padrão.
 *
 * @param WP_Post $p    Post.
 * @param string  $mod  Modificador BEM.
 */
$render_card = static function ( WP_Post $p, string $mod = '' ) : void {
	$thumb = get_the_post_thumbnail(
		$p->ID,
		'brasileira-card',
		array(
			'class'   => 'blk-editoria__card-img-el',
			'loading' => 'lazy',
			'alt'     => esc_attr( get_the_title( $p ) ),
		)
	);
	$cats  = get_the_category( $p->ID );
	$cat   = ! empty( $cats ) ? $cats[0]->name : '';
	$time  = human_time_diff( get_post_time( 'U', false, $p ), current_time( 'timestamp' ) );
	$mod_safe  = $mod !== '' ? sanitize_html_class( (string) $mod ) : '';
	$mod_class = $mod_safe !== '' ? ' blk-editoria__card--' . $mod_safe : '';
	?>
	<article class="blk-editoria__card<?php echo $mod_class; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>">
		<a class="blk-editoria__card-link" href="<?php echo esc_url( get_permalink( $p ) ); ?>">
			<?php if ( $thumb ) : ?>
				<figure class="blk-editoria__card-figure"><?php echo $thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
			<?php endif; ?>
			<div class="blk-editoria__card-content">
				<?php if ( $cat !== '' ) : ?>
					<span class="blk-editoria__card-cat"><?php echo esc_html( $cat ); ?></span>
				<?php endif; ?>
				<h3 class="blk-editoria__card-title"><?php echo esc_html( get_the_title( $p ) ); ?></h3>
				<span class="blk-editoria__card-meta"><?php echo esc_html( $time ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
			</div>
		</a>
	</article>
	<?php
};

?>
<section
	class="blk-editoria blk-editoria--<?php echo esc_attr( $style ); ?><?php echo $has_sidebar ? ' blk-editoria--with-sidebar' : ''; ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="editoria"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<header class="blk-editoria__header">
			<h2 class="blk-editoria__label">
				<span class="blk-editoria__label-bar" aria-hidden="true"></span>
				<?php echo esc_html( $label ); ?>
			</h2>
			<?php if ( $show_more && $more_url ) : ?>
				<a class="blk-editoria__more" href="<?php echo esc_url( $more_url ); ?>"><?php esc_html_e( 'Ver mais', 'brasileira-theme' ); ?> →</a>
			<?php endif; ?>
		</header>

		<?php if ( $has_sidebar ) : ?>
		<div class="blk-editoria__layout-with-sidebar">
		<?php endif; ?>

			<?php if ( $style === 'list_compact' ) : ?>
				<ul class="blk-editoria__list">
					<?php
					foreach ( $posts as $p ) {
						$thumb = get_the_post_thumbnail(
							$p->ID,
							'brasileira-thumb',
							array(
								'class'   => 'blk-editoria__list-img',
								'loading' => 'lazy',
								'alt'     => esc_attr( get_the_title( $p ) ),
							)
						);
						$cats = get_the_category( $p->ID );
						$cat  = ! empty( $cats ) ? $cats[0]->name : '';
						$time = human_time_diff( get_post_time( 'U', false, $p ), current_time( 'timestamp' ) );
						?>
						<li class="blk-editoria__list-item">
							<a class="blk-editoria__list-link" href="<?php echo esc_url( get_permalink( $p ) ); ?>">
								<?php if ( $thumb ) : ?>
									<span class="blk-editoria__list-thumb"><?php echo $thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></span>
								<?php endif; ?>
								<span class="blk-editoria__list-body">
									<?php if ( $cat !== '' ) : ?>
										<span class="blk-editoria__card-cat"><?php echo esc_html( $cat ); ?></span>
									<?php endif; ?>
									<span class="blk-editoria__list-title"><?php echo esc_html( get_the_title( $p ) ); ?></span>
									<span class="blk-editoria__card-meta"><?php echo esc_html( $time ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
								</span>
							</a>
						</li>
						<?php
					}
					?>
				</ul>
			<?php else : ?>
				<div class="blk-editoria__grid">
					<?php
					if ( $style === 'grid_5' ) {
						$render_card( $posts[0], 'hero' );
						foreach ( array_slice( $posts, 1 ) as $p ) {
							$render_card( $p, 'small' );
						}
					} elseif ( $style === 'grid_6_mosaic' ) {
						foreach ( $posts as $i => $p ) {
							$mod = ( 0 === $i ) ? 'mosaic-hero' : 'mosaic-cell';
							$render_card( $p, $mod );
						}
					} else {
						foreach ( $posts as $p ) {
							$render_card( $p );
						}
					}
					?>
				</div>
			<?php endif; ?>

		<?php if ( $has_sidebar ) : ?>
			<aside class="blk-editoria__sidebar" aria-label="<?php echo esc_attr__( 'Cotações', 'brasileira-theme' ); ?>">
				<?php dynamic_sidebar( 'sidebar-cotacoes' ); ?>
			</aside>
		</div>
		<?php endif; ?>
	</div>
</section>
