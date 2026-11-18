import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import { REVEAL_SETTLE_MS } from '$lib/ui/page-reveal.svelte';

vi.mock('$app/navigation', () => ({ onNavigate: vi.fn() }));

import HoldUntilHarness from './HoldUntilHarness.svelte';

function revealed(container: HTMLElement): string | undefined {
	return (container.querySelector('.page-reveal') as HTMLElement).dataset.revealed;
}

describe('HoldUntil', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it('draws nothing and holds the page reveal until ready', async () => {
		const { container, rerender } = renderComponent(HoldUntilHarness, { props: { ready: false } });
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS * 3);
		expect(screen.queryByText('held content')).toBeNull();
		expect(revealed(container)).toBe('false');

		await rerender({ ready: true });
		await vi.advanceTimersByTimeAsync(REVEAL_SETTLE_MS);
		expect(screen.getByText('held content')).toBeInTheDocument();
		expect(revealed(container)).toBe('true');
	});

	it('renders no wrapper element around its content', async () => {
		const { container } = renderComponent(HoldUntilHarness, { props: { ready: true } });
		const held = screen.getByText('held content');
		expect(held.parentElement).toBe(container.querySelector('.page-reveal'));
	});
});
