<?php
/**
 * Bloco: Mais lidas
 * Tipo: mais_lidas
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$period = isset( $config['period'] ) ? sanitize_key( (string) $config['period'] ) : '24h';
$count  = isset( $config['count'] ) ? max( 1, absint( $config['count'] ) ) : 10;
$style  = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'numbered_list';
$blk_id = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$periodo_map = array(
	'24h' => __( 'Hoje', 'brasileira-theme' ),
	'7d'  => __( 'Esta semana', 'brasileira-theme' ),
	'30d' => __( 'Este mês', 'brasileira-theme' ),
);
$periodo_label = $periodo_map[ $period ] ?? __( 'Período', 'brasileira-theme' );

$date_query = array();
if ( '24h' === $period ) {
	$date_query = array(
		array(
			'after'     => '24 hours ago',
			'inclusive' => true,
		),
	);
} elseif ( '7d' === $period ) {
	$date_query = array(
		array(
			'after'     => '7 days ago',
			'inclusive' => true,
		),
	);
} elseif ( '30d' === $period ) {
	$date_query = array(
		array(
			'after'     => '30 days ago',
			'inclusive' => true,
		),
	);
}

$qargs = array(
	'posts_per_page' => $count,
	'post_status'    => 'publish',
	'orderby'        => 'meta_value_num',
	'meta_key'       => 'brasileira_view_count',
	'order'          => 'DESC',
	'no_found_rows'  => true,
);
if ( ! empty( $date_query ) ) {
	$qargs['date_query'] = $date_query;
}

$posts = get_posts( $qargs );

if ( empty( $posts ) ) {
	unset( $qargs['meta_key'], $qargs['orderby'] );
	$qargs['orderby'] = 'date';
	$qargs['order']   = 'DESC';
	if ( ! empty( $date_query ) ) {
		$qargs['date_query'] = $date_query;
	}
	$posts = get_posts( $qargs );
}

if ( empty( $posts ) ) {
	unset( $qargs['date_query'] );
	$posts = get_posts( $qargs );
}

if ( empty( $posts ) ) {
	return;
}
?>
<section
	class="blk-mais_lidas blk-mais_lidas--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="mais_lidas"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<header class="blk-mais_lidas__header">
			<h2 class="blk-mais_lidas__titulo"><?php esc_html_e( 'Mais lidas', 'brasileira-theme' ); ?></h2>
			<span class="blk-mais_lidas__periodo"><?php echo esc_html( $periodo_label ); ?></span>
		</header>
		<ol class="blk-mais_lidas__lista">
			<?php
			$num = 0;
			foreach ( $posts as $p ) {
				++$num;
				$cats = get_the_category( $p->ID );
				$cat  = ! empty( $cats ) ? $cats[0]->name : '';
				?>
				<li class="blk-mais_lidas__item">
					<span class="blk-mais_lidas__num" aria-hidden="true"><?php echo esc_html( (string) $num ); ?></span>
					<div class="blk-mais_lidas__content">
						<?php if ( $cat !== '' ) : ?>
							<span class="blk-mais_lidas__cat"><?php echo esc_html( $cat ); ?></span>
						<?php endif; ?>
						<a href="<?php echo esc_url( get_permalink( $p ) ); ?>" class="blk-mais_lidas__titulo-link"><?php echo esc_html( get_the_title( $p ) ); ?></a>
					</div>
				</li>
				<?php
			}
			?>
		</ol>
	</div>
</section>
