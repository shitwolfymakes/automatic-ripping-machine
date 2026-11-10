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

/** The name a copy gets. */
export function copyName(name: string): string {
	return `${name} (copy)`;
}

/** The create body for a copy of a rip preset. */
export function ripPresetCopy(p: RipPresetView): RipPresetCreateRequest {
	return {
		name: copyName(p.name),
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
export function transcodePresetCopy(p: TranscodePresetView): TranscodePresetCreateRequest {
	return {
		name: copyName(p.name),
		media_type: p.media_type,
		tool: p.tool,
		preset_ref: p.preset_ref ?? null,
		container: p.container,
		encoder: p.encoder,
		extra_args: p.extra_args ?? null
	};
}
