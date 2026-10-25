import type { TrackView, ScanTitle, TrackRole } from '$lib/types/api.gen';

// One row shape covering both review-card lifecycle stages. A row is editable iff
// it has a real materialized-track id; scanned-title rows (trackId === null) are
// read-only.
export type ReviewRow = {
	index: number;
	durationSeconds: number | null;
	sourceLabel: string | null;
	trackId: string | null;
	title: string | null;
	year: number | null;
	episodeNumber: number | null;
	/** The placed episode's name, shown beside the number as on the job page. */
	episodeName: string | null;
	/** What the title is once a source or the operator has said: an extra is placed without an episode. */
	role: TrackRole | null;
	excluded: boolean;
};

export function trackToRow(t: TrackView): ReviewRow {
	return {
		index: t.index,
		// The post-rip actual, else the scan-time estimate: a track waiting to rip has a length too.
		durationSeconds: t.duration_seconds ?? t.expected_duration_seconds ?? null,
		sourceLabel: t.output_path || t.source_ref,
		trackId: t.id,
		title: t.title ?? null,
		year: t.year ?? null,
		episodeNumber: t.episode_number ?? null,
		episodeName: t.episode_name ?? null,
		role: t.role ?? null,
		excluded: t.excluded ?? false
	};
}

export function scanTitleToRow(s: ScanTitle): ReviewRow {
	return {
		index: s.index,
		durationSeconds: s.duration_seconds,
		sourceLabel: s.source_file ?? null,
		trackId: null,
		title: null,
		year: null,
		episodeNumber: null,
		episodeName: null,
		role: null,
		excluded: false
	};
}
