<?php
/**
 * Bloco: Vídeo
 * Tipo: video
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$style  = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'featured_player';
$blk_id = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$featured_id = isset( $config['featured_post_id'] ) ? absint( $config['featured_post_id'] ) : 0;
$playlist    = isset( $config['playlist'] ) && is_array( $config['playlist'] ) ? array_map( 'absint', $config['playlist'] ) : array();

if ( ! empty( $config['videos'] ) && is_array( $config['videos'] ) ) {
	foreach ( $config['videos'] as $row ) {
		if ( ! is_array( $row ) ) {
			continue;
		}
		if ( ! empty( $row['post_id'] ) ) {
			$pid = absint( $row['post_id'] );
			if ( $featured_id < 1 ) {
				$featured_id = $pid;
			} else {
				$playlist[] = $pid;
			}
		}
	}
}

if ( $featured_id < 1 && ! empty( $playlist[0] ) ) {
	$featured_id = $playlist[0];
	$playlist      = array_slice( $playlist, 1 );
}

$main = $featured_id ? get_post( $featured_id ) : null;
if ( ! $main || $main->post_status !== 'publish' ) {
	return;
}

$embed_html = '';
if ( function_exists( 'parse_blocks' ) ) {
	$blocks = parse_blocks( $main->post_content );
	foreach ( $blocks as $b ) {
		if ( ! empty( $b['blockName'] ) && 'core/embed' === $b['blockName'] && ! empty( $b['attrs']['url'] ) ) {
			$embed_html = wp_oembed_get( $b['attrs']['url'] );
			if ( $embed_html ) {
				break;
			}
		}
	}
}
if ( $embed_html === '' && preg_match( '/https?:\/\/[^\s"<]+/', $main->post_content, $m ) ) {
	$embed_html = wp_oembed_get( $m[0] );
}

$thumb = get_the_post_thumbnail(
	$main->ID,
	'brasileira-hero',
	array(
		'class'   => 'blk-video__poster-img',
		'loading' => 'lazy',
		'alt'     => esc_attr( get_the_title( $main ) ),
	)
);

$side_posts = array();
foreach ( $playlist as $pid ) {
	if ( $pid === $main->ID ) {
		continue;
	}
	$p = get_post( $pid );
	if ( $p && $p->post_status === 'publish' ) {
		$side_posts[] = $p;
	}
}
?>
<section
	class="blk-video blk-video--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="video"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<header class="blk-video__header">
			<h2 class="blk-video__titulo"><?php esc_html_e( 'Vídeos', 'brasileira-theme' ); ?></h2>
		</header>
		<?php if ( 'grid_thumbnails' !== $style ) : ?>
		<div class="blk-video__layout">
			<div class="blk-video__main">
				<div class="blk-video__player ratio-16x9">
					<?php if ( $embed_html ) : ?>
						<div class="blk-video__embed">
							<?php echo $embed_html; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- oEmbed ?>
						</div>
					<?php elseif ( $thumb ) : ?>
						<a class="blk-video__poster" href="<?php echo esc_url( get_permalink( $main ) ); ?>">
							<?php echo $thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
							<span class="blk-video__play-btn" aria-hidden="true"></span>
						</a>
					<?php else : ?>
						<a class="blk-video__link-fallback" href="<?php echo esc_url( get_permalink( $main ) ); ?>"><?php echo esc_html( get_the_title( $main ) ); ?></a>
					<?php endif; ?>
				</div>
			</div>
			<?php if ( ! empty( $side_posts ) && 'grid_thumbnails' !== $style ) : ?>
				<ul class="blk-video__playlist">
					<?php
					foreach ( $side_posts as $sp ) {
						$st = get_the_post_thumbnail(
							$sp->ID,
							'brasileira-thumb',
							array(
								'class'   => 'blk-video__pl-thumb',
								'loading' => 'lazy',
								'alt'     => esc_attr( get_the_title( $sp ) ),
							)
						);
						?>
						<li class="blk-video__pl-item">
							<a class="blk-video__pl-link" href="<?php echo esc_url( get_permalink( $sp ) ); ?>" data-embed-url="">
								<?php echo $st ? $st : ''; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
								<span class="blk-video__pl-title"><?php echo esc_html( get_the_title( $sp ) ); ?></span>
							</a>
						</li>
						<?php
					}
					?>
				</ul>
			<?php endif; ?>
		</div>
		<?php endif; ?>
		<?php if ( 'grid_thumbnails' === $style ) : ?>
			<div class="blk-video__grid">
				<?php
				$grid_ids = array_merge( array( $main->ID ), wp_list_pluck( $side_posts, 'ID' ) );
				$grid_ids = array_unique( array_filter( array_map( 'absint', $grid_ids ) ) );
				foreach ( $grid_ids as $gid ) {
					$gp = get_post( $gid );
					if ( ! $gp || $gp->post_status !== 'publish' ) {
						continue;
					}
					$gt = get_the_post_thumbnail(
						$gp->ID,
						'brasileira-card',
						array(
							'class'   => 'blk-video__grid-img',
							'loading' => 'lazy',
							'alt'     => esc_attr( get_the_title( $gp ) ),
						)
					);
					?>
					<article class="blk-video__grid-card">
						<a class="blk-video__grid-link" href="<?php echo esc_url( get_permalink( $gp ) ); ?>">
							<?php echo $gt ? $gt : ''; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
							<h3 class="blk-video__grid-title"><?php echo esc_html( get_the_title( $gp ) ); ?></h3>
						</a>
					</article>
					<?php
				}
				?>
			</div>
		<?php endif; ?>
	</div>
</section>
