import type { TrackView } from '$lib/types/api.gen';
import { formatBytes } from './format';

const TRACK_KIND_LABELS: Record<string, string> = {
	video_title: 'Video',
	audio_track: 'Audio',
	data_dump: 'Data'
};

export function trackKindLabel(kind: string | null | undefined): string {
	if (!kind) return '—';
	return TRACK_KIND_LABELS[kind] ?? kind;
}

// Actual size once ripped; otherwise the scan-time estimate prefixed with ~.
export function trackSizeLabel(track: TrackView): string {
	if (track.size_bytes != null) return formatBytes(track.size_bytes);
	if (track.expected_size_bytes != null) return `~${formatBytes(track.expected_size_bytes)}`;
	return '—';
}
