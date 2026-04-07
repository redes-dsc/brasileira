<?php
/**
 * Bloco: Especial
 * Tipo: especial
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config  = $block['config'];
$post_id = isset( $config['post_id'] ) ? absint( $config['post_id'] ) : 0;
$style   = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'fullwidth_cover';
$blk_id  = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$subtitle  = isset( $config['subtitle'] ) ? (string) $config['subtitle'] : '';
$badge     = isset( $config['badge_text'] ) ? (string) $config['badge_text'] : __( 'Especial', 'brasileira-theme' );
$label_alt = isset( $config['label'] ) ? (string) $config['label'] : '';

$post = $post_id ? get_post( $post_id ) : null;
if ( ! $post || $post->post_status !== 'publish' ) {
	return;
}

$thumb = get_the_post_thumbnail(
	$post->ID,
	'brasileira-hero',
	array(
		'class'   => 'blk-especial__bg-img',
		'loading' => 'lazy',
		'alt'     => esc_attr( get_the_title( $post ) ),
	)
);

$excerpt = get_the_excerpt( $post );
if ( $excerpt === '' ) {
	$excerpt = wp_trim_words( wp_strip_all_tags( $post->post_content ), 30, '…' );
}

$sub_final = $subtitle !== '' ? $subtitle : ( $label_alt !== '' ? $label_alt : '' );
?>
<section
	class="blk-especial blk-especial--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="especial"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<?php if ( 'side_panel' === $style ) : ?>
			<div class="blk-especial__side">
				<?php if ( $thumb ) : ?>
					<figure class="blk-especial__fig"><?php echo $thumb; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
				<?php endif; ?>
				<div class="blk-especial__side-body">
					<?php if ( $badge !== '' ) : ?>
						<span class="blk-especial__badge"><?php echo esc_html( $badge ); ?></span>
					<?php endif; ?>
					<h2 class="blk-especial__title">
						<a href="<?php echo esc_url( get_permalink( $post ) ); ?>"><?php echo esc_html( get_the_title( $post ) ); ?></a>
					</h2>
					<?php if ( $sub_final !== '' ) : ?>
						<p class="blk-especial__subtitle"><?php echo esc_html( $sub_final ); ?></p>
					<?php endif; ?>
					<p class="blk-especial__excerpt"><?php echo esc_html( wp_strip_all_tags( $excerpt ) ); ?></p>
					<a class="blk-especial__cta" href="<?php echo esc_url( get_permalink( $post ) ); ?>"><?php esc_html_e( 'Ler especial', 'brasileira-theme' ); ?> →</a>
				</div>
			</div>
		<?php else : ?>
			<div class="blk-especial__cover"<?php echo $thumb ? ' style="--especial-img:url(' . esc_url( wp_get_attachment_image_url( get_post_thumbnail_id( $post->ID ), 'full' ) ) . ')"' : ''; ?>>
				<div class="blk-especial__overlay">
					<?php if ( $badge !== '' ) : ?>
						<span class="blk-especial__badge"><?php echo esc_html( $badge ); ?></span>
					<?php endif; ?>
					<h2 class="blk-especial__title">
						<a href="<?php echo esc_url( get_permalink( $post ) ); ?>"><?php echo esc_html( get_the_title( $post ) ); ?></a>
					</h2>
					<?php if ( $sub_final !== '' ) : ?>
						<p class="blk-especial__subtitle"><?php echo esc_html( $sub_final ); ?></p>
					<?php endif; ?>
				</div>
			</div>
		<?php endif; ?>
	</div>
</section>
