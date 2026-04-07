/**
 * Atualizações ao vivo — breaking e blocos com data-auto-refresh.
 * SSE se habilitado; senão polling no REST (quando existir no plugin).
 */
(function () {
	'use strict';

	const config = window.BrasileiraSite || {};

	document.addEventListener('DOMContentLoaded', init);

	function init() {
		initClocks();

		const nodes = document.querySelectorAll('[data-auto-refresh]');
		if (!nodes.length) {
			return;
		}
		if (config.sseEnabled) {
			connectSSE(nodes);
		} else {
			nodes.forEach(function (el) {
				const sec = parseInt(el.getAttribute('data-auto-refresh'), 10);
				if (sec > 0) {
					startPolling(el, sec);
				}
			});
		}
	}

	function connectSSE(nodes) {
		const url = (config.restUrl || '').replace(/\/?$/, '/') + 'stream/breaking';
		let es;
		try {
			es = new EventSource(url);
		} catch (e) {
			nodes.forEach(function (el) {
				const sec = parseInt(el.getAttribute('data-auto-refresh'), 10) || 60;
				startPolling(el, sec);
			});
			return;
		}
		es.onmessage = function (ev) {
			nodes.forEach(function (el) {
				updateBlock(el, ev.data);
			});
		};
		es.onerror = function () {
			es.close();
			nodes.forEach(function (el) {
				const sec = parseInt(el.getAttribute('data-auto-refresh'), 10) || 60;
				startPolling(el, sec);
			});
		};
	}

	function startPolling(el, intervalSeconds) {
		const blockId = el.getAttribute('data-block-id');
		if (!blockId || !config.restUrl) {
			return;
		}
		const tick = function () {
			const u =
				config.restUrl.replace(/\/?$/, '/') +
				'block/' +
				encodeURIComponent(blockId) +
				'/html';
			fetch(u, { credentials: 'same-origin' })
				.then(function (r) {
					return r.ok ? r.text() : null;
				})
				.then(function (html) {
					if (html) {
						updateBlock(el, html);
					}
				})
				.catch(function () {});
		};
		setInterval(tick, Math.max(intervalSeconds, 10) * 1000);
	}

	function updateBlock(el, html) {
		if (!html) {
			return;
		}
		el.innerHTML = html;
	}

	function initClocks() {
		const clocks = document.querySelectorAll('[data-brasileira-clock]');
		if (!clocks.length) {
			return;
		}
		function tick() {
			const s = new Date().toLocaleTimeString('pt-BR', {
				hour: '2-digit',
				minute: '2-digit',
			});
			clocks.forEach(function (el) {
				el.textContent = s;
			});
		}
		tick();
		setInterval(tick, 30000);
	}
})();
