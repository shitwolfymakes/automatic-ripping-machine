#!/usr/bin/env node
// Visual parity harness for the ui-neu styling cleanup.
// capture: log in, walk every screen in every scheme and viewport, save PNGs.
// diff: compare current/ against baseline/ with pixelmatch; screens listed in
// DEVIATIONS.md are reported but do not fail the run.
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, 'ui-neu-parity');
const require = createRequire(resolve(here, '../services/ui-neu/frontend/package.json'));
const { chromium } = require('playwright');
const { PNG } = require('pngjs');
// pixelmatch@6 is ESM-only; createRequire's CJS interop puts the callable
// export under .default instead of returning it directly.
const pixelmatchModule = require('pixelmatch');
const pixelmatch = pixelmatchModule.default ?? pixelmatchModule;

const args = process.argv.slice(2);
const cmd = args[0];
const opt = (name, dflt) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : dflt; };
const BASE = opt('base', 'http://127.0.0.1:5174');
const USER = opt('user', 'admin');
const PASS = opt('pass', 'password');
const SCHEMES = opt('schemes', 'default,dark,lcars,winamp-97,tactical,hollywood-video-v2').split(',');
const THRESHOLD = Number(opt('threshold', '0.005'));
const VIEWPORTS = { desktop: { width: 1280, height: 900 }, mobile: { width: 390, height: 844 }, wide: { width: 1536, height: 900 } };

// Schemes whose `mode` locks the app to light or dark regardless of the
// user's saved theme preference (see schemeLocksMode in
// src/lib/stores/colorScheme.ts). Derived from COLOR_SCHEMES itself rather
// than hand-listed: a hand-maintained copy silently mis-captures any scheme
// added to it later (hollywood-video-v2 is mode: 'dark' and was missing from
// the old list, so it would have rendered light against dark-only tokens).
const LOCKED_DARK_SCHEMES = new Set(
	[...readFileSync(resolve(here, '../services/ui-neu/frontend/src/lib/stores/colorScheme.ts'), 'utf8')
		.matchAll(/id:\s*'([^']+)',[\s\S]{0,400}?mode:\s*'dark'/g)]
		.map((m) => m[1])
);

// The 400-char window above fails SILENTLY if a scheme definition grows past
// it (the regex simply stops matching that scheme). 'lcars' is a known
// mode: 'dark' scheme and stands in as a sentinel: if it — or the whole
// set — goes missing, the window most likely needs widening.
if (LOCKED_DARK_SCHEMES.size === 0 || !LOCKED_DARK_SCHEMES.has('lcars')) {
	throw new Error(
		'devtools/ui-neu-parity.mjs: LOCKED_DARK_SCHEMES derivation found no ' +
		"locked-dark schemes (or is missing the 'lcars' sentinel). The regex's " +
		"400-char window between a scheme's `id:` and its `mode: 'dark'` is " +
		'likely too narrow for a scheme definition in ' +
		'src/lib/stores/colorScheme.ts — widen the window.'
	);
}

