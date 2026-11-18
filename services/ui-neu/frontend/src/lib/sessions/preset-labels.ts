// The labels and one-line summaries the sessions screens show for a
// session's or preset's settings, shared by the Sessions and preset tables.
// Each label shows an unknown value as it is, and a missing one as -.

/** A value's label from `labels`. A value the table doesn't list shows
 * as itself, and no value as "-". */
function labelFrom(labels: ReadonlyMap<string, string>, v: string | null | undefined): string {
	return v == null ? '-' : (labels.get(v) ?? v);
}

const OUTPUT_MODE_LABELS: ReadonlyMap<string, string> = new Map([
	['tracks', 'Tracks'],
	['iso', 'ISO image'],
	['data_copy', 'File copy'],
	['folder', 'Disc backup (folder)']
]);

/** An output mode's label. */
export function humanizeOutputMode(v: string | null | undefined): string {
	return labelFrom(OUTPUT_MODE_LABELS, v);
}

const MEDIA_TYPE_LABELS: ReadonlyMap<string, string> = new Map([
	['movie', 'Movie'],
	['tv', 'TV'],
	['music', 'Music'],
	['data', 'Data'],
	['iso', 'ISO']
]);

/** A media type's label. */
export function humanizeMediaType(v: string | null | undefined): string {
	return labelFrom(MEDIA_TYPE_LABELS, v);
}

const TRACK_SELECTION_LABELS: ReadonlyMap<string, string> = new Map([
	['main_feature', 'Main feature'],
	['all_tracks', 'All tracks'],
	['archive', 'Archive'],
	['custom', 'Custom']
]);

/** A track selection's label. */
export function humanizeTrackSelection(v: string | null | undefined): string {
	return labelFrom(TRACK_SELECTION_LABELS, v);
}

const IDENTIFICATION_MODE_LABELS: ReadonlyMap<string, string> = new Map([
	['required', 'ID required'],
	['skip', 'ID skip'],
	['deferred_placeholder', 'ID deferred']
]);

/** An identification mode's label. */
export function humanizeIdentificationMode(v: string | null | undefined): string {
	return labelFrom(IDENTIFICATION_MODE_LABELS, v);
}

const TOOL_LABELS: ReadonlyMap<string, string> = new Map([
	['handbrake', 'HandBrake'],
	['abcde', 'abcde'],
	['none', 'None']
]);

/** A transcode tool's label. */
export function humanizeTool(v: string | null | undefined): string {
	return labelFrom(TOOL_LABELS, v);
}

const CONTAINER_LABELS: ReadonlyMap<string, string> = new Map([
	['mkv', 'MKV'],
	['mp4', 'MP4'],
	['webm', 'WebM'],
	['flac', 'FLAC'],
	['mp3', 'MP3'],
	['ogg', 'OGG'],
	['iso', 'ISO'],
	['none', 'None']
]);

/** A container's label. */
export function humanizeContainer(v: string | null | undefined): string {
	return labelFrom(CONTAINER_LABELS, v);
}
