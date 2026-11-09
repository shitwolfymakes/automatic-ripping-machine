import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/test-utils';
import type { TranscodeStatsView } from '$lib/types/api.gen';
import TranscoderStatTiles from '../TranscoderStatTiles.svelte';

function makeStats(overrides: Partial<TranscodeStatsView> = {}): TranscodeStatsView {
	return {
		tasks_by_status: {},
		total_tasks: 0,
		gpus_total: 1,
		gpus_available: 1,
		max_parallel: 2,
		...overrides
	} as TranscodeStatsView;
}

function tileValues(container: HTMLElement): Record<string, string> {
	const out: Record<string, string> = {};
	for (const tile of container.querySelectorAll('.stat')) {
		out[tile.querySelector('.stat-label')!.textContent!.trim()] = tile
			.querySelector('.stat-value')!
			.textContent!.trim();
	}
	return out;
}

describe('TranscoderStatTiles', () => {
	afterEach(() => cleanup());

	it('shows each status count from tasks_by_status and the total from total_tasks', () => {
		const { container } = renderComponent(TranscoderStatTiles, {
			stats: makeStats({
				tasks_by_status: { queued: 3, in_progress: 2, done: 7, failed: 1 },
				total_tasks: 13
			})
		});
		expect(tileValues(container)).toEqual({
			Queued: '3',
			'In Progress': '2',
			Done: '7',
			Failed: '1',
			Total: '13'
		});
	});

	it('shows 0 for a status missing from tasks_by_status', () => {
		const { container } = renderComponent(TranscoderStatTiles, {
			stats: makeStats({ tasks_by_status: { done: 4 }, total_tasks: 4 })
		});
		expect(tileValues(container)).toEqual({
			Queued: '0',
			'In Progress': '0',
			Done: '4',
			Failed: '0',
			Total: '4'
		});
	});
});
