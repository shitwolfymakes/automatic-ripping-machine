import type { TrackView } from '$lib/types/api.gen';
import { formatBytes } from '../utils/format';

const TRACK_KIND_LABELS: Record<string, string> = {
	video_title: 'Video',
	audio_track: 'Audio',
	data_dump: 'Data',
	disc_backup: 'Disc backup'
};

export function trackKindLabel(kind: string | null | undefined): string {
	if (!kind) return '-';
	return TRACK_KIND_LABELS[kind] ?? kind;
}

// True when any track is an episode, has an episode number, or has no role on
// a TV job.
export function isSeriesTrackList(tracks: readonly TrackView[], mediaType: string | null | undefined): boolean {
	return tracks.some((t) => t.role === 'episode' || t.episode_number != null || (t.role == null && mediaType === 'tv'));
}

// Tracks whose episode or role the user set by hand (switching to Movie drops them).
export function handSetTrackCount(tracks: readonly TrackView[]): number {
	return tracks.filter((t) => ['episode_number', 'role'].some((k) => t.identity_provenance?.[k] === 'manual')).length;
}

// Actual size once ripped; otherwise the scan-time estimate prefixed with ~.
export function trackSizeLabel(track: TrackView): string {
	if (track.size_bytes != null) return formatBytes(track.size_bytes);
	if (track.expected_size_bytes != null) return `~${formatBytes(track.expected_size_bytes)}`;
	return '-';
}