// Each screen: a name and a function that navigates and settles the page.
// Keep these deterministic: no live counters in view, animations finished.
const SCREENS = [
	['dashboard', async (p) => { await p.goto(BASE + '/'); }],
	['job-detail', async (p) => {
		await p.goto(BASE + '/');
		// The dashboard's job cards populate from an async fetch after
		// navigation (not present in the initial render), so wait for at
		// least one job link to appear before deciding there isn't one.
		const link = p.locator('a[href^="/jobs/"]').first();
		await link.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
		if (await link.count()) {
			await link.click();
			// The dashboard's job links are client-side (SvelteKit) navigations,
			// not full page loads. Wait for the URL to actually change before
			// moving on, so a slow-to-land navigation can't complete mid-flight
			// during a later screen and clobber it.
			await p.waitForURL(/\/jobs\//, { timeout: 5000 }).catch(() => {});
		}
	}],
	['files', async (p) => { await p.goto(BASE + '/files'); }],
	['logs', async (p) => { await p.goto(BASE + '/logs'); }],
	['notifications', async (p) => { await p.goto(BASE + '/notifications'); }],
	['transcoder', async (p) => { await p.goto(BASE + '/transcoder'); }],
	...['Metadata', 'Ripping', 'Sessions', 'Transcoding', 'Notifications', 'Interface', 'Themes', 'Drives', 'Users', 'System'].map((tab) => [
		`settings-${tab.toLowerCase()}`,
		async (p) => { await gotoSettings(p); await settingsTab(p, tab).click(); }
	]),
	['settings-notifications-add-bash', async (p) => { await gotoSettings(p); await settingsTab(p, 'Notifications').click(); await p.getByRole('button', { name: /add/i }).first().click(); await p.getByRole('radio', { name: /bash/i }).click({ force: true }); }],
	['settings-drives-slideover', async (p) => { await gotoSettings(p); await settingsTab(p, 'Drives').click(); const gear = p.getByRole('button', { name: /settings|configure/i }).first(); if (await gear.count()) await gear.click(); }],
	['login', async (p) => { await p.evaluate(() => { localStorage.removeItem('arm_token'); localStorage.removeItem('arm_role'); }); await p.goto(BASE + '/login'); }],
	['setup', async (p) => { await p.goto(BASE + '/setup'); }],
	// Mobile-only: the sidebar's hamburger drawer, which only mounts below
	// the lg breakpoint. drawer-menu is the default Menu view; drawer-stats
	// clicks the drawer's own Stats tab (MobileStatsPanel).
	['drawer-menu', async (p) => {
		await p.goto(BASE + '/');
		await p.waitForLoadState('networkidle').catch(() => {});
		await p.getByRole('button', { name: 'Toggle sidebar' }).click();
		await p.getByRole('button', { name: 'Menu', exact: true }).waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
	}, ['mobile']],
	['drawer-stats', async (p) => {
		await p.goto(BASE + '/');
		await p.waitForLoadState('networkidle').catch(() => {});
		await p.getByRole('button', { name: 'Toggle sidebar' }).click();
		const statsTab = p.getByRole('button', { name: 'Stats', exact: true });
		// The drawer mounts on click; wait for its Stats tab to be visible
		// before clicking, rather than racing the open transition.
		await statsTab.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
		// force: true - the drawer's own <hr> sits immediately below the
		// Menu/Stats toggle row with no explicit height, and geometrically
		// overlaps the Stats button's hit box in some captures (observed
		// consistently on winamp-97/mobile), failing Playwright's
		// actionability check even though a real click lands fine. Same
		// pattern as the settings-notifications-add-bash radio click below.
		await statsTab.click({ force: true });
	}, ['mobile']]
];

// Screens captured only at the wide (2xl, 1536px) viewport, where the
// sidebar's own SidebarStats panel replaces the bottom stats bar
// (`hidden 2xl:block` in +layout.svelte) - everything else at `wide` would
// just duplicate the desktop screen one dp wider, so skip it.
const WIDE_ONLY_SCREENS = new Set(['dashboard', 'settings-system']);

// The sidebar's "Settings" link only exists in the visible DOM at the lg+
// breakpoint (desktop). Below that it's rendered inside the mobile drawer,
// which is only mounted once the hamburger ("Toggle sidebar") button opens
// it. Open the drawer first when the desktop link isn't visible so this
// works at both viewports instead of flaking on mobile.
async function gotoSettings(p) {
	await p.goto(BASE + '/');
	await p.waitForLoadState('networkidle').catch(() => {});
	const desktopLink = p.getByRole('link', { name: 'Settings' });
	if (await desktopLink.first().isVisible().catch(() => false)) {
		await desktopLink.first().click();
	} else {
		await p.getByRole('button', { name: 'Toggle sidebar' }).click();
		await p.getByRole('link', { name: 'Settings' }).last().click();
	}
	// The sidebar's Settings link is a client-side (SvelteKit) navigation, not
	// a full page load. Wait for the URL to actually change to /settings
	// before returning, so callers that immediately query the page (e.g. for
	// a tab labeled "Ripping") don't race a still-rendering dashboard, whose
	// job cards can carry a "Ripping" status badge that matches the same text.
	await p.waitForURL(/\/settings/, { timeout: 5000 }).catch(() => {});
}

// Scope tab lookups to the Settings tab bar itself (nav[aria-label="Settings
// tabs"]) rather than matching text anywhere on the page. An unscoped text
// match (e.g. "Ripping") can also hit a dashboard job card's status badge if
// the previous navigation hasn't finished settling yet, landing the click on
// the wrong element entirely.
function settingsTab(p, label) {
	return p.locator('nav[aria-label="Settings tabs"]').getByText(label, { exact: true });
}

async function login(page) {
	await page.goto(BASE + '/login');
	await page.fill('input[name=username]', USER);
	await page.fill('input[name=password]', PASS);
	await page.click('button[type=submit]');
	await page.waitForTimeout(1200);
}

async function applyScheme(page, scheme) {
	await page.evaluate((s) => {
		localStorage.setItem('colorScheme', s === 'dark' ? 'default' : s);
		localStorage.setItem('theme', s === 'dark' ? 'dark' : 'light');
	}, scheme);
	if (LOCKED_DARK_SCHEMES.has(scheme)) {
		await page.evaluate(() => { localStorage.setItem('theme', 'dark'); });
	}
	await page.reload();
}

// Text patterns produced by live-clock-relative components (TimeAgo,
// CountdownTimer) that read the wall clock at render time. Their text
// necessarily differs between a baseline capture and a current capture run
// minutes or hours apart, even with reducedMotion and transitions disabled.
// Freeze them to a fixed placeholder instead of raising the diff threshold.
const LIVE_CLOCK_PATTERN = /^\d+[smhd] ago$|^(\d+[smhd]\s*)+left$/;

async function freezeLiveClocks(page) {
	await page.evaluate((patternSource) => {
		const pattern = new RegExp(patternSource);
		const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
		const hits = [];
		let node;
		while ((node = walker.nextNode())) {
			const text = node.textContent?.trim();
			if (text && pattern.test(text)) hits.push(node);
		}
		for (const n of hits) n.textContent = n.textContent.replace(/\S.*\S|\S/, '[frozen]');
	}, LIVE_CLOCK_PATTERN.source);
}

// Live host telemetry (BottomStatsBar, SidebarStats, and the mobile stats
// panel it composes) samples CPU%, memory, and per-mount disk usage fresh on
// every capture - inherently non-deterministic between a baseline run and a
// current run, even seconds apart. The real fix is at the network layer (the
// '**/api/system/resources' route intercept in capture(), which fixes every
// response to zeroed-out figures with real mount names/paths passed through
// unchanged) - that's what makes this deterministic, since BottomStatsBar
// mounts in the root layout and keeps polling for the lifetime of the shared
// browser context, so a DOM-only freeze here would otherwise race an
// in-flight or subsequent poll landing after this runs, at any point in a
// long screen-capture loop. This DOM pass is a backstop matching that same
// intercept in case a number ever renders here from something other than
// that endpoint: freeze every number-with-unit text node inside these
// containers to a fixed placeholder, and every progress-fill's --progress
// custom property to 0%.
const STATS_CONTAINER_SELECTOR = '[data-testid="bottom-stats-bar"], [data-sidebar-stats]';
// SidebarStats (and the mobile panel that composes it) appends " free" to
// its per-mount figure ("799.8 GB free"); BottomStatsBar does not. Both
// forms, plus the CPU%% and "used / total GB" shapes, are covered.
const STATS_NUMBER_PATTERN = /^\d+(\.\d+)?\s*(%|GB|MB|TB)?(\s+free)?$|^\d+(\.\d+)?\s*\/\s*\d+(\.\d+)?\s*(GB|MB|TB)$/;

async function freezeLiveStats(page) {
	await page.evaluate(({ containerSelector, patternSource }) => {
		const pattern = new RegExp(patternSource);
		const placeholderFor = (text) => {
			const trimmed = text.trim();
			if (/\//.test(trimmed)) {
				const unit = (trimmed.match(/(GB|MB|TB)\s*$/) || [])[1];
				return unit ? `0 / 0 ${unit}` : '0 / 0';
			}
			const suffix = trimmed.match(/(%|GB|MB|TB)(\s+free)?\s*$/);
			const unit = suffix?.[1];
			const free = suffix?.[2] ? ' free' : '';
			return unit ? `0${unit === '%' ? '' : ' '}${unit}${free}` : '0';
		};
		for (const container of document.querySelectorAll(containerSelector)) {
			const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
			const hits = [];
			let node;
			while ((node = walker.nextNode())) {
				const text = node.textContent?.trim();
				if (text && pattern.test(text)) hits.push(node);
			}
			for (const n of hits) n.textContent = placeholderFor(n.textContent);
			for (const fill of container.querySelectorAll('.progress-fill')) {
				fill.style.setProperty('--progress', '0%');
			}
		}
	}, { containerSelector: STATS_CONTAINER_SELECTOR, patternSource: STATS_NUMBER_PATTERN.source });
}

async function settle(page) {
	await page.waitForLoadState('networkidle').catch(() => {});
	await page.evaluate(() => document.fonts?.ready);
	// Poster images use loading="lazy"; native lazy-load timing depends on
	// the browser's own viewport-relative heuristic, which can differ by
	// viewport size (e.g. the `wide` viewport) and race a fixed settle
	// delay, leaving an image mid-load (falls back to the placeholder icon)
	// at screenshot time. Force every already-attached <img> to finish
	// loading (or error) before continuing.
	await page.evaluate(() => Promise.all(
		Array.from(document.images).map((img) =>
			img.complete ? Promise.resolve() : new Promise((res) => {
				img.addEventListener('load', res, { once: true });
				img.addEventListener('error', res, { once: true });
			})
		)
	)).catch(() => {});
	await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }' });
	await page.waitForTimeout(400);
	await freezeLiveClocks(page);
	await freezeLiveStats(page);
}

