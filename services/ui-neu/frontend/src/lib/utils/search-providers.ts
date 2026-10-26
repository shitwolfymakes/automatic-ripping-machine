// Shared by TitleSearch (the job page's provider badge) and FinishStep (the
// setup summary), which each carried their own copy of the label map.
const PROVIDER_LABELS: Record<string, string> = { tmdb: 'TMDb', omdb: 'OMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' };

/** Pretty name for a search-provider id; `fallback` until the config store hydrates. */
export function providerLabel(id: string | null | undefined, fallback = 'OMDb/TMDb'): string {
	return PROVIDER_LABELS[id ?? ''] ?? fallback;
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
