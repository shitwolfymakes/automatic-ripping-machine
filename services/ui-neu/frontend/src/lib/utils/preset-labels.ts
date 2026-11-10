// The labels the sessions screens show for a session's or preset's settings,
// shared by SessionCard and PresetRow. Each shows an unknown value as it is,
// and a missing one as -.
export function humanizeOutputMode(v: string | null | undefined): string {
	switch (v) {
		case 'tracks':
			return 'Tracks';
		case 'iso':
			return 'ISO image';
		case 'data_copy':
			return 'File copy';
		case 'folder':
			return 'Disc backup (folder)';
		default:
			return v ?? '-';
	}
}

/** A media type's label. */
export function humanizeMediaType(v: string | null | undefined): string {
	switch (v) {
		case 'movie':
			return 'Movie';
		case 'tv':
			return 'TV';
		case 'music':
			return 'Music';
		case 'data':
			return 'Data';
		case 'iso':
			return 'ISO';
		default:
			return v ?? '-';
	}
}

/** A track selection's label. */
export function humanizeTrackSelection(v: string | null | undefined): string {
	switch (v) {
		case 'main_feature':
			return 'Main feature';
		case 'all_tracks':
			return 'All tracks';
		case 'archive':
			return 'Archive';
		case 'custom':
			return 'Custom';
		default:
			return v ?? '-';
	}
}

/** An identification mode's label. */
export function humanizeIdentificationMode(v: string | null | undefined): string {
	switch (v) {
		case 'required':
			return 'ID required';
		case 'skip':
			return 'ID skip';
		case 'deferred_placeholder':
			return 'ID deferred';
		default:
			return v ?? '-';
	}
}

/** A transcode tool's label. */
export function humanizeTool(v: string | null | undefined): string {
	switch (v) {
		case 'handbrake':
			return 'HandBrake';
		case 'abcde':
			return 'abcde';
		case 'none':
			return 'None';
		default:
			return v ?? '-';
	}
}

/** A container's label. */
export function humanizeContainer(v: string | null | undefined): string {
	switch (v) {
		case 'mkv':
			return 'MKV';
		case 'mp4':
			return 'MP4';
		case 'webm':
			return 'WebM';
		case 'flac':
			return 'FLAC';
		case 'mp3':
			return 'MP3';
		case 'ogg':
			return 'OGG';
		case 'iso':
			return 'ISO';
		case 'none':
			return 'None';
		default:
			return v ?? '-';
	}
}
