import type { TrackView, ScanTitle, TrackRole, TitleClass } from '$lib/types/api.gen';
import { trackSizeLabel } from '$lib/jobs/track-fields';
import { formatBytes } from '$lib/utils/format';
import { featureLabel, sourceName, titleClassLabel, type RefIndex, type TitleClassLabel } from './title-class';
import { parseTitleRef } from './version-sets';

// One row shape covering both review-card lifecycle stages. A row is editable iff
// it has a real materialized-track id; scanned-title rows (trackId === null) are
// read-only.
export type ReviewRow = {
	index: number;
	durationSeconds: number | null;
	/** The actual size once ripped, else the scan estimate with a leading ~; '-' when unknown. */
	sizeLabel: string;
	/** What the Source column names: the ripped file, the playlist, the stream file, else the title number. */
	sourceName: string;
	/** The `source_ref` of this row's title, which a copy's `classRef` points at. */
	sourceRef: string;
	titleClass: TitleClass | null;
	classRef: string | null;
	classLabel: TitleClassLabel | null;
	trackId: string | null;
	title: string | null;
	year: number | null;
	episodeNumber: number | null;
	/** The placed episode's name, shown beside the number as on the job page. */
	episodeName: string | null;
	/** What the title is once a source or the operator has said: an extra is placed without an episode. */
	role: TrackRole | null;
	excluded: boolean;
	/** The angle the ref names (`00334.mpls:2`), null for a title without angles. */
	angle: number | null;
	/** The title plays a 3D view. */
	stereo3d: boolean;
	/** MakeMKV's list does not hold the title: it cannot be ripped. */
	unrippable: boolean;
	/** "Main feature" or "Extra" for a title that stands on its own, else null. */
	featureLabel: string | null;
};

export function trackToRow(t: TrackView, refIndex: RefIndex): ReviewRow {
	return {
		index: t.index,
		// The post-rip actual, else the scan-time estimate: a track waiting to rip has a length too.
		durationSeconds: t.duration_seconds ?? t.expected_duration_seconds ?? null,
		sizeLabel: trackSizeLabel(t),
		sourceName: sourceName(t),
		sourceRef: t.source_ref,
		titleClass: t.title_class ?? null,
		classRef: t.title_class_ref ?? null,
		classLabel: titleClassLabel(t, refIndex),
		trackId: t.id,
		title: t.title ?? null,
		year: t.year ?? null,
		episodeNumber: t.episode_number ?? null,
		episodeName: t.episode_name ?? null,
		role: t.role ?? null,
		excluded: t.excluded ?? false,
		angle: parseTitleRef(t.source_ref)?.angle ?? null,
		stereo3d: t.stereo_3d ?? false,
		unrippable: t.unrippable ?? false,
		featureLabel: featureLabel(t)
	};
}

export function scanTitleToRow(s: ScanTitle): ReviewRow {
	return {
		index: s.index,
		durationSeconds: s.duration_seconds,
		sizeLabel: s.size_bytes == null ? '-' : `~${formatBytes(s.size_bytes)}`,
		sourceName: sourceName({
			output_path: null,
			playlist_name: s.playlist_name,
			source_file: s.source_file,
			source_ref: String(s.index)
		}),
		sourceRef: String(s.index),
		titleClass: null,
		classRef: null,
		classLabel: null,
		trackId: null,
		title: null,
		year: null,
		episodeNumber: null,
		episodeName: null,
		role: null,
		excluded: false,
		angle: s.angle ?? null,
		stereo3d: s.stereo_3d ?? false,
		unrippable: false,
		featureLabel: null
	};
}

// A title a source or the operator placed as something other than an episode.
const NON_EPISODE: Record<string, string> = { extra: 'Extra', trailer: 'Trailer', other: 'Other' };

/** The role's label for a row placed without an episode number, else null. */
export function nonEpisode(row: { role: string | null; episodeNumber: number | null }): string | null {
	return row.episodeNumber == null && row.role ? (NON_EPISODE[row.role] ?? null) : null;
}
