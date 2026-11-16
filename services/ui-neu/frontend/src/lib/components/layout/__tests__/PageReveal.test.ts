import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderComponent, cleanup } from '$lib/testing/render';
import { REVEAL_CAP_MS, REVEAL_SETTLE_MS } from '$lib/ui/page-reveal.svelte';

type NavCallback = (nav: { from: { route: { id: string } } | null; to: { route: { id: string } } | null }) => void;
const nav = vi.hoisted(() => ({ callback: null as NavCallback | null }));
vi.mock('$app/navigation', () => ({
	onNavigate: (cb: NavCallback) => {
		nav.callback = cb;
	}
}));

import PageRevealHarness from './PageRevealHarness.svelte';

function revealer(container: HTMLElement): HTMLElement {
	return container.querySelector('.page-reveal') as HTMLElement;
}

const route = (id: string) => ({ route: { id } });

describe('PageReveal', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it('stays hidden while a panel is pending and reveals once it is not', async () => {
		const { container, rerender } = renderComponent(PageRevealHarness, { props: { pending: true } });
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS * 3);
		expect(revealer(container).dataset.revealed).toBe('false');
		expect(revealer(container)).toHaveAttribute('aria-busy', 'true');
		await rerender({ pending: false });
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS);
		expect(revealer(container).dataset.revealed).toBe('true');
		expect(revealer(container)).toHaveAttribute('aria-busy', 'false');
	});

	it('reveals at the cap when a panel never settles', async () => {
		const { container } = renderComponent(PageRevealHarness, { props: { pending: true } });
		await vi.advanceTimersByTimeAsync(REVEAL_CAP_MS);
		expect(revealer(container).dataset.revealed).toBe('true');
	});

	it('a pending panel that unmounts stops holding the reveal', async () => {
		const { container, rerender } = renderComponent(PageRevealHarness, { props: { pending: true } });
		await rerender({ pending: true, showProbe: false });
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS);
		expect(revealer(container).dataset.revealed).toBe('true');
	});

	it('hides again on a move to another route, not on a param change', async () => {
		const { container } = renderComponent(PageRevealHarness, { props: { pending: false } });
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS);
		nav.callback!({ from: route('/jobs/[id]'), to: route('/jobs/[id]') });
		await vi.advanceTimersByTimeAsync(0);
		expect(revealer(container).dataset.revealed).toBe('true');
		nav.callback!({ from: route('/jobs/[id]'), to: route('/') });
		await vi.advanceTimersByTimeAsync(0);
		expect(revealer(container).dataset.revealed).toBe('false');
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS);
		expect(revealer(container).dataset.revealed).toBe('true');
	});

	it('treats a navigation without route info as a route change', async () => {
		const { container } = renderComponent(PageRevealHarness, { props: { pending: false } });
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS);
		nav.callback!({ from: null, to: route('/') });
		await vi.advanceTimersByTimeAsync(0);
		expect(revealer(container).dataset.revealed).toBe('false');
	});
});
