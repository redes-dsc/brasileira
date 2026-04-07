<?php
/**
 * Bloco: Trending / assuntos em alta
 * Tipo: trending
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$style  = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'tag_cloud';
$blk_id = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$max = isset( $config['max_items'] ) ? max( 3, absint( $config['max_items'] ) ) : 10;
if ( isset( $config['count'] ) && absint( $config['count'] ) > 0 ) {
	$max = min( $max, absint( $config['count'] ) );
}

$topics = array();
if ( ! empty( $config['topics'] ) && is_array( $config['topics'] ) ) {
	foreach ( $config['topics'] as $row ) {
		if ( ! is_array( $row ) ) {
			continue;
		}
		$lab = isset( $row['label'] ) ? (string) $row['label'] : '';
		$url = isset( $row['url'] ) ? (string) $row['url'] : '';
		$cnt = isset( $row['count'] ) ? (int) $row['count'] : 0;
		if ( $lab !== '' && $url !== '' ) {
			$topics[] = array(
				'label' => $lab,
				'url'   => $url,
				'count' => max( 1, $cnt ),
			);
		}
		if ( count( $topics ) >= $max ) {
			break;
		}
	}
}

if ( empty( $topics ) ) {
	$tags = get_tags(
		array(
			'orderby'    => 'count',
			'order'      => 'DESC',
			'number'     => $max,
			'hide_empty' => true,
		)
	);
	foreach ( $tags as $t ) {
		$topics[] = array(
			'label' => $t->name,
			'url'   => get_tag_link( $t ),
			'count' => (int) $t->count,
		);
	}
}

if ( empty( $topics ) ) {
	return;
}

$counts   = wp_list_pluck( $topics, 'count' );
$max_c    = max( $counts );
$min_c    = min( $counts );
?>
<section
	class="blk-trending blk-trending--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="trending"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<header class="blk-trending__header">
			<h2 class="blk-trending__titulo"><?php esc_html_e( 'Em alta', 'brasileira-theme' ); ?></h2>
		</header>

		<?php if ( 'numbered_topics' === $style || 'list_trending' === $style ) : ?>
			<ol class="blk-trending__list">
				<?php
				$i = 0;
				foreach ( $topics as $row ) {
					++$i;
					?>
					<li class="blk-trending__list-item">
						<span class="blk-trending__num"><?php echo esc_html( (string) $i ); ?></span>
						<a class="blk-trending__link" href="<?php echo esc_url( $row['url'] ); ?>"><?php echo esc_html( $row['label'] ); ?></a>
						<span class="blk-trending__count"><?php echo esc_html( (string) $row['count'] ); ?></span>
					</li>
					<?php
				}
				?>
			</ol>
		<?php else : ?>
			<div class="blk-trending__cloud" role="list">
				<?php
				foreach ( $topics as $row ) {
					$size = 12;
					if ( $max_c > $min_c ) {
						$size = 12 + ( ( $row['count'] - $min_c ) / ( $max_c - $min_c ) ) * 10;
					}
					?>
					<a
						role="listitem"
						class="blk-trending__tag"
						href="<?php echo esc_url( $row['url'] ); ?>"
						style="font-size:<?php echo esc_attr( (string) round( $size, 1 ) ); ?>px"
					><?php echo esc_html( $row['label'] ); ?></a>
					<?php
				}
				?>
			</div>
		<?php endif; ?>
	</div>
</section>
