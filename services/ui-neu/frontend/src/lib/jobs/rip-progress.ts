// The job detail payload carries tracks but not the dashboard's rip_progress
// summary, so derive the same summary from the tracks.
import type { JobView, RipProgressSummary, TrackView } from '$lib/types/api.gen';

type ProgressTrack = Pick<TrackView, 'id' | 'index' | 'status' | 'excluded'>;

export function ripProgressFromTracks(tracks: ProgressTrack[]): RipProgressSummary {
	// Only the selected tracks count. An unticked one is no rip work even where `mkv all` still
	// writes it, and neither is a skipped one (unticked at Start of a per-title rip, never read).
	// Mirrors the backend's _summarize_rip_progress.
	const ordered = tracks.filter((t) => !t.excluded && t.status !== 'skipped').sort((a, b) => a.index - b.index);
	const current = ordered.findIndex((t) => t.status === 'in_progress');
	return {
		tracks_total: ordered.length,
		tracks_done: ordered.filter((t) => t.status === 'done').length,
		tracks_failed: ordered.filter((t) => t.status === 'failed').length,
		current_track_id: current === -1 ? null : ordered[current].id,
		current_track_index: current === -1 ? null : current + 1
	};
}

/**
 * The rip_progress the job page's stage rail reads. The backend fills
 * rip_progress only while a job is ripping, so the page derives it from the
 * tracks only then; for every other status it passes the job's own value, and
 * the job page and the dashboard card see the same input.
 */
export function railRipProgress(
	job: Pick<JobView, 'status' | 'rip_progress'>,
	tracks: ProgressTrack[]
): RipProgressSummary | null {
	if (job.status !== 'ripping') return job.rip_progress ?? null;
	return job.rip_progress ?? ripProgressFromTracks(tracks);
}
