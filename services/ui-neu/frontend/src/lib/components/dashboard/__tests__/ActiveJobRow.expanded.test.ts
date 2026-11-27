// The expanded panel repeats nothing the row already says and reads the same
// live progress as the row's header.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, within } from '$lib/testing/render';
import ActiveJobRow from '../ActiveJobRow.svelte';
import { createJob } from '../../../__fixtures__/job';

const live = vi.hoisted(() => ({
	value: {
		rip: {
			pct: 3,
			etaSeconds: 3660,
			fps: null,
			avgFps: null,
			pass: null,
			bytesDone: null,
			bytesTotal: null,
			rateBps: null,
			phase: null
		},
		transcode: null
	} as Record<string, unknown>
}));
vi.mock('$lib/stores/job-live.svelte', () => ({
	jobLive: { watch: vi.fn(() => () => {}), get: vi.fn(() => live.value) }
}));

async function renderExpanded() {
	const job = createJob({
		title: 'Indiana Jones and the Last Crusade',
		disc_type: 'bluray',
		poster_url: 'http://x/p.jpg',
		rip_progress: {
			tracks_total: 4,
			tracks_done: 0,
			tracks_failed: 0,
			current_track_id: null,
			current_track_index: null
		}
	});
	const { container } = renderComponent(ActiveJobRow, { props: { job } });
	await fireEvent.click(screen.getByRole('button', { name: 'Expand' }));
	return container;
}

describe('ActiveJobRow expanded panel', () => {
	afterEach(cleanup);

	it('names the disc type once per place it shows it', async () => {
		const container = await renderExpanded();
		expect(screen.queryAllByRole('img', { name: 'Blu-ray' })).toHaveLength(0);
		expect(container.textContent?.match(/Blu-ray/g)).toHaveLength(2);
	});

	it('names the title once in the panel', async () => {
		await renderExpanded();
		const panel = screen.getByText('Job ID').closest('div.flex') as HTMLElement;
		expect(within(panel).getAllByText(/Last Crusade/)).toHaveLength(1);
		expect(within(panel).queryByRole('img', { name: /Last Crusade/ })).toBeNull();
	});

	it('shows the header progress in the Progress cell', async () => {
		await renderExpanded();
		const cell = screen.getByText('Progress', { selector: 'td' }).nextElementSibling as HTMLElement;
		expect(cell).toHaveTextContent('1h 1m left');
	});
});
