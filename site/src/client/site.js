// Site behaviour: nav drawer, theme toggle, toc scroll-spy, search. Classic
// script (no modules, no fetch) so everything works from file:// too.
(function () {
	var root = document.documentElement.getAttribute('data-root') || '';
	var body = document.body;

	var navToggle = document.querySelector('[data-nav-toggle]');
	if (navToggle) {
		navToggle.addEventListener('click', function () {
			var open = body.getAttribute('data-nav-open') !== 'true';
			body.setAttribute('data-nav-open', String(open));
			navToggle.setAttribute('aria-expanded', String(open));
		});
	}

	var themeToggle = document.querySelector('[data-theme-toggle]');
	if (themeToggle) {
		themeToggle.addEventListener('click', function () {
			var dark = !document.documentElement.classList.contains('dark');
			document.documentElement.classList.toggle('dark', dark);
			try {
				localStorage.setItem('theme', dark ? 'dark' : 'light');
			} catch (e) {
				// storage blocked: the toggle still works for this page view
			}
		});
	}

	var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.docs-toc-link'));
	if (tocLinks.length && 'IntersectionObserver' in window) {
		var byId = {};
		tocLinks.forEach(function (a) { byId[decodeURIComponent(a.getAttribute('href').slice(1))] = a; });
		var observer = new IntersectionObserver(function (entries) {
			entries.forEach(function (entry) {
				if (!entry.isIntersecting || !byId[entry.target.id]) return;
				tocLinks.forEach(function (a) { a.removeAttribute('data-active'); });
				byId[entry.target.id].setAttribute('data-active', 'true');
			});
		}, { rootMargin: '-64px 0px -70% 0px' });
		document.querySelectorAll('.docs-prose h2[id], .docs-prose h3[id]').forEach(function (h) { observer.observe(h); });
	}

	var input = document.querySelector('[data-search-input]');
	var results = document.querySelector('[data-search-results]');
	var data = window.ARM_DOCS_SEARCH;
	if (!input || !results || !data || !window.MiniSearch) return;
	var search = window.MiniSearch.loadJS(data.index, data.options);

	function render(query) {
		results.textContent = '';
		if (!query.trim()) {
			results.hidden = true;
			return;
		}
		var hits = search.search(query, { prefix: true, fuzzy: 0.2, boost: { title: 3, headings: 2 } }).slice(0, 8);
		if (!hits.length) {
			var empty = document.createElement('p');
			empty.className = 'docs-search-empty';
			empty.textContent = 'No matches';
			results.appendChild(empty);
		}
		hits.forEach(function (hit) {
			var page = data.pages[hit.id];
			if (!page) return;
			var a = document.createElement('a');
			a.className = 'docs-search-result';
			a.href = root + page.path;
			a.textContent = page.title;
			results.appendChild(a);
		});
		results.hidden = false;
	}
	input.addEventListener('input', function () { render(input.value); });
	input.addEventListener('keydown', function (e) {
		if (e.key === 'Escape') {
			input.value = '';
			render('');
		} else if (e.key === 'Enter') {
			var first = results.querySelector('a');
			if (first) window.location.href = first.href;
		}
	});
	document.addEventListener('click', function (e) {
		if (!e.target.closest('.docs-search')) results.hidden = true;
	});
})();
