import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, cleanup, within, fireEvent, waitFor } from '$lib/testing/render';
import JobMusicTracklist from '../JobMusicTracklist.svelte';

afterEach(cleanup);

const TRACKS = [
	{ number: 1, title: 'Opening', rawTitle: 'Opening', durationLabel: '3:21' },
	{ number: 2, title: 'Track 2', rawTitle: '', durationLabel: '2:00' }
];

describe('JobMusicTracklist', () => {
	it('shows the heading with the track count and the column headers', () => {
		renderComponent(JobMusicTracklist, { tracks: TRACKS });
		expect(screen.getByRole('heading', { name: /Tracklist\s*\(2 tracks\)/ })).toBeInTheDocument();
		expect(screen.getByText('#')).toBeInTheDocument();
		expect(screen.getByText('Title')).toBeInTheDocument();
		expect(screen.getByText('Duration')).toBeInTheDocument();
	});

	it('renders one row per track with its number, title and duration label', () => {
		renderComponent(JobMusicTracklist, { tracks: TRACKS });
		const rows = screen.getAllByRole('row').slice(1);
		expect(rows).toHaveLength(2);
		expect(within(rows[0]).getByText('1')).toBeInTheDocument();
		expect(within(rows[0]).getByText('Opening')).toBeInTheDocument();
		expect(within(rows[0]).getByText('3:21')).toBeInTheDocument();
		expect(within(rows[1]).getByText('2')).toBeInTheDocument();
		// A track with no stored title shows the blank-field dash.
		expect(within(rows[1]).getByText('-')).toBeInTheDocument();
		expect(within(rows[1]).getByText('2:00')).toBeInTheDocument();
	});
});

describe('JobMusicTracklist editing', () => {
	it('edits a title in place and reports the track number', async () => {
		const onsave = vi.fn().mockResolvedValue(undefined);
		renderComponent(JobMusicTracklist, { tracks: TRACKS, canEdit: true, onsave });
		await fireEvent.click(screen.getByRole('button', { name: 'Edit Track 2 title' }));
		const input = screen.getByRole('textbox');
		await fireEvent.input(input, { target: { value: 'Two' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(onsave).toHaveBeenCalledWith(2, 'Two'));
	});

	it('offers no editors when editing is off', () => {
		renderComponent(JobMusicTracklist, { tracks: TRACKS, canEdit: false, onsave: vi.fn() });
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});
});
