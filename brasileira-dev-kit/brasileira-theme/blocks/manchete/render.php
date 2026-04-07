<?php
/**
 * Bloco: Manchete (hero)
 * Tipo: manchete
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config        = $block['config'];
$principal_id  = isset( $config['principal'] ) ? absint( $config['principal'] ) : 0;
$style         = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'hero_large';
$blk_id        = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';
$sub_ids       = isset( $config['submanchetes'] ) && is_array( $config['submanchetes'] ) ? array_map( 'absint', $config['submanchetes'] ) : array();
$sub_ids       = array_values( array_filter( $sub_ids ) );

$principal = $principal_id ? get_post( $principal_id ) : null;
if ( ! $principal || $principal->post_status !== 'publish' ) {
	return;
}

/**
 * Renderiza um card compacto de post.
 *
 * @param WP_Post $p Post.
 * @param string  $heading_tag h2 ou h3.
 */
$render_card = static function ( WP_Post $p, string $heading_tag = 'h3' ) : void {
	$thumb = get_the_post_thumbnail(
		$p->ID,
		'brasileira-thumb',
		array(
			'class'   => 'blk-manchete__img-tag',
			'loading' => 'lazy',
			'alt'     => esc_attr( get_the_title( $p ) ),
		)
	);
	$cats  = get_the_category( $p->ID );
	$cat   = ! empty( $cats ) ? $cats[0]->name : '';
	$time  = human_time_diff( get_post_time( 'U', false, $p ), current_time( 'timestamp' ) );
	$url   = get_permalink( $p );
	$title = get_the_title( $p );
	?>
	<article class="blk-manchete__sub">
		<a class="blk-manchete__sub-link" href="<?php echo esc_url( $url ); ?>">
			<?php if ( $thumb ) : ?>
				<figure class="blk-manchete__sub-fig"><?php echo $thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
			<?php endif; ?>
			<div class="blk-manchete__sub-body">
				<?php if ( $cat !== '' ) : ?>
					<span class="blk-manchete__sub-cat"><?php echo esc_html( $cat ); ?></span>
				<?php endif; ?>
				<<?php echo esc_attr( $heading_tag ); ?> class="blk-manchete__sub-title"><?php echo esc_html( $title ); ?></<?php echo esc_attr( $heading_tag ); ?>>
				<span class="blk-manchete__meta"><?php echo esc_html( $time ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
			</div>
		</a>
	</article>
	<?php
};

$principal_thumb = get_the_post_thumbnail(
	$principal->ID,
	'brasileira-hero',
	array(
		'class'   => 'blk-manchete__img-tag',
		'loading' => 'lazy',
		'alt'     => esc_attr( get_the_title( $principal ) ),
	)
);
$p_cats          = get_the_category( $principal->ID );
$p_cat_name      = ! empty( $p_cats ) ? $p_cats[0]->name : '';
$p_excerpt       = get_the_excerpt( $principal );
if ( $p_excerpt === '' ) {
	$p_excerpt = wp_trim_words( wp_strip_all_tags( $principal->post_content ), 28, '…' );
}
$p_time = human_time_diff( get_post_time( 'U', false, $principal ), current_time( 'timestamp' ) );
?>
<section
	class="blk-manchete blk-manchete--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="manchete"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<?php if ( $style === 'hero_split' ) : ?>
			<div class="blk-manchete__grid blk-manchete__grid--split">
				<?php
				$split_posts = array( $principal );
				foreach ( $sub_ids as $sid ) {
					if ( count( $split_posts ) >= 2 ) {
						break;
					}
					if ( ! $sid || (int) $sid === (int) $principal->ID ) {
						continue;
					}
					$sp_obj = get_post( $sid );
					if ( $sp_obj && $sp_obj->post_status === 'publish' ) {
						$split_posts[] = $sp_obj;
					}
				}
				foreach ( $split_posts as $po ) {
					if ( ! ( $po instanceof WP_Post ) || $po->post_status !== 'publish' ) {
						continue;
					}
					$big = get_the_post_thumbnail(
						$po->ID,
						'brasileira-card',
						array(
							'class'   => 'blk-manchete__img-tag',
							'loading' => 'lazy',
							'alt'     => esc_attr( get_the_title( $po ) ),
						)
					);
					$pcats = get_the_category( $po->ID );
					$pct   = ! empty( $pcats ) ? $pcats[0]->name : '';
					?>
					<article class="blk-manchete__split-card">
						<a class="blk-manchete__split-link" href="<?php echo esc_url( get_permalink( $po ) ); ?>">
							<?php if ( $big ) : ?>
								<figure class="blk-manchete__img"><?php echo $big; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
							<?php endif; ?>
							<div class="blk-manchete__content">
								<?php if ( $pct !== '' ) : ?>
									<figcaption class="blk-manchete__category"><?php echo esc_html( $pct ); ?></figcaption>
								<?php endif; ?>
								<h2 class="blk-manchete__title"><?php echo esc_html( get_the_title( $po ) ); ?></h2>
								<p class="blk-manchete__excerpt"><?php echo esc_html( wp_strip_all_tags( get_the_excerpt( $po ) ?: wp_trim_words( $po->post_content, 20 ) ) ); ?></p>
								<span class="blk-manchete__meta"><?php echo esc_html( human_time_diff( get_post_time( 'U', false, $po ), current_time( 'timestamp' ) ) ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
							</div>
						</a>
					</article>
					<?php
				}
				?>
			</div>
		<?php elseif ( $style === 'hero_video' ) : ?>
			<div class="blk-manchete__grid blk-manchete__grid--video">
				<article class="blk-manchete__principal blk-manchete__principal--video">
					<a class="blk-manchete__principal-link" href="<?php echo esc_url( get_permalink( $principal ) ); ?>">
						<div class="blk-manchete__video-frame">
							<?php if ( $principal_thumb ) : ?>
								<figure class="blk-manchete__img"><?php echo $principal_thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
							<?php endif; ?>
							<span class="blk-manchete__play" aria-hidden="true"></span>
						</div>
						<div class="blk-manchete__content">
							<?php if ( $p_cat_name !== '' ) : ?>
								<span class="blk-manchete__category"><?php echo esc_html( $p_cat_name ); ?></span>
							<?php endif; ?>
							<h1 class="blk-manchete__title"><?php echo esc_html( get_the_title( $principal ) ); ?></h1>
							<p class="blk-manchete__excerpt"><?php echo esc_html( wp_strip_all_tags( $p_excerpt ) ); ?></p>
						</div>
					</a>
				</article>
				<div class="blk-manchete__subs">
					<?php
					foreach ( array_slice( $sub_ids, 0, 3 ) as $sid ) {
						$sp = get_post( $sid );
						if ( $sp && $sp->post_status === 'publish' ) {
							$render_card( $sp, 'h3' );
						}
					}
					?>
				</div>
			</div>
		<?php else : ?>
			<div class="blk-manchete__grid blk-manchete__grid--large">
				<article class="blk-manchete__principal">
					<a class="blk-manchete__principal-link" href="<?php echo esc_url( get_permalink( $principal ) ); ?>">
						<?php if ( $principal_thumb ) : ?>
							<figure class="blk-manchete__img"><?php echo $principal_thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
						<?php endif; ?>
						<div class="blk-manchete__content">
							<?php if ( $p_cat_name !== '' ) : ?>
								<figcaption class="blk-manchete__category"><?php echo esc_html( $p_cat_name ); ?></figcaption>
							<?php endif; ?>
							<h1 class="blk-manchete__title"><?php echo esc_html( get_the_title( $principal ) ); ?></h1>
							<p class="blk-manchete__excerpt"><?php echo esc_html( wp_strip_all_tags( $p_excerpt ) ); ?></p>
							<span class="blk-manchete__meta"><?php echo esc_html( $p_time ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
						</div>
					</a>
				</article>
				<div class="blk-manchete__subs">
					<?php
					foreach ( array_slice( $sub_ids, 0, 3 ) as $sid ) {
						$sp = get_post( $sid );
						if ( $sp && $sp->post_status === 'publish' ) {
							$render_card( $sp, 'h3' );
						}
					}
					?>
				</div>
			</div>
		<?php endif; ?>
	</div>
</section>
