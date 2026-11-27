import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import DiscReviewWidget from '../DiscReviewWidget.svelte';
import { createJob, createTrack } from '../../../__fixtures__/job';
import type { TrackView } from '$lib/types/api.gen';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return { role: { subscribe: _role.subscribe }, isAdmin: derived(_role, (r) => r === 'admin') };
});

const server = vi.hoisted(() => ({ tracks: [] as TrackView[] }));

vi.mock('$lib/api/jobs', async () => {
	const { createJob } = await import('../../../__fixtures__/job');
	const job = () => createJob({ status: 'awaiting_review', rip_invocation: 'mkv_all' });
	return {
		fetchJob: vi.fn(() => Promise.resolve({ job: job(), tracks: server.tracks, fingerprints: [] })),
		fetchNamingPreview: vi.fn(() => Promise.resolve({ items: [] })),
		updateTrack: vi.fn((_id: string, trackId: string, data: { excluded?: boolean }) => {
			server.tracks = server.tracks.map((t) => (t.id === trackId ? { ...t, ...data } : t));
			return Promise.resolve(job());
		})
	};
});
vi.mock('$lib/api/sessions', () => ({ fetchSessions: vi.fn(() => Promise.resolve([])) }));
vi.mock('$lib/api/iso', () => ({ cancelIsoRip: vi.fn() }));

function video(i: number, excluded: boolean) {
	return createTrack({
		id: `trk_${i}`,
		index: i,
		kind: 'video_title',
		source_ref: `0000${i}.mpls`,
		excluded,
		expected_size_bytes: 1_000_000_000
	});
}

describe('DiscReviewWidget tick counts', () => {
	afterEach(() => cleanup());

	it('updates the Rip row and the totals line right after a title is unticked', async () => {
		server.tracks = [video(0, false), video(1, false), video(2, true), video(3, true)];
		renderComponent(DiscReviewWidget, {
			props: { job: createJob({ status: 'awaiting_review', rip_invocation: 'mkv_all' }), paused: false }
		});
		await waitFor(() => expect(screen.getByTestId('rip-row')).toHaveTextContent(/Rips all 4 titles.*2 transcode/));
		await fireEvent.click(screen.getByRole('button', { name: 'Info' }));
		await waitFor(() =>
			expect(screen.getByTestId('rip-plan-line')).toHaveTextContent(/Rips all 4 titles.*2 transcode/)
		);

		await fireEvent.click(screen.getByRole('checkbox', { name: 'Include track 1' }));

		await waitFor(() => expect(screen.getByTestId('rip-row')).toHaveTextContent(/Rips all 4 titles.*1 transcode/));
		expect(screen.getByTestId('rip-plan-line')).toHaveTextContent(/Rips all 4 titles.*1 transcode/);
	});
});
