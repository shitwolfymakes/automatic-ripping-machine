import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderComponent, cleanup, screen } from '$lib/testing/render';
import { REVEAL_CAP_MS, REVEAL_SETTLE_MS } from '$lib/stores/page-reveal.svelte';
import { SKELETON_MIN_SHOW_MS } from '$lib/stores/skeleton-gate.svelte';

type NavCallback = (nav: { from: { route: { id: string } } | null; to: { route: { id: string } } | null }) => void;
const nav = vi.hoisted(() => ({ callback: null as NavCallback | null }));
vi.mock('$app/navigation', () => ({
	onNavigate: (cb: NavCallback) => {
		nav.callback = cb;
	}
}));

import PageRevealHarness from './PageRevealHarness.svelte';
import LoadStateRevealHarness from './LoadStateRevealHarness.svelte';

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

describe('PageReveal with a LoadState', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it('reveals with the data, not the skeleton, when the data lands after the skeleton delay', async () => {
		const { container, rerender } = renderComponent(LoadStateRevealHarness, { props: { data: null } });
		await vi.advanceTimersByTimeAsync(450);
		await rerender({ data: 'x' });
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS);
		expect(revealer(container).dataset.revealed).toBe('true');
		expect(screen.getByText('READY')).toBeInTheDocument();
		expect(screen.queryByText('LOADING')).toBeNull();
	});

	it('keeps a skeleton revealed at the cap for the minimum time from the reveal', async () => {
		const { container, rerender } = renderComponent(LoadStateRevealHarness, { props: { data: null } });
		await vi.advanceTimersByTimeAsync(REVEAL_CAP_MS);
		expect(revealer(container).dataset.revealed).toBe('true');
		await vi.advanceTimersByTimeAsync(100);
		await rerender({ data: 'x' });
		await vi.advanceTimersByTimeAsync(SKELETON_MIN_SHOW_MS - 100 - 1);
		expect(screen.getByText('LOADING')).toBeInTheDocument();
		await vi.advanceTimersByTimeAsync(1);
		expect(screen.getByText('READY')).toBeInTheDocument();
	});
});
