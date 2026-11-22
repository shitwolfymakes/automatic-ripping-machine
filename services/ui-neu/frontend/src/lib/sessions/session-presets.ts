// What the sessions area knows about a preset: which kind it is, and
// the create body that copies one.
import type {
	RipPresetCreateRequest,
	RipPresetView,
	TranscodePresetCreateRequest,
	TranscodePresetView
} from '$lib/types/api.gen';

/** The preset is a rip preset: only rip presets carry a track selection. */
export function isRipPreset(p: RipPresetView | TranscodePresetView): p is RipPresetView {
	return 'track_selection' in p;
}

// A trailing " (copy)" or " (copy N)", as copyName writes it.
const COPY_SUFFIX = / \(copy(?: (\d+))?\)$/;

const nameKey = (name: string): string => name.trim().toLowerCase();

/** The name a copy gets: "<name> (copy)", or "(copy 2)", "(copy 3)"... when
 * that is taken (ignoring case and surrounding spaces). A copy of a copy
 * numbers from the original's name, so it never reads "(copy) (copy)". */
export function copyName(name: string, taken: Iterable<string> = []): string {
	const base = name.trim().replace(COPY_SUFFIX, '');
	const used = new Set(Array.from(taken, nameKey));
	const candidate = (n: number) => (n === 1 ? `${base} (copy)` : `${base} (copy ${n})`);
	let n = 1;
	while (used.has(nameKey(candidate(n)))) n++;
	return candidate(n);
}

/** The create body for a copy of a rip preset. */
export function ripPresetCopy(p: RipPresetView, taken: Iterable<string> = []): RipPresetCreateRequest {
	return {
		name: copyName(p.name, taken),
		media_type: p.media_type,
		track_selection: p.track_selection,
		identification_mode: p.identification_mode,
		output_mode: p.output_mode,
		// track_filters_json is { [key: string]: unknown } | null in the API;
		// RipPresetView carries it as unknown - narrow with a cast.
		track_filters_json: p.track_filters_json as { [key: string]: unknown } | null
	};
}

/** The create body for a copy of a transcode preset. */
export function transcodePresetCopy(
	p: TranscodePresetView,
	taken: Iterable<string> = []
): TranscodePresetCreateRequest {
	return {
		name: copyName(p.name, taken),
		media_type: p.media_type,
		tool: p.tool,
		preset_ref: p.preset_ref ?? null,
		handbrake_settings: p.handbrake_settings ?? null,
		container: p.container,
		encoder: p.encoder,
		extra_args: p.extra_args ?? null
	};
}
