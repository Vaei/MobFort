/* Copyright (c) Jared Taylor. All Rights Reserved */

/* Documentation shell. Repo-agnostic: everything it renders comes from site.js.
   No fetch, no modules, no network - the site has to work from file:// as well as Pages. */

(function () {
	'use strict';

	var D = window.DOCS || {};
	var SHOTS = D.shots || {};
	var SECTIONS = D.sections || [];
	var IMG = D.imgDir || 'img/';

	var here = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
	if (here === '') here = 'index.html';

	var flat = [];
	SECTIONS.forEach(function (s) { (s.pages || []).forEach(function (p) { flat.push(p); }); });

	function el(tag, attrs, kids) {
		var n = document.createElement(tag);
		for (var k in attrs || {}) {
			if (k === 'text') n.textContent = attrs[k];
			else if (k === 'html') n.innerHTML = attrs[k];
			else n.setAttribute(k, attrs[k]);
		}
		(kids || []).forEach(function (c) { if (c) n.appendChild(c); });
		return n;
	}

	function slug(s) {
		return s.toLowerCase().replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-');
	}

	/* ------------------------------------------------------------- theme */

	function applyTheme(t) {
		document.documentElement.dataset.theme = t;
		try { localStorage.setItem('mob-theme', t); } catch (e) {}
		var b = document.getElementById('themebtn');
		if (b) { b.textContent = t === 'dark' ? '☀' : '☽'; b.title = t === 'dark' ? 'Light' : 'Dark'; }
	}

	/* -------------------------------------------------------------- chrome */

	function buildHeader() {
		var brandKids = [];
		if (D.icon) brandKids.push(el('img', { src: D.icon, alt: '' }));
		brandKids.push(el('span', { text: D.title || 'Documentation' }));

		var menu = el('button', { class: 'iconbtn menu', type: 'button', 'aria-label': 'Menu', text: '≡' });
		menu.onclick = function () { document.querySelector('nav.rail').classList.toggle('open'); };

		var theme = el('button', { class: 'iconbtn', type: 'button', id: 'themebtn', 'aria-label': 'Theme' });
		theme.onclick = function () {
			applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
		};

		var kids = [menu, el('a', { class: 'brand', href: 'index.html' }, brandKids), el('div', { class: 'spacer' })];
		if (D.repo) {
			var g = el('a', { class: 'iconbtn', href: D.repo, title: 'Repository', target: '_blank', rel: 'noopener', text: '⚑' });
			kids.push(g);
		}
		kids.push(theme);
		return el('header', { class: 'top' }, kids);
	}

	function buildRail() {
		var rail = el('nav', { class: 'rail' });
		var filter = el('input', { class: 'filter', type: 'search', placeholder: 'Filter pages', 'aria-label': 'Filter pages' });
		rail.appendChild(filter);

		SECTIONS.forEach(function (s) {
			var h = el('h6', { text: s.name });
			rail.appendChild(h);
			(s.pages || []).forEach(function (p) {
				var a = el('a', { href: p.file, text: p.label });
				if (p.file.toLowerCase() === here) a.className = 'here';
				a.dataset.hay = (p.label + ' ' + (p.blurb || '')).toLowerCase();
				rail.appendChild(a);
			});
		});

		filter.oninput = function () {
			var q = filter.value.trim().toLowerCase();
			rail.querySelectorAll('a[data-hay]').forEach(function (a) {
				a.classList.toggle('hidden', !!q && a.dataset.hay.indexOf(q) < 0);
			});
			rail.querySelectorAll('h6').forEach(function (h) {
				var vis = false, n = h.nextElementSibling;
				while (n && n.tagName === 'A') { if (!n.classList.contains('hidden')) vis = true; n = n.nextElementSibling; }
				h.style.display = vis ? '' : 'none';
			});
		};
		return rail;
	}

	function buildToc(main) {
		var aside = el('aside', { class: 'toc' });
		var heads = main.querySelectorAll('h2, h3');
		if (!heads.length) return aside;
		aside.appendChild(el('strong', { text: 'On this page' }));
		heads.forEach(function (h) {
			if (!h.id) h.id = slug(h.textContent);
			h.appendChild(el('a', { class: 'anchor', href: '#' + h.id, 'aria-hidden': 'true', text: '#' }));
			var a = el('a', { href: '#' + h.id, text: h.textContent.replace(/#$/, '') });
			if (h.tagName === 'H3') a.className = 'sub';
			a.dataset.for = h.id;
			aside.appendChild(a);
		});

		var links = aside.querySelectorAll('a[data-for]');
		var spy = function () {
			var best = null, top = 120;
			heads.forEach(function (h) {
				var y = h.getBoundingClientRect().top;
				if (y < top) best = h.id;
			});
			links.forEach(function (a) { a.classList.toggle('here', a.dataset.for === best); });
		};
		document.addEventListener('scroll', spy, { passive: true });
		spy();
		return aside;
	}

	function buildPageNav() {
		var i = -1;
		flat.forEach(function (p, n) { if (p.file.toLowerCase() === here) i = n; });
		if (i < 0) return null;
		var wrap = el('div', { class: 'pagenav' });
		if (i > 0) wrap.appendChild(el('a', { class: 'prev', href: flat[i - 1].file },
			[el('small', { text: 'Previous' }), el('b', { text: flat[i - 1].label })]));
		if (i < flat.length - 1) wrap.appendChild(el('a', { class: 'next', href: flat[i + 1].file },
			[el('small', { text: 'Next' }), el('b', { text: flat[i + 1].label })]));
		return wrap.children.length ? wrap : null;
	}

	/* ------------------------------------------------------------- figures */

	var gallery = [];

	function media(shot) {
		if (shot.yt) return { kind: 'yt', src: 'https://www.youtube.com/embed/' + shot.yt };
		if (shot.vid) return { kind: 'vid', src: IMG + shot.vid };
		if (shot.file) return { kind: 'img', src: IMG + shot.file };
		return null;
	}

	function wantedChip(cap) {
		return el('span', { class: 'shot-chip wanted' }, [el('span', { class: 'cap', text: cap })]);
	}

	/* Gallery slots are reserved in document order so the arrow keys walk the page
	   the way it reads, whatever order the thumbnails happen to decode in. */
	function buildShot(id, host) {
		var shot = SHOTS[id];
		if (!shot) { host.appendChild(wantedChip('undeclared figure: ' + id)); return; }
		var cap = shot.cap || id;
		var m = media(shot);
		if (!m) { host.appendChild(wantedChip(cap)); return; }

		/* A local video cannot be probed, so its poster stands in as the proof it exists.
		   No poster means the shot has not been captured yet. */
		if (m.kind === 'vid' && !shot.poster) { host.appendChild(wantedChip(cap)); return; }

		var idx = gallery.push({ shot: shot, media: m, cap: cap, ok: m.kind !== 'img' }) - 1;
		var chip = el('button', { class: 'shot-chip', type: 'button' });
		chip.onclick = function () { openLightbox(idx); };

		/* Only a still can be probed. A missing image is the only failure the page
		   can detect without fetch, and it is the one that has to stay compact. */
		if (m.kind === 'img' || shot.poster) {
			var thumb = el('img', { alt: '', loading: 'lazy' });
			thumb.onerror = function () {
				gallery[idx].ok = false;
				host.replaceChild(wantedChip(cap), chip);
			};
			thumb.onload = function () { gallery[idx].ok = true; };
			thumb.src = m.kind === 'img' ? m.src : IMG + shot.poster;
			chip.appendChild(thumb);
		}

		var hasThumb = !!chip.querySelector('img');
		if (m.kind !== 'img' && hasThumb) chip.appendChild(el('span', { class: 'badge', text: '▶' }));
		chip.appendChild(el('span', { class: 'cap', text: (m.kind === 'img' || hasThumb ? '' : '▶  ') + cap }));
		host.appendChild(chip);
	}

	function mountFigures(main) {
		main.querySelectorAll('[data-shot]').forEach(function (host) {
			host.classList.add('shot');
			buildShot(host.dataset.shot.trim(), host);
		});
		main.querySelectorAll('[data-shots]').forEach(function (host) {
			host.classList.add('shots');
			host.dataset.shots.split(',').forEach(function (id) {
				id = id.trim();
				if (!id) return;
				var cell = el('div', { class: 'shot' });
				host.appendChild(cell);
				buildShot(id, cell);
			});
		});
	}

	/* ------------------------------------------------------------ lightbox */

	var lb, lbStage, lbCap, lbCount, lbIndex = 0;

	function buildLightbox() {
		lbCount = el('span', {});
		lbCap = el('div', { class: 'lb-cap' });
		lbStage = el('div', { class: 'lb-stage' });

		var prev = el('button', { type: 'button', text: '←' });
		var next = el('button', { type: 'button', text: '→' });
		var close = el('button', { type: 'button', text: 'Close  ×' });
		prev.onclick = function () { step(-1); };
		next.onclick = function () { step(1); };
		close.onclick = closeLightbox;

		var bar = el('div', { class: 'lb-bar' }, [prev, next, lbCount, el('div', { class: 'spacer' }), close]);
		lb = el('div', { class: 'lb' }, [bar, lbStage, lbCap]);
		lb.onclick = function (e) { if (e.target === lb || e.target === lbStage) closeLightbox(); };
		document.body.appendChild(lb);

		document.addEventListener('keydown', function (e) {
			if (!lb.classList.contains('open')) return;
			if (e.key === 'Escape') closeLightbox();
			else if (e.key === 'ArrowLeft') step(-1);
			else if (e.key === 'ArrowRight') step(1);
		});
	}

	function step(d) {
		if (!gallery.length) return;
		var i = lbIndex;
		for (var n = 0; n < gallery.length; n++) {
			i = (i + d + gallery.length) % gallery.length;
			if (gallery[i].ok) { lbIndex = i; render(); return; }
		}
	}

	function compareView(entry) {
		var box = el('div', { class: 'cmp' });
		var a = el('img', { src: IMG + entry.shot.file, alt: '' });
		var b = el('img', { class: 'after', src: IMG + entry.shot.compare, alt: '' });
		var handle = el('div', { class: 'handle' });
		var labels = entry.shot.compareLabels || ['Before', 'After'];
		box.appendChild(a);
		box.appendChild(b);
		box.appendChild(el('span', { class: 'tagl', text: labels[0] }));
		box.appendChild(el('span', { class: 'tagr', text: labels[1] }));
		box.appendChild(handle);

		var drag = function (e) {
			var r = box.getBoundingClientRect();
			var x = ((e.touches ? e.touches[0].clientX : e.clientX) - r.left) / r.width;
			x = Math.max(0, Math.min(1, x));
			b.style.clipPath = 'inset(0 0 0 ' + (x * 100) + '%)';
			handle.style.left = (x * 100) + '%';
		};
		var stop = function () {
			window.removeEventListener('mousemove', drag);
			window.removeEventListener('touchmove', drag);
			window.removeEventListener('mouseup', stop);
			window.removeEventListener('touchend', stop);
		};
		var start = function (e) {
			e.preventDefault();
			window.addEventListener('mousemove', drag);
			window.addEventListener('touchmove', drag, { passive: false });
			window.addEventListener('mouseup', stop);
			window.addEventListener('touchend', stop);
		};
		handle.addEventListener('mousedown', start);
		handle.addEventListener('touchstart', start, { passive: false });
		box.addEventListener('click', function (e) { e.stopPropagation(); drag(e); });
		return box;
	}

	function render() {
		var entry = gallery[lbIndex];
		lbStage.className = 'lb-stage';
		lbStage.textContent = '';

		if (entry.media.kind === 'yt') {
			lbStage.appendChild(el('iframe', {
				src: entry.media.src, width: '960', height: '540', frameborder: '0',
				allow: 'accelerometer; encrypted-media; picture-in-picture', allowfullscreen: 'true'
			}));
		} else if (entry.media.kind === 'vid') {
			lbStage.appendChild(el('video', { src: entry.media.src, controls: 'true', autoplay: 'true', loop: 'true', playsinline: 'true' }));
		} else if (entry.shot.compare) {
			lbStage.appendChild(compareView(entry));
		} else {
			var img = el('img', { src: entry.media.src, alt: entry.cap });
			img.onclick = function (e) { e.stopPropagation(); lbStage.classList.toggle('actual'); };
			lbStage.appendChild(img);
		}

		var live = gallery.filter(function (g) { return g.ok; });
		lbCap.textContent = entry.cap;
		lbCount.textContent = (live.indexOf(entry) + 1) + ' / ' + live.length;
	}

	function openLightbox(i) {
		lbIndex = i;
		lb.classList.add('open');
		document.body.style.overflow = 'hidden';
		render();
	}

	function closeLightbox() {
		lb.classList.remove('open');
		lbStage.textContent = '';
		document.body.style.overflow = '';
	}

	/* ---------------------------------------------------------------- boot */

	function boot() {
		var main = document.querySelector('main');
		if (!main) return;

		document.body.insertBefore(buildHeader(), document.body.firstChild);

		var shell = el('div', { class: 'shell' });
		main.parentNode.insertBefore(shell, main);
		var rail = buildRail();
		shell.appendChild(rail);
		shell.appendChild(main);

		mountFigures(main);
		var toc = buildToc(main);
		shell.appendChild(toc);

		var nav = buildPageNav();
		if (nav) main.appendChild(nav);
		if (D.footer) main.appendChild(el('div', { class: 'foot', html: D.footer }));

		buildLightbox();
		applyTheme(document.documentElement.dataset.theme || 'light');

		document.addEventListener('click', function (e) {
			if (window.innerWidth > 900) return;
			if (rail.classList.contains('open') && !rail.contains(e.target) && !e.target.closest('.iconbtn.menu')) {
				rail.classList.remove('open');
			}
		});

		if (window.MOB_PAGE_READY) window.MOB_PAGE_READY({ shots: SHOTS, sections: SECTIONS, imgDir: IMG, el: el });
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
	else boot();
})();
