import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import LiveProgressLine from '../LiveProgressLine.svelte';
import type { LiveSample } from '$lib/live/feeds';

function sample(overrides: Partial<LiveSample> = {}): LiveSample {
	return {
		pct: null,
		etaSeconds: null,
		fps: null,
		avgFps: null,
		pass: null,
		bytesDone: null,
		bytesTotal: null,
		rateBps: null,
		phase: null,
		trackId: null,
		...overrides
	};
}

describe('LiveProgressLine', () => {
	afterEach(cleanup);

	it('shows the bar at the sample percent', () => {
		const { container } = renderComponent(LiveProgressLine, { sample: sample({ pct: 42 }) });
		expect(screen.getByText('42%')).toBeTruthy();
		const fill = container.querySelector<HTMLElement>('[data-progress-fill]');
		expect(fill?.style.getPropertyValue('--progress')).toBe('42%');
		expect(screen.queryByText('Waiting for the first progress report')).toBeNull();
	});

	it('shows the ETA left', () => {
		renderComponent(LiveProgressLine, { sample: sample({ pct: 10, etaSeconds: 1080 }) });
		expect(screen.getByText('18m left')).toBeTruthy();
	});

	it('omits the ETA and transfer when not reported', () => {
		const { container } = renderComponent(LiveProgressLine, { sample: sample({ pct: 10 }) });
		expect(screen.queryByText(/left$/)).toBeNull();
		expect(container.querySelector('.mono')).toBeNull();
	});

	it('shows the transfer line for a byte copy', () => {
		renderComponent(LiveProgressLine, {
			sample: sample({ pct: 50, bytesDone: 1_000_000_000, bytesTotal: 2_000_000_000, rateBps: 50_000_000 })
		});
		expect(screen.getByText(/of .*\/s/)).toBeTruthy();
	});

	it('shows the waiting text before the first sample', () => {
		renderComponent(LiveProgressLine, { sample: null });
		expect(screen.getByText('Waiting for the first progress report')).toBeTruthy();
	});

	it('shows the waiting text when the sample has no percent, or custom text', () => {
		renderComponent(LiveProgressLine, { sample: sample(), waitingText: 'Starting up' });
		expect(screen.getByText('Starting up')).toBeTruthy();
	});

	it('passes the colour to the bar', () => {
		const { container } = renderComponent(LiveProgressLine, {
			sample: sample({ pct: 5 }),
			colorVar: 'var(--color-status-ripping)'
		});
		const fill = container.querySelector<HTMLElement>('[data-progress-fill]');
		expect(fill?.style.getPropertyValue('--progress-color')).toBe('var(--color-status-ripping)');
	});
});
