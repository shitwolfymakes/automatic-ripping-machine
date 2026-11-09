// Scrolling to a help page's URL fragment once the page has rendered.

/** The element id a `location.hash` value names ('' when it has none). */
export function fragmentId(hash: string): string {
	const raw = hash.slice(1);
	let id = raw;
	try {
		id = decodeURIComponent(raw);
	} catch {
		// Malformed percent-encoding: fall back to the raw hash rather
		// than failing the whole page load.
	}
	return id;
}

/** Scroll to the element with this id, or to the top of <main> without one. */
export function scrollToFragment(id: string): void {
	if (id) document.getElementById(id)?.scrollIntoView();
	// The app scrolls inside <main>, not the window, so a plain
	// navigation (no hash) needs its own scroll-to-top.
	else document.querySelector('main')?.scrollTo(0, 0);
}
