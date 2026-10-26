import { writable } from 'svelte/store';
import { fetchConfig } from '$lib/api/config';

// Subsystem AVAILABILITY: whether this deployment can run transcode
// containers at all (a deployment fact, fixed at install time). Existing
// consumers (nav filter, EmptyDashboardPanel, SettingsReviewStep, the
// /transcoder page's own full-page empty state for a ripper-only deep link)
// hide transcoder UI entirely when this is false - neu-style hide, not a
// disabled control.
const _transcoderEnabled = writable<boolean>(true);
// Runtime toggle: capable AND turned on (Settings > Transcoding "Enable
// transcoding"). Encode sessions can only be applied while this is true;
// passthrough sessions work either way. Consumers that want a
// visible-but-disabled presentation read this instead of transcoderEnabled.
const _transcodeRuntimeEnabled = writable<boolean>(true);
// The job page's search provider per media type; nulls until hydrated.
const _searchProviders = writable<{ movie: string | null; tv: string | null }>({ movie: null, tv: null });
// Which keyed search providers have a saved API key. Fails open (all true)
// until hydrated or when the config fetch fails: the backend still refuses an
// unkeyed provider with a 400 the search shows.
export interface KeyedSources {
	tmdb: boolean;
	omdb: boolean;
	tvdb: boolean;
}
const ALL_KEYED: KeyedSources = { tmdb: true, omdb: true, tvdb: true };
const _keyedSources = writable<KeyedSources>(ALL_KEYED);

export const transcoderEnabled = { subscribe: _transcoderEnabled.subscribe };
export const transcodeRuntimeEnabled = { subscribe: _transcodeRuntimeEnabled.subscribe };
export const searchProviders = { subscribe: _searchProviders.subscribe };
export const keyedSources = { subscribe: _keyedSources.subscribe };

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
		_searchProviders.set({ movie: cfg.search_provider_movie, tv: cfg.search_provider_tv });
		_keyedSources.set({ tmdb: cfg.tmdb_keyed, omdb: cfg.omdb_keyed, tvdb: cfg.tvdb_keyed });
	} catch {
		_transcoderEnabled.set(true);
		_transcodeRuntimeEnabled.set(true);
		_searchProviders.set({ movie: null, tv: null });
		_keyedSources.set(ALL_KEYED);
	}
}