// A screen runs at a given viewport unless its own onlyViewports list (3rd
// tuple element) excludes it, or the viewport is `wide` and the screen isn't
// in WIDE_ONLY_SCREENS (wide only adds the two screens that actually render
// differently there; everything else would just duplicate desktop).
function screenRunsAt(name, onlyViewports, vpName) {
	if (onlyViewports && !onlyViewports.includes(vpName)) return false;
	if (vpName === 'wide' && !WIDE_ONLY_SCREENS.has(name)) return false;
	return true;
}

async function capture(dirName, routesFilter) {
	const out = resolve(root, dirName);
	mkdirSync(out, { recursive: true });
	const browser = await chromium.launch();
	for (const scheme of SCHEMES) {
		for (const [vpName, vp] of Object.entries(VIEWPORTS)) {
			const screensThisViewport = SCREENS.filter(([name, , onlyViewports]) =>
				screenRunsAt(name, onlyViewports, vpName) && (!routesFilter || routesFilter.includes(name))
			);
			if (!screensThisViewport.length) continue;
			const ctx = await browser.newContext({ viewport: vp, ignoreHTTPSErrors: true, reducedMotion: 'reduce' });
			// Cover art is a live third-party fetch (posterSrc() in
			// src/lib/utils/poster.ts routes every external poster through the
			// backend's /api/images/proxy). Whether it arrives before the
			// screenshot varies run to run, so abort it on every context: the
			// <img> onerror handler then swaps in the local placeholder, which
			// renders identically in baseline and current.
			await ctx.route('**/api/images/proxy*', (r) => r.abort());
			// BottomStatsBar mounts in the root layout and polls
			// /api/system/resources every 5s for the lifetime of the browser
			// context (every screen in this scheme+viewport loop shares one
			// page). Freezing the DOM after the fact races that poll - the
			// numbers can change between any two screens, and the very first
			// load can resolve at any point relative to a screen's own settle
			// pass, intermittently clobbering the freeze before the
			// screenshot (observed on the baseline re-seed, not just
			// `current`). Fix it at the source instead: intercept the route
			// so every response has the same fixed, zeroed-out figures - real
			// mount names/paths pass through unchanged (so the label text
			// still matches the actual environment), only the numbers differ.
			await ctx.route('**/api/system/resources', async (route) => {
				const res = await route.fetch();
				let body;
				try { body = await res.json(); } catch { return route.continue(); }
				const zeroMount = (m) => ({ ...m, total_gb: 0, used_gb: 0, free_gb: 0, percent: 0 });
				await route.fulfill({
					response: res,
					json: {
						...body,
						cpu_percent: 0,
						cpu_temp: 0,
						memory: { total_gb: 0, used_gb: 0, free_gb: 0, percent: 0 },
						storage: (body.storage ?? []).map(zeroMount)
					}
				});
			});
			const page = await ctx.newPage();
			await login(page);
			await applyScheme(page, scheme);
			for (const [name, go] of screensThisViewport) {
				try {
					await go(page);
					await settle(page);
					await page.screenshot({ path: resolve(out, `${scheme}__${vpName}__${name}.png`), fullPage: true });
					process.stdout.write(`captured ${scheme}/${vpName}/${name}\n`);
				} catch (e) {
					process.stdout.write(`SKIP ${scheme}/${vpName}/${name}: ${String(e).split('\n')[0]}\n`);
				}
				if (name === 'login') await login(page);
			}
			await ctx.close();
		}
	}
	await browser.close();
}

