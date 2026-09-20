import type { TrackView, ScanTitle } from '$lib/types/api.gen';

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
	excluded: boolean;
};

export function trackToRow(t: TrackView): ReviewRow {
	return {
		index: t.index,
		durationSeconds: t.duration_seconds,
		sourceLabel: t.output_path || t.source_ref,
		trackId: t.id,
		title: t.title ?? null,
		year: t.year ?? null,
		episodeNumber: t.episode_number ?? null,
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
		excluded: false
	};
}
