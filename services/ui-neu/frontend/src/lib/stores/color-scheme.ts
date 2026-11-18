import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { fetchThemes, type ThemeMeta } from '$lib/api/themes';
import { COLOR_SCHEMES, DEFAULT_SCHEME, type ColorScheme } from '$lib/themes/builtin-schemes';
import { applySchemeToDocument, applyTokensForCurrentMode } from '$lib/themes/apply-scheme';
import { fetchThemeCss, cacheThemeCss, cachedThemeCss } from '$lib/themes/theme-css';

/** Writable store of all available schemes (built-in + API-loaded) */
export const allSchemes = writable<ColorScheme[]>([...COLOR_SCHEMES]);

/** In-flight fetch promises keyed by theme id - prevents duplicate concurrent fetches */
const inFlight = new Map<string, Promise<void>>();

function getInitialScheme(): string {
	if (!browser) return DEFAULT_SCHEME.id;
	return localStorage.getItem('colorScheme') ?? DEFAULT_SCHEME.id;
}

function applyScheme(id: string) {
	if (!browser) return;
	const schemes = get(allSchemes);
	const scheme = schemes.find((s) => s.id === id) ?? DEFAULT_SCHEME;
	applySchemeToDocument(scheme, scheme.css ?? cachedThemeCss(scheme.id) ?? '');
}

/**
 * Re-apply the active scheme's inline tokens for the current `.dark` class
 * state on <html>. Called whenever something outside this module toggles
 * dark mode (the `theme` store), so the inline tokens follow the mode
 * instead of staying stuck on whichever mode was active at the last
 * `applyScheme` call.
 */
export function reapplySchemeForCurrentMode() {
	if (!browser) return;
	const id = get(colorScheme);
	const schemes = get(allSchemes);
	const scheme = schemes.find((s) => s.id === id) ?? DEFAULT_SCHEME;
	if (scheme.mode != null) return; // locked schemes ignore the theme store
	applyTokensForCurrentMode(scheme);
}

export const colorScheme = writable<string>(getInitialScheme());

/** True when the active color scheme locks the mode (light or dark) */
export const schemeLocksMode = derived(colorScheme, (id) => {
	const schemes = get(allSchemes);
	const scheme = schemes.find((s) => s.id === id);
	return scheme?.mode != null;
});

/**
 * Overlay the API themes on the built-in fallbacks. Built-ins come first with
 * builtin: true; an API theme replaces the built-in of the same id.
 */
function mergeThemes(builtins: ColorScheme[], apiThemes: ThemeMeta[]): ColorScheme[] {
	const merged = new Map<string, ColorScheme>();

	// Start with built-in fallbacks
	for (const s of builtins) {
		merged.set(s.id, { ...s, builtin: true });
	}

	// Overlay API themes (merge tokens so built-in defaults like --radius aren't lost)
	for (const t of apiThemes) {
		const existing = merged.get(t.id);
		merged.set(t.id, {
			id: t.id,
			label: t.label,
			swatch: t.swatch,
			mode: t.mode,
			tokens: { ...(existing?.tokens ?? {}), ...t.tokens },
			author: t.author,
			description: t.description,
			builtin: t.builtin ?? false
		});
	}

	return Array.from(merged.values());
}

/**
 * Merge user-uploaded themes from the API into the built-in fallback list and
 * load the active theme's CSS. Built-ins always come from the compiled-in
 * COLOR_SCHEMES (tokens) + static CSS; the API contributes only user themes.
 * Call on app startup. Always loads the active theme's CSS, even when the
 * backend is down or the user has no uploaded themes.
 */
export async function loadThemesFromApi(): Promise<void> {
	try {
		const apiThemes = (await fetchThemes()) ?? [];

		allSchemes.set(mergeThemes(COLOR_SCHEMES, apiThemes));
	} catch {
		// Backend unreachable — built-in themes are already loaded.
	}

	// Always load the active theme's CSS (built-in static or user API),
	// regardless of whether the API call above succeeded.
	await loadThemeCss(get(colorScheme));
}

/**
 * Fetch and cache full theme CSS from the API, then re-apply the scheme.
 * Concurrent calls for the same id share one in-flight promise so the network
 * request is issued only once even when loadThemesFromApi() and the subscribe
 * handler both call this on page load.
 */
export async function loadThemeCss(id: string): Promise<void> {
	if (cachedThemeCss(id) !== undefined) {
		// Already cached — update the scheme object and re-apply
		const schemes = get(allSchemes);
		const scheme = schemes.find((s) => s.id === id);
		if (scheme) {
			scheme.css = cachedThemeCss(id);
			applyScheme(id);
		}
		return;
	}

	if (inFlight.has(id)) {
		return inFlight.get(id);
	}

	const promise = (async () => {
		try {
			const css = await fetchThemeCss(id);
			if (css) {
				cacheThemeCss(id, css);
				// Update the scheme in the store
				allSchemes.update((schemes) => schemes.map((s) => (s.id === id ? { ...s, css } : s)));
			}
			applyScheme(id);
		} catch {
			// Fetch failed — apply without CSS
			applyScheme(id);
		} finally {
			inFlight.delete(id);
		}
	})();

	inFlight.set(id, promise);
	return promise;
}

if (browser) {
	colorScheme.subscribe(async (id) => {
		localStorage.setItem('colorScheme', id);
		// Apply tokens synchronously so there's no flash of default-blue
		// between page load and API response.  loadThemeCss will re-apply
		// with custom CSS once the fetch completes.
		applyScheme(id);
		await loadThemeCss(id);
	});
}
