import { describe, it, expect, vi, beforeEach } from 'vitest';

function fakeNode(): Element {
	const el = document.createElement('div');
	document.body.appendChild(el);
	return el;
}

describe('transitions', () => {
	beforeEach(() => {
		vi.resetModules();
	});

	it('exports send and receive from crossfade', async () => {
		const mod = await import('../transitions');
		expect(typeof mod.send).toBe('function');
		expect(typeof mod.receive).toBe('function');
	});

	it('panel fades: duration 200 and opacity-only css when reduced-motion is not set', async () => {
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
		const mod = await import('../transitions');
		const cfg = mod.panel(fakeNode(), {});
		expect(cfg.duration).toBe(200);
		const css = cfg.css!(0.5, 0.5);
		expect(css).toContain('opacity');
		expect(css).not.toContain('height');
	});

	it('panel has duration 0 when reduced-motion is preferred', async () => {
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
		const mod = await import('../transitions');
		expect(mod.panel(fakeNode(), {}).duration).toBe(0);
	});

	it('expand slides: css animates height, duration 200 by default', async () => {
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
		const mod = await import('../transitions');
		const cfg = mod.expand(fakeNode(), {});
		expect(cfg.duration).toBe(200);
		expect(cfg.css!(0.5, 0.5)).toContain('height');
	});

	it('expand has duration 0 when reduced-motion is preferred', async () => {
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
		const mod = await import('../transitions');
		expect(mod.expand(fakeNode(), {}).duration).toBe(0);
	});
});
