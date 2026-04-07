<?php
/**
 * Bloco: Newsletter CTA
 * Tipo: newsletter_cta
 *
 * @package brasileira-theme
 */

defined( 'ABSPATH' ) || exit;

if ( empty( $block ) || empty( $block['config'] ) || ! is_array( $block['config'] ) ) {
	return;
}

$config = $block['config'];

$variant = isset( $config['variant'] ) ? sanitize_key( (string) $config['variant'] ) : '';
if ( $variant === '' && ! empty( $config['form_id'] ) ) {
	$variant = sanitize_key( (string) $config['form_id'] );
}
if ( $variant === '' ) {
	$variant = 'inline_banner';
}

$display_style = isset( $config['style'] ) ? sanitize_key( (string) $config['style'] ) : $variant;
$blk_id          = isset( $block['id'] ) ? sanitize_html_class( (string) $block['id'] ) : '';

$title = $config['headline'] ?? $config['title'] ?? '';
$title = is_string( $title ) ? $title : '';
if ( $title === '' ) {
	$title = __( 'Receba as principais notícias', 'brasileira-theme' );
}

$subtitle = $config['subtitle'] ?? '';
$subtitle = is_string( $subtitle ) ? $subtitle : __( 'Newsletter gratuita. Cancele quando quiser.', 'brasileira-theme' );

$cta = $config['cta_text'] ?? $config['button_text'] ?? __( 'Assinar', 'brasileira-theme' );
$cta = is_string( $cta ) ? $cta : __( 'Assinar', 'brasileira-theme' );

$form_id = isset( $config['form_id'] ) ? sanitize_key( (string) $config['form_id'] ) : 'default';
?>
<section
	class="blk-newsletter_cta blk-newsletter_cta--<?php echo esc_attr( $display_style ); ?>"
	id="blk-<?php echo esc_attr( $blk_id ); ?>"
	data-block-type="newsletter_cta"
	data-block-id="<?php echo esc_attr( $blk_id ); ?>"
>
	<div class="container">
		<div class="blk-newsletter_cta__inner">
			<div class="blk-newsletter_cta__texto">
				<h2 class="blk-newsletter_cta__title"><?php echo esc_html( $title ); ?></h2>
				<p class="blk-newsletter_cta__subtitle"><?php echo esc_html( $subtitle ); ?></p>
			</div>
			<form
				class="blk-newsletter_cta__form"
				action="<?php echo esc_url( admin_url( 'admin-ajax.php' ) ); ?>"
				method="post"
				data-form-id="<?php echo esc_attr( $form_id ); ?>"
			>
				<?php wp_nonce_field( 'brasileira_newsletter', 'nl_nonce' ); ?>
				<input type="hidden" name="action" value="brasileira_subscribe" />
				<label class="sr-only" for="nl-email-<?php echo esc_attr( $blk_id ); ?>"><?php esc_html_e( 'E-mail', 'brasileira-theme' ); ?></label>
				<input
					id="nl-email-<?php echo esc_attr( $blk_id ); ?>"
					type="email"
					name="email"
					required
					placeholder="<?php esc_attr_e( 'Seu e-mail', 'brasileira-theme' ); ?>"
					class="blk-newsletter_cta__input"
					autocomplete="email"
				/>
				<button type="submit" class="blk-newsletter_cta__btn"><?php echo esc_html( $cta ); ?></button>
			</form>
		</div>
	</div>
</section>
