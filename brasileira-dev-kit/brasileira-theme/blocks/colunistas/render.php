<?php
/**
 * Bloco: Colunistas
 * Tipo: colunistas
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$rows   = isset( $config['colunistas'] ) && is_array( $config['colunistas'] ) ? $config['colunistas'] : array();
$style  = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'carousel_horizontal';
$blk_id = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

if ( empty( $rows ) ) {
	return;
}
?>
<section
	class="blk-colunistas blk-colunistas--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="colunistas"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<header class="blk-colunistas__header">
			<h2 class="blk-colunistas__titulo"><?php esc_html_e( 'Colunistas', 'brasileira-theme' ); ?></h2>
		</header>
		<div class="blk-colunistas__track">
			<?php
			foreach ( $rows as $row ) {
				if ( ! is_array( $row ) ) {
					continue;
				}
				$author_id = isset( $row['author_id'] ) ? absint( $row['author_id'] ) : 0;
				$post_id   = isset( $row['post_id'] ) ? absint( $row['post_id'] ) : 0;
				if ( $author_id < 1 || $post_id < 1 ) {
					continue;
				}
				$cpost = get_post( $post_id );
				if ( ! $cpost || $cpost->post_status !== 'publish' ) {
					continue;
				}
				$nome = get_the_author_meta( 'display_name', $author_id );
				$nome = $nome ? $nome : __( 'Colunista', 'brasileira-theme' );
				$avatar = get_avatar(
					$author_id,
					80,
					'',
					esc_attr( $nome ),
					array( 'class' => 'blk-colunistas__img' )
				);
				?>
				<article class="blk-colunistas__card">
					<a class="blk-colunistas__link" href="<?php echo esc_url( get_permalink( $cpost ) ); ?>">
						<figure class="blk-colunistas__avatar"><?php echo $avatar; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?></figure>
						<div class="blk-colunistas__info">
							<span class="blk-colunistas__nome"><?php echo esc_html( $nome ); ?></span>
							<h3 class="blk-colunistas__col-titulo"><?php echo esc_html( get_the_title( $cpost ) ); ?></h3>
						</div>
					</a>
				</article>
				<?php
			}
			?>
		</div>
	</div>
</section>
