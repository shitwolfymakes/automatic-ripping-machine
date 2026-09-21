/**
 * Frontend-only preset/scheme shapes.
 *
 * These mirror the BFF-era `Scheme` / `Preset` / `Overrides` types that the
 * PresetEditor and TranscodeOverrides components consume. v3 has NO equivalent
 * on the wire: the transcoder-scheme endpoint is MISSING, and v3's
 * `TranscodePresetView` is a flat, unrelated shape (id/name/media_type/tool).
 * The scheme-driven editor therefore runs in its offline state under v3; these
 * local interfaces exist so the component logic keeps type-checking until a v3
 * transcoder-scheme backend lands.
 */

// A single tier (dvd/bluray/uhd) or shared override bag: arbitrary keyed values.
export type OverrideBag = Record<string, unknown>;

export interface Overrides {
	shared: OverrideBag;
	tiers: Record<string, OverrideBag>;
}

export interface SchemeEncoder {
	slug: string;
	name: string;
	tuning_presets?: string[];
}

export interface SchemeAdvancedField {
	type: string;
	values?: string[];
	default?: string;
	description?: string;
}

export interface Scheme {
	slug: string;
	name: string;
	supported_encoders: SchemeEncoder[];
	supported_audio_encoders: string[];
	supported_subtitle_modes: string[];
	advanced_fields?: Record<string, SchemeAdvancedField>;
}

export interface Preset {
	slug: string;
	name: string;
	scheme: string;
	description?: string;
	builtin: boolean;
	parent_slug?: string;
	shared: OverrideBag;
	tiers: Record<string, OverrideBag>;
	unavailable?: boolean;
	reason?: string;
}

export interface PresetEditorState {
	preset_slug: string;
	overrides: Overrides;
}
