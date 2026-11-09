import type { KeyedSources } from '$lib/stores/config';

// Shared by TitleSearch (the job page's provider badge) and FinishStep (the
// setup summary), which each carried their own copy of the label map.
const PROVIDER_LABELS: Record<string, string> = { tmdb: 'TMDb', omdb: 'OMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' };

/** Pretty name for a search-provider id; `fallback` until the config store hydrates. */
export function providerLabel(id: string | null | undefined, fallback = 'OMDb/TMDb'): string {
	return PROVIDER_LABELS[id ?? ''] ?? fallback;
}

export type SearchSource = 'tmdb' | 'omdb' | 'tvmaze' | 'tvdb';

export interface SearchSourceOption {
	id: SearchSource;
	label: string;
}

/** The sources each search type offers, in picker order. */
export const SEARCH_SOURCES: Record<'movie' | 'tv', SearchSourceOption[]> = {
	movie: [
		{ id: 'tmdb', label: 'TMDb' },
		{ id: 'omdb', label: 'OMDb' }
	],
	tv: [
		{ id: 'tmdb', label: 'TMDb' },
		{ id: 'omdb', label: 'OMDb' },
		{ id: 'tvmaze', label: 'TVmaze' },
		{ id: 'tvdb', label: 'TVDB' }
	]
};

/** TVmaze needs no key; the others need a saved one. */
export function sourceKeyed(id: SearchSource, keyed: KeyedSources): boolean {
	return id === 'tvmaze' || keyed[id];
}

/**
 * The source a search uses: the picked one while the type offers it; else the
 * Settings default for the type. When the default's key was removed, the first
 * usable source, or the default itself when none is usable. `undefined` when
 * the default is not one of the type's sources.
 */
export function chooseSource(
	options: SearchSourceOption[],
	picked: SearchSource | null,
	fromSettings: string | null,
	keyed: KeyedSources
): SearchSource | undefined {
	if (picked && options.some((o) => o.id === picked)) return picked;
	const settingsSource = options.find((o) => o.id === fromSettings)?.id;
	// The default's key was removed after it was chosen: start on the first
	// usable source; with none usable keep the default (the backend's 400 shows).
	if (settingsSource && !sourceKeyed(settingsSource, keyed)) {
		return options.find((o) => sourceKeyed(o.id, keyed))?.id ?? settingsSource;
	}
	return settingsSource;
}

/**
 * The movie provider the backend will actually search with, or null when
 * neither movie key is saved and it has no source to use.
 *
 * `search_provider_movie` only takes effect while its key is saved; without
 * one the backend falls back to the first movie source that has a key
 * (`identity.sources.registry.search_source`). Reporting the raw setting told
 * an OMDb-only install that titles come from TMDb.
 */
export function effectiveMovieProvider(config: {
	search_provider_movie?: string | null;
	tmdb_api_key?: string | null;
	omdb_api_key?: string | null;
}): 'tmdb' | 'omdb' | null {
	const chosen = config.search_provider_movie === 'omdb' ? 'omdb' : 'tmdb';
	const chosenKey = chosen === 'omdb' ? config.omdb_api_key : config.tmdb_api_key;
	if (chosenKey) return chosen;
	if (config.tmdb_api_key) return 'tmdb';
	return config.omdb_api_key ? 'omdb' : null;
}
