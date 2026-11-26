import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/testing/render';
import JobMusicTracklist from '../JobMusicTracklist.svelte';

afterEach(cleanup);

const TRACKS = [
	{ number: 1, title: 'Opening', durationLabel: '3:21' },
	{ number: 2, title: 'Track 2', durationLabel: '-' }
];

describe('JobMusicTracklist', () => {
	it('shows the heading with the track count and the column headers', () => {
		renderComponent(JobMusicTracklist, { tracks: TRACKS });
		expect(screen.getByRole('heading', { name: /Tracklist\s*\(2 tracks via MusicBrainz\)/ })).toBeInTheDocument();
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
		expect(within(rows[1]).getByText('Track 2')).toBeInTheDocument();
		expect(within(rows[1]).getByText('-')).toBeInTheDocument();
	});
});
