import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent, within } from '$lib/testing/render';
import JobTracksTable from '../JobTracksTable.svelte';
import { createJob, createTrack } from '$lib/__fixtures__/job';
import type { NamingPreviewItem, TrackView } from '$lib/types/api.gen';
import { searchMetadata, updateTrack } from '$lib/api/jobs';
import * as authStore from '$lib/stores/auth';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper - not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/jobs', () => ({
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	clearTrackTitle: vi.fn(),
	updateTrack: vi.fn()
}));

const setRole = (authStore as unknown as { __setRole: (r: string | null) => void }).__setRole;

const onexcludedchange = vi.fn();
const ontitleapplied = vi.fn();

interface Overrides {
	tracksAreSeries?: boolean;
	previews?: NamingPreviewItem[];
	excludeError?: { trackId: string; message: string } | null;
}

function renderTable(tracks: TrackView[], overrides: Overrides = {}) {
	return renderComponent(JobTracksTable, {
		job: createJob({}),
		tracks,
		tracksAreSeries: overrides.tracksAreSeries ?? false,
		previewByTrack: new Map((overrides.previews ?? []).map((p) => [p.track_id, p])),
		onexcludedchange,
		excludeError: overrides.excludeError,
		ontitleapplied
	});
}

const text = (el: HTMLElement) => (el.textContent ?? '').replace(/\s+/g, ' ').trim();
const trackRows = () => Array.from(document.querySelectorAll<HTMLElement>('tr.table-row'));
const cellOf = (row: HTMLElement, label: string) => row.querySelector<HTMLElement>(`td[data-label="${label}"]`)!;
const titleButtonOf = (row: HTMLElement) => within(cellOf(row, 'Title')).getByRole('button');

const series = () => [
	createTrack({ id: 'trk_1', index: 1, title: 'Pilot', status: 'done' }),
	createTrack({ id: 'trk_2', index: 2, title: null, excluded: true, status: 'failed', last_error: 'MakeMKV exited 1' }),
	createTrack({ id: 'trk_3', index: 3, title: null, status: 'done' })
];

beforeEach(() => {
	setRole('admin');
	vi.clearAllMocks();
});

afterEach(() => {
	cleanup();
});

describe('JobTracksTable', () => {
	it('titles the table with the track count', () => {
		renderTable(series());
		expect(screen.getByText('Tracks (3)')).toBeInTheDocument();
	});

	it('has the Episode column only for a series', () => {
		renderTable(series(), { tracksAreSeries: true });
		const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
		expect(headers.slice(0, 5)).toEqual(['#', 'Kind', 'Title', 'Episode', 'Filename']);
		cleanup();
		renderTable([createTrack({ id: 'trk_1', status: 'done' })]);
		expect(screen.queryByRole('columnheader', { name: 'Episode' })).not.toBeInTheDocument();
	});

	it('renders one row per track and hands each its own preview', () => {
		renderTable(series(), {
			previews: [
				{
					track_id: 'trk_1',
					track_number: 1,
					output_path: 'Dir/One.mkv',
					output_dir: 'Dir',
					output_name: 'One.mkv'
				}
			]
		});
		const rows = trackRows();
		expect(rows).toHaveLength(3);
		expect(text(cellOf(rows[0], 'Filename'))).toBe('One.mkv');
		expect(text(cellOf(rows[2], 'Filename'))).toBe('-');
	});

	it('passes the exclusion change on from a row', async () => {
		renderTable(series());
		await fireEvent.click(screen.getAllByRole('checkbox')[1]);
		expect(onexcludedchange).toHaveBeenLastCalledWith('trk_2', false);
	});

	it('shows a failed exclusion change on its own row only', () => {
		renderTable(series(), { excludeError: { trackId: 'trk_2', message: 'denied' } });
		const rows = trackRows();
		expect(text(cellOf(rows[1], 'Include'))).toBe('denied');
		expect(text(cellOf(rows[0], 'Include'))).toBe('');
		expect(screen.getAllByRole('alert')).toHaveLength(1);
	});

	it('moves the exclusion error and the track count with the props', async () => {
		const props = {
			job: createJob({}),
			tracks: series(),
			tracksAreSeries: false,
			previewByTrack: new Map(),
			onexcludedchange,
			ontitleapplied
		};
		const { rerender } = renderComponent(JobTracksTable, {
			...props,
			excludeError: { trackId: 'trk_2', message: 'denied' }
		});
		await rerender({ ...props, tracks: series().slice(0, 2), excludeError: { trackId: 'trk_1', message: 'nope' } });
		expect(screen.getByText('Tracks (2)')).toBeInTheDocument();
		expect(text(cellOf(trackRows()[0], 'Include'))).toBe('nope');
		expect(text(cellOf(trackRows()[1], 'Include'))).toBe('');
	});

	it('shows no exclusion error when none is given', () => {
		renderTable(series());
		expect(screen.queryByRole('alert')).not.toBeInTheDocument();
	});

	describe('per-track title search', () => {
		const picked = { title: 'Picked', year: 2001, kind: 'movie', poster_url: null, provider_id: 'tt3333' };
		const two = () => [createTrack({ id: 'trk_1', status: 'done' }), createTrack({ id: 'trk_2', index: 1 })];

		it('opens under the row when an admin clicks the title cell and closes on the next click', async () => {
			renderTable([createTrack({ id: 'trk_1', status: 'done' })]);
			const cell = titleButtonOf(trackRows()[0]);
			await fireEvent.click(cell);
			expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
			await fireEvent.click(cell);
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});

		it('moves from one track to another when a second title cell is clicked', async () => {
			renderTable(two());
			const rows = trackRows();
			await fireEvent.click(titleButtonOf(rows[0]));
			await fireEvent.click(titleButtonOf(rows[1]));
			expect(screen.getAllByRole('button', { name: 'Search' })).toHaveLength(1);
		});

		it('closes from its close button', async () => {
			renderTable(two());
			await fireEvent.click(titleButtonOf(trackRows()[0]));
			await fireEvent.click(screen.getByTitle('Close'));
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});

		it('closes on applying a match and calls ontitleapplied', async () => {
			vi.mocked(searchMetadata).mockResolvedValue({ candidates: [picked] });
			vi.mocked(updateTrack).mockResolvedValue(undefined as never);
			renderTable(two());
			await fireEvent.click(titleButtonOf(trackRows()[0]));
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByText('Picked'));
			await fireEvent.click(await screen.findByRole('button', { name: 'Apply' }));
			await waitFor(() => expect(ontitleapplied).toHaveBeenCalledTimes(1));
			await waitFor(() => expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument());
		});

		it('opens nothing when a guest clicks a title cell', async () => {
			setRole('guest');
			renderTable(two());
			expect(within(cellOf(trackRows()[0], 'Title')).queryByRole('button')).not.toBeInTheDocument();
			await fireEvent.click(cellOf(trackRows()[0], 'Title'));
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});
	});
});
