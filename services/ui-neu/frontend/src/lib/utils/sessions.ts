// Passthrough helpers shared by every session/preset picker that has to hide
// encode work: the apply dialog (runtime toggle off) and, on a ripper-only
// deployment (not transcode-capable), the drive pickers and the sessions
// editor. Passthrough = no transcode preset at all, or a preset whose tool is
// the explicit 'none' tool; those still finalize in-process without a
// transcoder, so they stay visible everywhere.

/** Tool of the 'none' (passthrough) transcode preset. */
export const PASSTHROUGH_TOOL = 'none';

/**
 * A session is passthrough-compatible when it has no transcode preset, or its
 * preset's tool is 'none'. A preset id missing from `presetToolById` (presets
 * not loaded yet, or a dangling id) counts as NOT passthrough, so an unknown
 * session is never offered as one.
 */
export function isPassthroughSession(
	s: { transcode_preset_id: string | null },
	presetToolById: Map<string, string>
): boolean {
	return s.transcode_preset_id === null || presetToolById.get(s.transcode_preset_id) === PASSTHROUGH_TOOL;
}

/** id -> tool lookup for `isPassthroughSession`. */
export function presetToolMap(presets: ReadonlyArray<{ id: string; tool: string }>): Map<string, string> {
	return new Map(presets.map((p) => [p.id, p.tool]));
}

const VIDEO_MEDIA_TYPES: ReadonlySet<string> = new Set(['movie', 'tv']);

/**
 * Whether a session of `sessionMediaType` can apply to a job of `jobMediaType`;
 * mirrors the Backend's `auto_session._media_types_compatible`, which also
 * gates session routes. Movie and tv share a track kind; an iso/data session
 * takes a dump of any video or data disc; music is only ever music.
 */
export function mediaTypesCompatible(jobMediaType: string, sessionMediaType: string): boolean {
	if (jobMediaType === sessionMediaType) return true;
	if (VIDEO_MEDIA_TYPES.has(sessionMediaType) && VIDEO_MEDIA_TYPES.has(jobMediaType)) return true;
	return (
		(sessionMediaType === 'iso' || sessionMediaType === 'data') &&
		(VIDEO_MEDIA_TYPES.has(jobMediaType) || jobMediaType === 'data')
	);
}
