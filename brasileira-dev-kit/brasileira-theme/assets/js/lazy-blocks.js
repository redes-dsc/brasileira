/**
 * Carregamento preguiçoso de blocos (placeholder → HTML via REST).
 */
(function () {
	'use strict';

	document.addEventListener('DOMContentLoaded', initLazyBlocks);

	function initLazyBlocks() {
		const sel = '.blk--lazy, [data-lazy-block]';
		const els = document.querySelectorAll(sel);
		if (!els.length) {
			return;
		}
		if (!('IntersectionObserver' in window)) {
			loadAll(els);
			return;
		}
		const io = new IntersectionObserver(
			function (entries, obs) {
				entries.forEach(function (entry) {
					if (!entry.isIntersecting) {
						return;
					}
					const el = entry.target;
					obs.unobserve(el);
					loadBlock(el);
				});
			},
			{ rootMargin: '200px 0px', threshold: 0.01 }
		);
		els.forEach(function (el) {
			io.observe(el);
		});
	}

	function loadAll(nodeList) {
		nodeList.forEach(loadBlock);
	}

	function loadBlock(el) {
		const blockId = el.getAttribute('data-block-id');
		const base = (window.BrasileiraSite && window.BrasileiraSite.restUrl) || '';
		if (!blockId || !base) {
			return;
		}
		const url = base.replace(/\/?$/, '/') + 'block/' + encodeURIComponent(blockId) + '/html';
		fetch(url, { credentials: 'same-origin' })
			.then(function (r) {
				return r.ok ? r.text() : '';
			})
			.then(function (html) {
				if (html) {
					el.classList.remove('blk--lazy');
					el.innerHTML = html;
				}
			})
			.catch(function () {});
	}
})();
