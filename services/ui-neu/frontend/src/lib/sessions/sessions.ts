// Passthrough helpers shared by every session/preset picker that has to hide
// encode work: the apply dialog (runtime toggle off) and, on a ripper-only
// deployment (not transcode-capable), the drive pickers and the sessions
// editor. Passthrough = no transcode preset at all, or a preset whose tool is
// the explicit 'none' tool; those still finalize in-process without a
// transcoder, so they stay visible everywhere.
import type { DiscType, MediaType } from '$lib/types/api.gen';

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

/**
 * The sessions the manual-rip picker offers. A ripper-only deployment (not
 * transcode-capable) can never run an encode session, so the picker offers
 * only passthrough ones; with the transcoder on, every session is offered.
 */
export function manualRipSessionChoices<S extends { transcode_preset_id: string | null }>(
	sessions: S[],
	presets: ReadonlyArray<{ id: string; tool: string }>,
	transcoderEnabled: boolean
): S[] {
	if (transcoderEnabled) return sessions;
	const toolById = presetToolMap(presets);
	return sessions.filter((s) => isPassthroughSession(s, toolById));
}

/**
 * The sessions the default-session picker offers: the manual-rip choices, plus
 * an encode session already saved as the drive's default, which stays listed
 * so the select still shows the real value.
 */
export function defaultSessionChoices<S extends { id: string; transcode_preset_id: string | null }>(
	sessions: S[],
	presets: ReadonlyArray<{ id: string; tool: string }>,
	transcoderEnabled: boolean,
	defaultSessionId: string | null | undefined
): S[] {
	if (transcoderEnabled) return sessions;
	const passthrough = manualRipSessionChoices(sessions, presets, false);
	const current = sessions.find((s) => s.id === defaultSessionId);
	return current && !passthrough.includes(current) ? [...passthrough, current] : passthrough;
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

// dvd/bluray → movie, cd → music, data → data, otherwise (e.g. unknown) → null
// (no media type, so every session applies).
function discTypeToMediaType(dt: DiscType): MediaType | null {
	if (dt === 'dvd' || dt === 'bluray') return 'movie';
	if (dt === 'cd') return 'music';
	if (dt === 'data') return 'data';
	return null;
}

/**
 * The sessions a disc of this type can take: those of its media type plus tv
 * sessions, or every session when the disc type maps to no media type
 * (unknown).
 */
export function sessionsForDisc<S extends { media_type: string }>(sessions: readonly S[], discType: DiscType): S[] {
	const mt = discTypeToMediaType(discType);
	return sessions.filter((s) => mt === null || s.media_type === mt || s.media_type === 'tv');
}

/** The media types a session can have. */
const SESSION_MEDIA_TYPES: MediaType[] = ['movie', 'tv', 'music', 'data', 'iso'];

/** How many sessions there are, in all and of each media type. */
export function countByMediaType(sessions: ReadonlyArray<{ media_type: string }>): Record<MediaType | 'all', number> {
	const counts: Record<string, number> = { all: sessions.length };
	for (const m of SESSION_MEDIA_TYPES) counts[m] = sessions.filter((s) => s.media_type === m).length;
	return counts as Record<MediaType | 'all', number>;
}