function deviations() {
	const p = resolve(root, 'DEVIATIONS.md');
	if (!existsSync(p)) return new Set();
	return new Set(readFileSync(p, 'utf8').split('\n').filter((l) => l.startsWith('- `')).map((l) => l.slice(3, l.indexOf('`', 3))));
}

// Diff-time mask: the app header's live-activity cluster (the "N ripping /
// N transcoding / N notifications" counts in .layout-activity-group). Task 5
// collapsed those three bespoke shades onto the semantic roles
// (indigo-600 -> --color-status-transcoding, blue -> --color-status-ripping,
// amber-600 -> --color-warning), an accepted, app-wide token collapse that
// therefore contributes a constant slice of diff to EVERY screen that renders
// the desktop header. The rectangles below are zeroed identically in both
// images before pixelmatch so that accepted collapse cannot mask, or be
// mistaken for, a real per-screen regression. Bounds were measured from the
// live DOM (getBoundingClientRect on .layout-activity-ripping /
// -transcoding / -notification) and cross-checked against the flagged-pixel
// bounding box in baseline/default__desktop__dashboard.png and
// baseline/default__wide__dashboard.png (x 601-872, y 22-34), then padded by
// 2px for glyph antialiasing. The cluster lives in .layout-stats-bar, which is
// `hidden lg:flex` - it does not render at the 390px mobile viewport at all,
// so `mobile` has no mask region. Mask nothing else.
const HEADER_ACTIVITY_MASK = {
	desktop: [{ x: 597, y: 17, w: 280, h: 23 }],
	wide: [{ x: 597, y: 17, w: 280, h: 23 }],
	mobile: []
};

