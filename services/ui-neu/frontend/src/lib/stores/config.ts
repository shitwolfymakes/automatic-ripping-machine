import { writable } from 'svelte/store';
import { fetchConfig } from '$lib/api/config';

// Subsystem AVAILABILITY: whether this deployment can run transcode
// containers at all (a deployment fact, fixed at install time). Existing
// consumers (nav filter, EmptyDashboardPanel, SettingsReviewStep, the
// /transcoder route guard) hide transcoder UI entirely when this is false -
// neu-style hide, not a disabled control.
const _transcoderEnabled = writable<boolean>(true);
// Runtime toggle: capable AND turned on (Settings > Transcoding "Enable
// transcoding"). Encode sessions can only be applied while this is true;
// passthrough sessions work either way. Consumers that want a
// visible-but-disabled presentation read this instead of transcoderEnabled.
const _transcodeRuntimeEnabled = writable<boolean>(true);
// Configured default metadata provider ('tmdb' | 'omdb'); null until hydrated.
const _metadataProvider = writable<string | null>(null);

export const transcoderEnabled = { subscribe: _transcoderEnabled.subscribe };
export const transcodeRuntimeEnabled = { subscribe: _transcodeRuntimeEnabled.subscribe };
export const metadataProvider = { subscribe: _metadataProvider.subscribe };

export function setTranscoderEnabled(value: boolean): void {
	_transcoderEnabled.set(value);
}

export function setTranscodeRuntimeEnabled(value: boolean): void {
	_transcodeRuntimeEnabled.set(value);
}

export async function hydrateConfig(): Promise<void> {
	try {
		const cfg = await fetchConfig();
		_transcoderEnabled.set(cfg.transcoder_capable);
		_transcodeRuntimeEnabled.set(cfg.transcoder_capable && cfg.transcoder_enabled);
		_metadataProvider.set(cfg.metadata_provider ?? null);
	} catch {
		_transcoderEnabled.set(true);
		_transcodeRuntimeEnabled.set(true);
		_metadataProvider.set(null);
	}
}
