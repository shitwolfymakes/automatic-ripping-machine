// The job detail payload carries tracks but not the dashboard's rip_progress
// summary, so derive the same summary from the tracks.
import type { RipProgressSummary, TrackView } from '$lib/types/api.gen';

export function ripProgressFromTracks(tracks: Pick<TrackView, 'id' | 'index' | 'status'>[]): RipProgressSummary {
	const ordered = [...tracks].sort((a, b) => a.index - b.index);
	const current = ordered.findIndex((t) => t.status === 'in_progress');
	return {
		tracks_total: ordered.length,
		tracks_done: ordered.filter((t) => t.status === 'done').length,
		tracks_failed: ordered.filter((t) => t.status === 'failed').length,
		current_track_id: current === -1 ? null : ordered[current].id,
		current_track_index: current === -1 ? null : current + 1
	};
}
