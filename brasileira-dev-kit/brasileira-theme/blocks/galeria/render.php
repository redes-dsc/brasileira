<?php
/**
 * Bloco: Galeria
 * Tipo: galeria
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$style  = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'masonry_grid';
$blk_id = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$title = isset( $config['caption'] ) ? (string) $config['caption'] : __( 'Galeria', 'brasileira-theme' );

$items = array();

if ( ! empty( $config['images'] ) && is_array( $config['images'] ) ) {
	foreach ( $config['images'] as $row ) {
		if ( ! is_array( $row ) ) {
			continue;
		}
		$aid = isset( $row['attachment_id'] ) ? absint( $row['attachment_id'] ) : 0;
		$cap = isset( $row['caption'] ) ? (string) $row['caption'] : '';
		if ( $aid ) {
			$items[] = array(
				'attachment_id' => $aid,
				'caption'       => $cap,
				'link'          => '',
			);
		}
	}
}

if ( empty( $items ) && ! empty( $config['posts'] ) && is_array( $config['posts'] ) ) {
	foreach ( $config['posts'] as $pid ) {
		$pid = absint( $pid );
		$p   = get_post( $pid );
		if ( ! $p || $p->post_status !== 'publish' ) {
			continue;
		}
		$thumb_id = get_post_thumbnail_id( $p->ID );
		if ( $thumb_id ) {
			$items[] = array(
				'attachment_id' => $thumb_id,
				'caption'       => get_the_title( $p ),
				'link'          => get_permalink( $p ),
			);
		}
	}
}

if ( empty( $items ) ) {
	return;
}

$lightbox = ! empty( $config['lightbox'] );
?>
<section
	class="blk-galeria blk-galeria--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="galeria"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<header class="blk-galeria__header">
			<h2 class="blk-galeria__title"><?php echo esc_html( $title ); ?></h2>
		</header>
		<div class="blk-galeria__grid" role="list">
			<?php
			foreach ( $items as $item ) {
				$aid = $item['attachment_id'];
				$img = wp_get_attachment_image(
					$aid,
					'brasileira-card',
					false,
					array(
						'class'   => 'blk-galeria__img',
						'loading' => 'lazy',
						'alt'     => esc_attr( wp_strip_all_tags( $item['caption'] ?? '' ) ),
					)
				);
				if ( ! $img ) {
					continue;
				}
				$full = wp_get_attachment_image_url( $aid, 'full' );
				$cap  = $item['caption'] ?? '';
				$link = isset( $item['link'] ) ? (string) $item['link'] : '';
				$wrap = $link !== '' ? 'a' : 'div';
				?>
				<figure class="blk-galeria__cell" role="listitem">
					<?php if ( $wrap === 'a' ) : ?>
						<a class="blk-galeria__link" href="<?php echo esc_url( $link ); ?>">
							<?php echo $img; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
						</a>
					<?php else : ?>
						<?php if ( $lightbox && $full ) : ?>
							<a class="blk-galeria__link" href="<?php echo esc_url( $full ); ?>" data-lightbox="1">
								<?php echo $img; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
							</a>
						<?php else : ?>
							<?php echo $img; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
						<?php endif; ?>
					<?php endif; ?>
					<?php if ( $cap !== '' && $wrap !== 'a' ) : ?>
						<figcaption class="blk-galeria__caption"><?php echo esc_html( $cap ); ?></figcaption>
					<?php endif; ?>
				</figure>
				<?php
			}
			?>
		</div>
	</div>
</section>