// Zero the masked rectangles in an RGBA buffer in place, so both images carry
// identical bytes there and pixelmatch reports no difference for those pixels.
function applyMask(png, rects) {
	for (const { x, y, w, h } of rects) {
		for (let py = Math.max(0, y); py < Math.min(png.height, y + h); py++) {
			for (let px = Math.max(0, x); px < Math.min(png.width, x + w); px++) {
				const i = (py * png.width + px) * 4;
				png.data[i] = 0; png.data[i + 1] = 0; png.data[i + 2] = 0; png.data[i + 3] = 255;
			}
		}
	}
}

function diff(schemesFilter) {
	const base = resolve(root, 'baseline');
	const cur = resolve(root, 'current');
	const out = resolve(root, 'diff');
	mkdirSync(out, { recursive: true });
	const allowed = deviations();
	const rows = [];
	let failed = 0;
	const prefixes = schemesFilter ? schemesFilter.map((s) => `${s}__`) : null;
	const matchesFilter = (file) => !prefixes || prefixes.some((p) => file.startsWith(p));
	for (const file of readdirSync(base).filter((f) => f.endsWith('.png') && matchesFilter(f)).sort()) {
		const curPath = resolve(cur, file);
		if (!existsSync(curPath)) { rows.push([file, 'MISSING', '']); failed++; continue; }
		const a = PNG.sync.read(readFileSync(resolve(base, file)));
		const b = PNG.sync.read(readFileSync(curPath));
		if (a.width !== b.width || a.height !== b.height) {
			rows.push([file, `SIZE ${a.width}x${a.height} vs ${b.width}x${b.height}`, allowed.has(file) ? 'allowed' : 'FAIL']);
			if (!allowed.has(file)) failed++;
			continue;
		}
		const maskRects = HEADER_ACTIVITY_MASK[file.split('__')[1]] ?? [];
		applyMask(a, maskRects);
		applyMask(b, maskRects);
		const d = new PNG({ width: a.width, height: a.height });
		const n = pixelmatch(a.data, b.data, d.data, a.width, a.height, { threshold: 0.1 });
		const ratio = n / (a.width * a.height);
		const verdict = ratio <= THRESHOLD ? 'ok' : allowed.has(file) ? 'allowed' : 'FAIL';
		if (verdict === 'FAIL') failed++;
		if (verdict !== 'ok') writeFileSync(resolve(out, file), PNG.sync.write(d));
		rows.push([file, (ratio * 100).toFixed(3) + '%', verdict]);
	}
	const width = rows.length ? Math.max(...rows.map((r) => r[0].length)) : 0;
	for (const [f, v, s] of rows) process.stdout.write(`${f.padEnd(width)}  ${v.padStart(8)}  ${s}\n`);
	process.stdout.write(`\n${rows.length} screens, ${failed} failing (threshold ${THRESHOLD * 100}%)\n`);
	process.exit(failed ? 1 : 0);
}

// --schemes filters diff's baseline/current comparison to files whose name
// starts with one of the given scheme ids (the `<scheme>__` filename
// prefix written by capture()). Not passed: compare every captured file.
const diffSchemesRaw = opt('schemes', null);
const diffSchemes = diffSchemesRaw ? diffSchemesRaw.split(',').filter(Boolean) : null;

// --routes filters capture to only the named screens (by SCREENS entry
// name), so a run against a different base URL (e.g. the untouched tree,
// to seed baseline/ with screens this branch added) can ADD just those
// files without touching or deleting anything else already in the target
// directory. Not passed: capture every screen (each still subject to its
// own viewport restriction).
const captureRoutesRaw = opt('routes', null);
const captureRoutes = captureRoutesRaw ? captureRoutesRaw.split(',').filter(Boolean) : null;

if (cmd === 'capture') await capture(args[1] || 'current', captureRoutes);
else if (cmd === 'diff') diff(diffSchemes);
else { console.error('usage: ui-neu-parity.mjs capture <baseline|current> [--routes a,b] | diff [--schemes a,b]'); process.exit(2); }
