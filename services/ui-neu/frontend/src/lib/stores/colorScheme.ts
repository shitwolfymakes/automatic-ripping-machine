import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { fetchThemes, fetchTheme } from '$lib/api/themes';
import { COLOR_SCHEMES, DEFAULT_SCHEME, type ColorScheme } from '$lib/themes/builtinSchemes';

/**
 * Built-in scheme ids. Their full CSS ships as static assets in the frontend
 * (static/themes/{id}.css, served same-origin by nginx) — NOT from the backend
 * theme API, which now serves only user-uploaded themes. So theme styling is a
 * pure frontend concern; only uploads round-trip the backend.
 */
const BUILTIN_IDS = new Set(COLOR_SCHEMES.map((s) => s.id));

/** Writable store of all available schemes (built-in + API-loaded) */
export const allSchemes = writable<ColorScheme[]>([...COLOR_SCHEMES]);

/** Cache of full theme data (with CSS) fetched from the API */
const cssCache = new Map<string, string>();

/** In-flight fetch promises keyed by theme id - prevents duplicate concurrent fetches */
const inFlight = new Map<string, Promise<void>>();

function getInitialScheme(): string {
	if (!browser) return DEFAULT_SCHEME.id;
	return localStorage.getItem('colorScheme') ?? DEFAULT_SCHEME.id;
}

/**
 * `--color-primary` keeps the same value in light and dark mode (spec 5.1:
 * "Light default ... Dark default: same"), and tokens.css's own `.dark {}`
 * block never redefines it. `--color-primary-dark` in a scheme's `tokens` is
 * a distinct legacy alias role (a fixed darker shade some unmigrated
 * components read directly via `dark:text-primary-dark`), not "what primary
 * becomes in dark mode" - so it must not be treated as `--color-primary`'s
 * effective-mode twin the way `--color-page-dark`/`--color-surface-dark`/
 * `--color-primary-text-dark`/`--color-primary-light-bg-dark` are.
 */
const MODE_INVARIANT_ROLES = new Set(['--color-primary']);

/**
 * Write the scheme's inline custom-property tokens for the effective mode.
 *
 * Inline `style` on <html> beats every selector in the cascade, including
 * `.dark { --color-page: ...; }` in tokens.css. Each scheme's `tokens` map
 * carries light values under a base name (`--color-surface`) and, for roles
 * that vary by mode, a dark value under the `-dark`-suffixed twin
 * (`--color-surface-dark`). Without this, the inline style always won the
 * base (light) value regardless of dark mode. So for any base role that has
 * a `-dark` twin in this scheme (and is not mode-invariant, see above), write
 * whichever value matches the `effectiveDark` mode; every other token
 * (including the `-dark`-suffixed names themselves, and roles the scheme
 * does not pair, e.g. tones and `--color-border`) is written unchanged, so
 * `.dark {}` keeps handling those and unmigrated `dark:bg-surface-dark`-style
 * utilities keep working.
 */
/**
 * Inline token properties written by the last applyTokens call. Cleared
 * before the next write so a scheme SWITCH does not leak tokens the new
 * scheme never defines: without this, winamp-97's `--font-family:
 * 'Silkscreen', ...` survived on <html> into any scheme chosen after it
 * (craft, default, ...) and pixelated the whole app until a reload.
 */
let appliedTokenProps: string[] = [];

function applyTokens(root: HTMLElement, scheme: ColorScheme, effectiveDark: boolean) {
	for (const prop of appliedTokenProps) {
		root.style.removeProperty(prop);
	}
	const written: string[] = [];
	for (const [prop, value] of Object.entries(scheme.tokens)) {
		if (prop.endsWith('-dark')) {
			// Legacy paired name: keep writing it unchanged for components
			// that still use `dark:bg-surface-dark` etc.
			root.style.setProperty(prop, value);
			written.push(prop);
			continue;
		}
		const darkTwin = MODE_INVARIANT_ROLES.has(prop) ? undefined : scheme.tokens[`${prop}-dark`];
		const effectiveValue = effectiveDark && darkTwin !== undefined ? darkTwin : value;
		root.style.setProperty(prop, effectiveValue);
		written.push(prop);
	}
	appliedTokenProps = written;
}

