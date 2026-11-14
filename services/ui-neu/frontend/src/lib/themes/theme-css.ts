// Where a theme's CSS comes from (a static file for a built-in, the theme API
// for an upload) and the in-memory and localStorage copies kept of it.
import { fetchTheme } from '$lib/api/themes';
import { COLOR_SCHEMES } from '$lib/themes/builtin-schemes';

/**
 * Built-in scheme ids. Their full CSS ships as static assets in the frontend
 * (static/themes/{id}.css, served same-origin by nginx) — NOT from the backend
 * theme API, which serves only user-uploaded themes. So theme styling is a
 * pure frontend concern; only uploads round-trip the backend.
 */
const BUILTIN_IDS = new Set(COLOR_SCHEMES.map((s) => s.id));

/** Cache of full theme data (with CSS) fetched from the API */
const cssCache = new Map<string, string>();

/** Fetch a built-in theme's CSS from the frontend's own static assets. */
async function fetchBuiltinCss(id: string): Promise<string> {
	const res = await fetch(`/themes/${encodeURIComponent(id)}.css`);
	if (!res.ok) return '';
	return res.text();
}

/**
 * Fetch a theme's CSS. Built-in themes: the bundled static CSS (same-origin,
 * no API). User-uploaded themes: the backend theme API.
 */
export async function fetchThemeCss(id: string): Promise<string> {
	return BUILTIN_IDS.has(id) ? await fetchBuiltinCss(id) : (await fetchTheme(id)).css;
}

/** Remember a theme's CSS in memory and in localStorage. */
export function cacheThemeCss(id: string, css: string): void {
	cssCache.set(id, css);
	try {
		globalThis.window?.localStorage?.setItem(`theme-cache-v1-${id}`, css);
	} catch {
		// localStorage unavailable or quota exceeded - non-fatal
	}
}

/** The CSS cached for a theme id, if any. */
export function cachedThemeCss(id: string): string | undefined {
	return cssCache.get(id);
}
