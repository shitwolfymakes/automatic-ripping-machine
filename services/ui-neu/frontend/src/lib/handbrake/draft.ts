// The transcode preset sidebar's editable draft and the request bodies it saves as.
// Pure functions; the sidebar component does the I/O.

import type {
	ContainerFormat,
	HandbrakeSettings,
	MediaType,
	TranscodePresetCreateRequest,
	TranscodePresetUpdateRequest,
	TranscodePresetView,
	TranscodeTool
} from '$lib/types/api.gen';
import { PRESET_ENCODER_ID } from './encoder-availability';
import { toPayload } from './settingsEdit';

export type PresetField = 'name' | 'media_type' | 'tool' | 'preset_ref' | 'container' | 'encoder' | 'extra_args';

export interface Draft {
	name: string;
	media_type: MediaType;
	tool: TranscodeTool;
	preset_ref: string | null;
	container: ContainerFormat;
	encoder: string;
	extra_args: string;
	settings: HandbrakeSettings;
}

export function settingsOf(s: HandbrakeSettings | null): Required<HandbrakeSettings> {
	return { common: s?.common ?? {}, encoders: s?.encoders ?? {} };
}

export function settingsCount(s: HandbrakeSettings | null): number {
	const n = settingsOf(s);
	return Object.keys(n.common).length + Object.values(n.encoders).reduce((sum, b) => sum + Object.keys(b).length, 0);
}

export function initialDraft(preset: TranscodePresetView | null): Draft {
	return {
		name: preset?.name ?? '',
		media_type: preset?.media_type ?? 'movie',
		tool: preset?.tool ?? 'handbrake',
		preset_ref: preset?.preset_ref ?? null,
		container: preset?.container ?? 'mkv',
		encoder: preset?.encoder ?? PRESET_ENCODER_ID,
		extra_args: preset?.extra_args ?? '',
		settings: settingsOf(preset?.handbrake_settings ?? null)
	};
}

// vaapi_* catalog ids are the ffmpeg_vaapi engine: HandBrake settings do not apply to them.
export function isVaapiEncoder(encoderId: string): boolean {
	return encoderId.startsWith('vaapi_');
}

export function showTabs(d: Draft): boolean {
	return d.tool === 'handbrake' && !isVaapiEncoder(d.encoder);
}

// The draft holds settings the save will drop because the tabs no longer apply.
export function clearsSettings(d: Draft): boolean {
	return !showTabs(d) && settingsCount(d.settings) > 0;
}

// Settings the tabs cannot show are not sent: the encoder would ignore them.
function settingsPayload(d: Draft): HandbrakeSettings | null {
	return showTabs(d) ? toPayload(d.settings) : null;
}

function presetFields(d: Draft) {
	return {
		name: d.name,
		tool: d.tool,
		preset_ref: d.preset_ref,
		container: d.container,
		encoder: d.encoder,
		extra_args: d.extra_args || null,
		handbrake_settings: settingsPayload(d)
	};
}

export function draftToUpdate(d: Draft): TranscodePresetUpdateRequest {
	return presetFields(d);
}

export function draftToCreate(d: Draft): TranscodePresetCreateRequest {
	return { ...presetFields(d), media_type: d.media_type };
}