/**
 * True when <html> is (or is about to be) in dark mode for this scheme.
 * A scheme that locks the mode always wins. Otherwise the user's saved
 * `theme` preference is the authority: the `theme` store (see theme.ts)
 * writes `localStorage.theme` synchronously on every toggle, so it always
 * reflects the user's actual intent for unlocked schemes. Falls back to the
 * OS setting only when nothing has been saved yet.
 *
 * The live `<html class="dark">` state is deliberately NOT consulted here.
 * It can be leftover from a previously active mode-locked scheme (e.g.
 * `lcars`, which forces `dark` regardless of the saved preference) - reading
 * it back would treat "the last scheme forced dark" as "the user wants
 * dark", permanently overriding a saved `light` preference the moment the
 * user leaves a locked scheme.
 */
function resolveEffectiveDark(scheme: ColorScheme): boolean {
	if (scheme.mode === 'dark') return true;
	if (scheme.mode === 'light') return false;
	const saved = localStorage.getItem('theme');
	if (saved === 'dark') return true;
	if (saved === 'light') return false;
	return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function applyScheme(id: string) {
	if (!browser) return;
	const schemes = get(allSchemes);
	const scheme = schemes.find((s) => s.id === id) ?? DEFAULT_SCHEME;
	const root = document.documentElement;
	const effectiveDark = resolveEffectiveDark(scheme);
	applyTokens(root, scheme, effectiveDark);

	root.dataset.scheme = scheme.id;

	// Inject theme CSS into a managed <style> element
	injectThemeCss(scheme);

	if (scheme.mode === 'dark') {
		root.classList.add('dark');
	} else if (scheme.mode === 'light') {
		root.classList.remove('dark');
	} else {
		root.classList.toggle('dark', effectiveDark);
	}
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
	const root = document.documentElement;
	applyTokens(root, scheme, root.classList.contains('dark'));
}

function injectThemeCss(scheme: ColorScheme) {
	const styleId = 'arm-theme-css';
	let el = document.getElementById(styleId) as HTMLStyleElement | null;

	// Get CSS from scheme object or cache
	const css = scheme.css ?? cssCache.get(scheme.id) ?? '';

	if (!css) {
		// No custom CSS — remove any existing injected style
		el?.remove();
		return;
	}

	if (!el) {
		el = document.createElement('style');
		el.id = styleId;
		document.head.appendChild(el);
	}
	el.textContent = css;
}

export const colorScheme = writable<string>(getInitialScheme());

/** True when the active color scheme locks the mode (light or dark) */
export const schemeLocksMode = derived(colorScheme, (id) => {
	const schemes = get(allSchemes);
	const scheme = schemes.find((s) => s.id === id);
	return scheme?.mode != null;
});

/** Fetch a built-in theme's CSS from the frontend's own static assets. */
async function fetchBuiltinCss(id: string): Promise<string> {
	const res = await fetch(`/themes/${encodeURIComponent(id)}.css`);
	if (!res.ok) return '';
	return res.text();
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

		// Build merged list: API (user) themes overlay the built-in fallbacks.
		const merged = new Map<string, ColorScheme>();

		// Start with built-in fallbacks
		for (const s of COLOR_SCHEMES) {
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

		allSchemes.set(Array.from(merged.values()));
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
	if (cssCache.has(id)) {
		// Already cached — update the scheme object and re-apply
		const schemes = get(allSchemes);
		const scheme = schemes.find((s) => s.id === id);
		if (scheme) {
			scheme.css = cssCache.get(id);
			applyScheme(id);
		}
		return;
	}

	if (inFlight.has(id)) {
		return inFlight.get(id);
	}

	const promise = (async () => {
		try {
			// Built-in themes: fetch the bundled static CSS (same-origin, no API).
			// User-uploaded themes: fetch from the backend theme API.
			const css = BUILTIN_IDS.has(id) ? await fetchBuiltinCss(id) : (await fetchTheme(id)).css;
			if (css) {
				cssCache.set(id, css);
				try {
					globalThis.window?.localStorage?.setItem(`theme-cache-v1-${id}`, css);
				} catch {
					// localStorage unavailable or quota exceeded - non-fatal
				}
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
