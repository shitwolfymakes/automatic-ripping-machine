import type { JobDetailView, TitlesReadView, TrackView } from '$lib/types/api.gen';
import { createJob, createTrack } from './job';

const GB = 1_000_000_000;

/**
 * A 3D Blu-ray with every title class, as the review card lists it (genericized from a real disc).
 * Two playlists (00095, 00096) are in the structure but MakeMKV does not list them (unrippable).
 * The feature is 00334 with two angles; 00342 is the same film without chapters; 00343 is its 2D twin;
 * 00400 is a longer cut (an edition); 00103 copies the extra; 00500 replays the feature's clips (a decoy);
 * 00335 is the feature plus a short intro (a variant). The 2D twin has two angles of its own.
 */
export function bladeRunnerTracks(): TrackView[] {
	const t = (index: number, ref: string, over: Partial<TrackView>): TrackView =>
		createTrack({
			id: `trk_${index}`,
			index,
			source_ref: ref,
			source_file: ref.split(':')[0],
			title: 'Feature Title',
			year: 2017,
			title_class: 'primary',
			status: 'queued',
			duration_seconds: null,
			expected_size_bytes: 40 * GB,
			expected_duration_seconds: 9807,
			...over
		});
	return [
		t(0, '00095.mpls', {
			excluded: true,
			unrippable: true,
			stereo_3d: true,
			expected_duration_seconds: 4680,
			expected_size_bytes: 25.7 * GB
		}),
		t(1, '00096.mpls', {
			excluded: true,
			unrippable: true,
			stereo_3d: true,
			expected_duration_seconds: 4620,
			expected_size_bytes: 25 * GB
		}),
		t(2, '00102.mpls', { expected_duration_seconds: 287, expected_size_bytes: 0.3 * GB }),
		t(3, '00334.mpls:1', { stereo_3d: true }),
		t(4, '00334.mpls:2', { stereo_3d: true, title_class: 'angle', title_class_ref: '00334.mpls:1', excluded: true }),
		t(5, '00342.mpls', {
			stereo_3d: true,
			title_class: 'subset',
			title_class_ref: '00334.mpls:1',
			excluded: true,
			expected_duration_seconds: 9698
		}),
		t(6, '00343.mpls:1', { title_class: 'view', title_class_ref: '00334.mpls:1', excluded: true }),
		t(7, '00335.mpls', {
			stereo_3d: true,
			title_class: 'variant',
			title_class_ref: '00334.mpls:1',
			excluded: true,
			expected_duration_seconds: 9852
		}),
		t(8, '00400.mpls', { title_class: 'edition', expected_duration_seconds: 10500 }),
		t(9, '00103.mpls', {
			title_class: 'duplicate',
			title_class_ref: '00102.mpls',
			excluded: true,
			expected_duration_seconds: 287,
			expected_size_bytes: 0.3 * GB
		}),
		t(10, '00500.mpls', {
			title_class: 'decoy',
			title_class_ref: '00334.mpls:1',
			excluded: true,
			stereo_3d: true
		}),
		t(11, '00343.mpls:2', { title_class: 'angle', title_class_ref: '00334.mpls:1', excluded: true })
	];
}

/** The disc's review-card detail: a movie job at the review gate holding `bladeRunnerTracks()`. */
export function bladeRunnerDetail(titles: TitlesReadView = { state: 'ready' }): JobDetailView {
	const job = createJob({
		status: 'awaiting_review',
		disc_type: 'bluray',
		rip_invocation: 'per_title',
		media_type: 'movie',
		title: 'Feature Title',
		year: 2017
	});
	return { job, tracks: bladeRunnerTracks(), fingerprints: [], titles_read: titles };
}
