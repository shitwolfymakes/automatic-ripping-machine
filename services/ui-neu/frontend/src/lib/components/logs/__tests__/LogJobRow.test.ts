import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/testing/render';
import LogJobRowHarness from './LogJobRowHarness.svelte';

const NOW = new Date('2026-06-15T12:00:00Z');
const minutesAgo = (m: number) => new Date(NOW.getTime() - m * 60_000).toISOString();

vi.mock('$lib/stores/dashboard', async () => {
	const { readable } = await import('svelte/store');
	return {
		dashboard: readable({
			drive_names: { drv_1: 'Front Drive' },
			drive_source_kinds: { drv_iso: 'iso' }
		})
	};
});

const JOB = {
	id: 'job_alpha9A41',
	drive_id: 'drv_1',
	disc_type: 'bluray',
	media_type: 'tv',
	season: 1,
	disc_number: 1,
	disc_total: 4,
	status: 'failed',
	title: 'Alpha',
	year: 2001,
	metadata_json: {}
};

function renderRow(job: Record<string, unknown> = {}, logAt?: string) {
	renderComponent(LogJobRowHarness, { job: { ...JOB, ...job } as never, logAt });
	return screen.getByRole('row');
}

describe('LogJobRow', () => {
	beforeEach(() => {
		vi.useFakeTimers({ toFake: ['Date'] });
		vi.setSystemTime(NOW);
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it('links the title to the job log with the short id beneath', () => {
		const row = renderRow();
		expect(within(row).getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', '/logs/job_alpha9A41');
		expect(within(row).getByText('job_9a41')).toHaveAttribute('title', 'job_alpha9A41');
	});

	it('uses the id as the link text when the title is missing', () => {
		const row = renderRow({ title: null });
		expect(within(row).getByRole('link', { name: 'job_alpha9A41' })).toHaveAttribute('href', '/logs/job_alpha9A41');
	});

	it('gives a CD job a square poster and other discs the default one', () => {
		const poster = (row: HTMLElement) => row.querySelector('.logs-panel-title-cell .logs-panel-poster');
		expect(poster(renderRow({ disc_type: 'cd' }))).toHaveClass('logs-panel-poster-square');
		cleanup();
		expect(poster(renderRow())).not.toHaveClass('logs-panel-poster-square');
	});

	it('shows the status badge', () => {
		expect(within(renderRow()).getByText('Failed')).toBeInTheDocument();
	});

	it('shows the job type and disc kind chips', () => {
		const row = renderRow();
		expect(within(row).getByText('Series')).toBeInTheDocument();
		expect(within(row).getByText('Blu-ray')).toBeInTheDocument();
	});

	it('shows the disc kind from the drive source kind', () => {
		const row = renderRow({ drive_id: 'drv_iso' });
		expect(within(row).getByText('ISO')).toBeInTheDocument();
	});

	it('shows the disc position', () => {
		expect(within(renderRow()).getByText('S1 · Disc 1/4')).toBeInTheDocument();
	});

	it('shows a named drive with a tooltip', () => {
		const drive = renderRow().querySelector('[data-label="Drive"] [title]');
		expect(drive).toHaveAttribute('title', 'Front Drive');
		expect(drive).toHaveTextContent('Front Drive');
	});

	it('shows a dash when the job has no drive', () => {
		const cell = renderRow({ drive_id: null }).querySelector('[data-label="Drive"]');
		expect(cell?.textContent?.trim()).toBe('-');
		expect(cell?.querySelector('[title]')).toBeNull();
	});

	it('shows a recent log as relative over absolute', () => {
		const cell = renderRow({}, minutesAgo(42)).querySelector('[data-label="Last modified"]')!;
		expect(within(cell as HTMLElement).getByText('42 min ago')).toBeInTheDocument();
		expect(cell.querySelectorAll('div')).toHaveLength(2);
		expect(cell.querySelector('.logs-panel-small')?.textContent).toMatch(/\d{1,2}:\d{2}/);
	});

	it('shows an old log as the absolute time only', () => {
		const cell = renderRow({}, minutesAgo(60 * 24 * 10)).querySelector('[data-label="Last modified"]')!;
		expect(cell.textContent).not.toMatch(/ago|Yesterday|Just now/);
		expect(cell.textContent?.trim()).toMatch(/\d{1,2}:\d{2}/);
		expect(cell.querySelectorAll('div')).toHaveLength(1);
	});

	it('says there is no log yet when the job has none', () => {
		expect(within(renderRow()).getByText('No log yet')).toBeInTheDocument();
	});
});
