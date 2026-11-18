// Writes a resolved color scheme onto the document: the inline token
// properties, the dark class, the dataset and the injected theme <style>.
import type { ColorScheme } from '$lib/themes/builtin-schemes';

/**
 * `--color-primary` keeps the same value in light and dark mode, and tokens.css's own `.dark {}`
 * block never redefines it. `--color-primary-dark` in a scheme's `tokens` is
 * a distinct legacy alias role (a fixed darker shade), not "what primary
 * becomes in dark mode" - so it must not be treated as `--color-primary`'s
 * effective-mode twin the way `--color-page-dark`/`--color-surface-dark`/
 * `--color-primary-text-dark`/`--color-primary-light-bg-dark` are.
 */
const MODE_INVARIANT_ROLES = new Set(['--color-primary']);

/**
 * Inline token properties written by the last applyTokens call. Cleared
 * before the next write so a scheme SWITCH does not leak tokens the new
 * scheme never defines: without this, winamp-97's `--font-family:
 * 'Silkscreen', ...` survived on <html> into any scheme chosen after it
 * (craft, default, ...) and pixelated the whole app until a reload.
 */
let appliedTokenProps: string[] = [];

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
 * `.dark {}` keeps handling those.
 */
function applyTokens(root: HTMLElement, scheme: ColorScheme, effectiveDark: boolean) {
	for (const prop of appliedTokenProps) {
		root.style.removeProperty(prop);
	}
	const written: string[] = [];
	for (const [prop, value] of Object.entries(scheme.tokens)) {
		if (prop.endsWith('-dark')) {
			// Legacy paired name: keep writing it unchanged.
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

function injectThemeCss(css: string) {
	const styleId = 'arm-theme-css';
	let el = document.getElementById(styleId) as HTMLStyleElement | null;

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

/** Write a resolved scheme and its CSS onto <html> and <head>. */
export function applySchemeToDocument(scheme: ColorScheme, css: string) {
	const root = document.documentElement;
	const effectiveDark = resolveEffectiveDark(scheme);
	applyTokens(root, scheme, effectiveDark);

	root.dataset.scheme = scheme.id;

	// Inject theme CSS into a managed <style> element
	injectThemeCss(css);

	if (scheme.mode === 'dark') {
		root.classList.add('dark');
	} else if (scheme.mode === 'light') {
		root.classList.remove('dark');
	} else {
		root.classList.toggle('dark', effectiveDark);
	}
}

/** Write the scheme's inline tokens for the live `.dark` class on <html>. */
export function applyTokensForCurrentMode(scheme: ColorScheme) {
	const root = document.documentElement;
	applyTokens(root, scheme, root.classList.contains('dark'));
}
