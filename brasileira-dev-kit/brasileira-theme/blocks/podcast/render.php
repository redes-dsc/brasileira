<?php
/**
 * Bloco: Podcast
 * Tipo: podcast
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];
$style  = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : 'player_featured';
$blk_id = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$episodes = isset( $config['episodes'] ) && is_array( $config['episodes'] ) ? $config['episodes'] : array();
$feat_id  = isset( $config['featured_episode_id'] ) ? absint( $config['featured_episode_id'] ) : 0;

$resolved = array();

if ( ! empty( $episodes ) ) {
	foreach ( $episodes as $ep ) {
		if ( ! is_array( $ep ) ) {
			continue;
		}
		$pid   = isset( $ep['post_id'] ) ? absint( $ep['post_id'] ) : 0;
		$audio = isset( $ep['audio_url'] ) ? esc_url_raw( (string) $ep['audio_url'] ) : '';
		$dur   = isset( $ep['duration'] ) ? (string) $ep['duration'] : '';
		$show  = isset( $ep['show_name'] ) ? (string) $ep['show_name'] : '';
		if ( $pid ) {
			$p = get_post( $pid );
			if ( $p && $p->post_status === 'publish' ) {
				if ( $audio === '' ) {
					$audio = get_post_meta( $pid, 'audio_url', true );
					$audio = is_string( $audio ) ? esc_url_raw( $audio ) : '';
				}
				$resolved[] = array(
					'post'  => $p,
					'audio' => $audio,
					'dur'   => $dur,
					'show'  => $show,
				);
			}
		}
	}
}

if ( $feat_id > 0 ) {
	$fp = get_post( $feat_id );
	if ( $fp && $fp->post_status === 'publish' ) {
		array_unshift(
			$resolved,
			array(
				'post'  => $fp,
				'audio' => esc_url_raw( (string) get_post_meta( $feat_id, 'audio_url', true ) ),
				'dur'   => '',
				'show'  => '',
			)
		);
	}
}

$resolved = array_values( array_filter( $resolved ) );
if ( empty( $resolved ) ) {
	return;
}

$first = $resolved[0];
$rest  = array_slice( $resolved, 1 );
?>
<section
	class="blk-podcast blk-podcast--<?php echo esc_attr( $style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="podcast"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<header class="blk-podcast__header">
			<h2 class="blk-podcast__titulo"><?php esc_html_e( 'Podcast', 'brasileira-theme' ); ?></h2>
		</header>

		<?php if ( 'list_episodes' === $style ) : ?>
			<ol class="blk-podcast__list">
				<?php
				foreach ( $resolved as $row ) {
					/** @var WP_Post $p */
					$p = $row['post'];
					?>
					<li class="blk-podcast__list-item">
						<a class="blk-podcast__list-link" href="<?php echo esc_url( get_permalink( $p ) ); ?>">
							<span class="blk-podcast__list-title"><?php echo esc_html( get_the_title( $p ) ); ?></span>
							<?php if ( $row['dur'] !== '' ) : ?>
								<span class="blk-podcast__dur"><?php echo esc_html( $row['dur'] ); ?></span>
							<?php endif; ?>
						</a>
						<?php if ( $row['audio'] !== '' ) : ?>
							<audio class="blk-podcast__audio" controls preload="none" src="<?php echo esc_url( $row['audio'] ); ?>"></audio>
						<?php endif; ?>
					</li>
					<?php
				}
				?>
			</ol>
		<?php else : ?>
			<div class="blk-podcast__featured">
				<h3 class="blk-podcast__ep-title">
					<a href="<?php echo esc_url( get_permalink( $first['post'] ) ); ?>"><?php echo esc_html( get_the_title( $first['post'] ) ); ?></a>
				</h3>
				<?php if ( $first['show'] !== '' ) : ?>
					<p class="blk-podcast__show"><?php echo esc_html( $first['show'] ); ?></p>
				<?php endif; ?>
				<?php if ( $first['audio'] !== '' ) : ?>
					<audio class="blk-podcast__audio blk-podcast__audio--main" controls preload="none" src="<?php echo esc_url( $first['audio'] ); ?>"></audio>
				<?php endif; ?>
			</div>
			<?php if ( ! empty( $rest ) ) : ?>
				<ul class="blk-podcast__extras">
					<?php
					foreach ( $rest as $row ) {
						$p = $row['post'];
						?>
						<li class="blk-podcast__extra">
							<a href="<?php echo esc_url( get_permalink( $p ) ); ?>"><?php echo esc_html( get_the_title( $p ) ); ?></a>
							<?php if ( $row['dur'] !== '' ) : ?>
								<span class="blk-podcast__dur"><?php echo esc_html( $row['dur'] ); ?></span>
							<?php endif; ?>
						</li>
						<?php
					}
					?>
				</ul>
			<?php endif; ?>
		<?php endif; ?>
	</div>
</section>
