import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import { updateTrack } from '$lib/api/jobs';
import ReviewTracksTable from '../ReviewTracksTable.svelte';
import type { TrackView } from '$lib/types/api.gen';
import { createJob } from '../../../__fixtures__/job';

vi.mock('$lib/stores/auth', async () => {
	const { readable } = await import('svelte/store');
	return { isAdmin: readable(true), isAuthenticated: readable(true), authStore: readable({ role: 'admin' }) };
});

vi.mock('$lib/api/jobs', () => ({
	updateTrack: vi.fn(() => Promise.resolve({})),
	clearTrackTitle: vi.fn(),
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn()
}));

const track = (o: Partial<TrackView>): TrackView =>
	({ id: 'trk_0', index: 0, source_ref: '0', kind: 'video_title', duration_seconds: null, ...o }) as TrackView;

afterEach(cleanup);

describe('ReviewTracksTable', () => {
	it('shows the scan estimate as the length before the rip', () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job: createJob({ media_type: 'tv' }),
				tracks: [track({ expected_duration_seconds: 3093 })],
				isVideo: true,
				isTv: true,
				isMusic: false
			}
		});
		expect(screen.getByText('51m 33s')).toBeInTheDocument();
		expect(screen.queryByText('--')).toBeNull();
	});

	it('labels an extra instead of showing it as unplaced', () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job: createJob({ media_type: 'tv' }),
				tracks: [
					track({
						id: 'trk_0',
						index: 0,
						source_ref: '0',
						role: 'episode',
						episode_number: 1,
						episode_name: 'The Ripper',
						duration_seconds: 3093
					}),
					track({ id: 'trk_5', index: 5, source_ref: '5', role: 'extra', duration_seconds: 542 }),
					track({ id: 'trk_6', index: 6, source_ref: '6', duration_seconds: 2990 })
				],
				isVideo: true,
				isTv: true,
				isMusic: false
			}
		});
		expect(screen.getByTestId('track-role')).toHaveTextContent('Extra');
		// Every track has an Include box, like the job page.
		expect(screen.getAllByRole('checkbox', { name: /Include track/ })).toHaveLength(3);
		// The placed episode shows its name beside the number, as on the job page.
		expect(screen.getByTestId('track-episode-name')).toHaveTextContent('The Ripper');
		// The episode and the unplaced title keep their number box.
		expect(screen.getAllByPlaceholderText('--')).toHaveLength(2);
	});

	it('shows the generated name as the episode once a session names the track', () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job: createJob({ media_type: 'tv' }),
				tracks: [track({ id: 'trk_0', role: 'episode', episode_number: 1, episode_name: 'The Ripper' })],
				fileNames: new Map([['trk_0', 'Kolchak - S01E01 - The Ripper.mkv']]),
				isVideo: true,
				isTv: true,
				isMusic: false
			}
		});
		expect(screen.getByTestId('track-generated-name')).toHaveTextContent('Kolchak - S01E01 - The Ripper.mkv');
		expect(screen.queryByPlaceholderText('--')).toBeNull();
	});

	it('the Include box leaves a track out of the output', async () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job: createJob({ media_type: 'tv' }),
				tracks: [track({ id: 'trk_0' })],
				isVideo: true,
				isTv: true,
				isMusic: false
			}
		});
		const box = screen.getByRole('checkbox', { name: 'Include track 0' });
		expect(box).toBeChecked();
		await fireEvent.click(box);
		expect(updateTrack).toHaveBeenCalledWith(expect.anything(), 'trk_0', { excluded: true });
	});

	describe('rip copy', () => {
		const GB = 1024 ** 3;
		const four = (o: Partial<TrackView> = {}) =>
			[0, 1, 2, 3].map((i) =>
				track({ id: `trk_${i}`, index: i, source_ref: `${i}`, expected_size_bytes: 10 * GB, excluded: i > 1, ...o })
			);
		const render = (jobOverrides: Parameters<typeof createJob>[0], tracks: TrackView[]) =>
			renderComponent(ReviewTracksTable, {
				props: { job: createJob(jobOverrides), tracks, isVideo: true, isMusic: false }
			});

		it('says a per-title tick rips and transcodes the title', () => {
			render({ status: 'awaiting_review', rip_invocation: 'per_title' }, four());
			const box = screen.getByRole('checkbox', { name: 'Include track 0' });
			expect(box).toHaveAttribute('title', 'Rip and transcode this title');
			expect(box).toBeEnabled();
		});

		it('says an mkv all tick only includes the title in the transcode', () => {
			render({ status: 'awaiting_review', rip_invocation: 'mkv_all' }, four());
			expect(screen.getByRole('checkbox', { name: 'Include track 0' })).toHaveAttribute(
				'title',
				'Include this title in the transcode'
			);
		});

		it('disables the box of a title that was not ripped', () => {
			render({ status: 'ripped', rip_invocation: 'per_title' }, four({ status: 'skipped' }));
			const box = screen.getByRole('checkbox', { name: 'Include track 3' });
			expect(box).toBeDisabled();
			expect(box).not.toBeChecked();
			expect(box).toHaveAttribute('title', 'Not ripped: it was unticked when the rip started');
		});

		it('shows the size column and the per-title totals line', () => {
			render({ status: 'awaiting_review', rip_invocation: 'per_title' }, four());
			expect(screen.getByRole('columnheader', { name: 'Size' })).toBeInTheDocument();
			expect(screen.getAllByText('~10 GB')).toHaveLength(4);
			expect(screen.getByTestId('rip-plan-line')).toHaveTextContent('Rips 2 of 4 titles, about 20 GB');
		});

		it('shows the mkv all totals line, and the transcode count after Start', () => {
			const { unmount } = renderComponent(ReviewTracksTable, {
				props: {
					job: createJob({ status: 'awaiting_review', rip_invocation: 'mkv_all' }),
					tracks: four(),
					isVideo: true,
					isMusic: false
				}
			});
			expect(screen.getByTestId('rip-plan-line')).toHaveTextContent('Rips all 4 titles, about 40 GB. 2 transcode.');
			unmount();
			render({ status: 'ripping', rip_invocation: 'mkv_all' }, four());
			expect(screen.getByTestId('rip-plan-line')).toHaveTextContent('2 of 4 titles transcode');
		});

		it('has no totals line and a plain Include state for scanned titles and non-admins', () => {
			renderComponent(ReviewTracksTable, {
				props: {
					job: createJob({ status: 'awaiting_review' }),
					tracks: [],
					scanTitles: [{ index: 0, duration_seconds: 60, size_bytes: 2048 }],
					isVideo: true,
					isMusic: false
				}
			});
			expect(screen.queryByTestId('rip-plan-line')).toBeNull();
			expect(screen.getByText('~2 KB')).toBeInTheDocument();
			expect(screen.queryByRole('checkbox')).toBeNull();
		});
	});
});
