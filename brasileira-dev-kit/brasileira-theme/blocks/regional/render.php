<?php
/**
 * Bloco: Regional (por UF)
 * Tipo: regional
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config        = $block['config'];
$ufs           = isset( $config['ufs'] ) && is_array( $config['ufs'] ) ? $config['ufs'] : array();
$ufs           = array_map(
	static function ( $u ) {
		return strtoupper( sanitize_text_field( (string) $u ) );
	},
	$ufs
);
$ufs           = array_values( array_filter( array_unique( $ufs ) ) );
$style         = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'uf_tabs';
$blk_id        = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';
$posts_per_uf  = isset( $config['posts_per_uf'] ) ? max( 1, absint( $config['posts_per_uf'] ) ) : 2;
$highlight     = isset( $config['highlight_uf'] ) ? strtoupper( sanitize_text_field( (string) $config['highlight_uf'] ) ) : '';

if ( empty( $ufs ) ) {
	return;
}

if ( $highlight === '' || ! in_array( $highlight, $ufs, true ) ) {
	$highlight = $ufs[0];
}

/**
 * Busca posts por tag = sigla da UF em minúsculas.
 *
 * @param string $uf Sigla.
 * @param int    $n    Quantidade.
 * @return WP_Post[]
 */
$fetch_by_uf = static function ( string $uf, int $n ): array {
	$slug = strtolower( $uf );
	$q    = new WP_Query(
		array(
			'posts_per_page' => $n,
			'post_status'    => 'publish',
			'tag_slug__in'   => array( $slug ),
			'no_found_rows'  => true,
		)
	);
	$posts = $q->have_posts() ? $q->posts : array();
	wp_reset_postdata();
	if ( empty( $posts ) ) {
		$q = new WP_Query(
			array(
				'posts_per_page' => $n,
				'post_status'    => 'publish',
				'category_name'  => $slug,
				'no_found_rows'  => true,
			)
		);
		$posts = $q->have_posts() ? $q->posts : array();
		wp_reset_postdata();
	}
	return $posts;
};

$panels = array();
foreach ( $ufs as $uf ) {
	$panels[ $uf ] = $fetch_by_uf( $uf, $posts_per_uf );
}
?>
<section
	class="blk-regional blk-regional--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="regional"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
	data-highlight-uf="<?php echo esc_attr( $highlight ); ?>"
>
	<div class="container">
		<header class="blk-regional__header">
			<h2 class="blk-regional__titulo"><?php esc_html_e( 'Regional', 'brasileira-theme' ); ?></h2>
		</header>

		<?php if ( 'map_grid' === $style ) : ?>
			<div class="blk-regional__map-grid">
				<?php foreach ( $panels as $uf => $posts ) : ?>
					<div class="blk-regional__cell">
						<h3 class="blk-regional__uf"><?php echo esc_html( $uf ); ?></h3>
						<ul class="blk-regional__list">
							<?php foreach ( $posts as $p ) : ?>
								<li><a href="<?php echo esc_url( get_permalink( $p ) ); ?>"><?php echo esc_html( get_the_title( $p ) ); ?></a></li>
							<?php endforeach; ?>
						</ul>
					</div>
				<?php endforeach; ?>
			</div>
		<?php else : ?>
			<div class="blk-regional__tabs" role="tablist" aria-label="<?php echo esc_attr__( 'Estados', 'brasileira-theme' ); ?>">
				<?php foreach ( $ufs as $i => $uf ) : ?>
					<button
						type="button"
						class="blk-regional__tab<?php echo $uf === $highlight ? ' is-active' : ''; ?>"
						role="tab"
						aria-selected="<?php echo $uf === $highlight ? 'true' : 'false'; ?>"
						data-uf="<?php echo esc_attr( $uf ); ?>"
						id="tab-<?php echo esc_attr( $blk_id . '-' . $uf ); ?>"
					><?php echo esc_html( $uf ); ?></button>
				<?php endforeach; ?>
			</div>
			<?php foreach ( $ufs as $uf ) : ?>
				<div
					class="blk-regional__panel<?php echo $uf === $highlight ? ' is-active' : ''; ?>"
					role="tabpanel"
					data-uf-panel="<?php echo esc_attr( $uf ); ?>"
					aria-labelledby="tab-<?php echo esc_attr( $blk_id . '-' . $uf ); ?>"
					<?php echo $uf === $highlight ? '' : ' hidden'; ?>
				>
					<ul class="blk-regional__list">
						<?php
						foreach ( $panels[ $uf ] as $p ) {
							$t = human_time_diff( get_post_time( 'U', false, $p ), current_time( 'timestamp' ) );
							?>
							<li class="blk-regional__item">
								<a class="blk-regional__link" href="<?php echo esc_url( get_permalink( $p ) ); ?>"><?php echo esc_html( get_the_title( $p ) ); ?></a>
								<span class="blk-regional__meta"><?php echo esc_html( $t ); ?> <?php esc_html_e( 'atrás', 'brasileira-theme' ); ?></span>
							</li>
							<?php
						}
						?>
					</ul>
				</div>
			<?php endforeach; ?>
		<?php endif; ?>
	</div>
</section>
<script>
(function(){
	var root = document.getElementById(<?php echo wp_json_encode( 'blk-' . $blk_id ); ?>);
	if(!root||!root.querySelectorAll) return;
	var tabs = root.querySelectorAll('.blk-regional__tab');
	var panels = root.querySelectorAll('.blk-regional__panel');
	tabs.forEach(function(tab){
		tab.addEventListener('click', function(){
			var uf = tab.getAttribute('data-uf');
			tabs.forEach(function(t){ t.classList.remove('is-active'); t.setAttribute('aria-selected','false'); });
			tab.classList.add('is-active'); tab.setAttribute('aria-selected','true');
			panels.forEach(function(p){
				var show = p.getAttribute('data-uf-panel') === uf;
				p.classList.toggle('is-active', show);
				p.hidden = !show;
			});
		});
	});
})();
</script>
