// How identify names a provider to the operator. The search source picker
// keeps its own labels in search-providers.ts.

/** Display names for identification provider ids. */
export const PROVIDER_LABELS: Record<string, string> = {
	tmdb: 'TMDb',
	omdb: 'OMDb',
	tvmaze: 'TVmaze',
	tvdb: 'TVDB',
	musicbrainz: 'MusicBrainz',
	arm_server: 'ARM community database',
	thediscdb: 'TheDiscDB'
};

/** A provider id's display name; an unknown id shows as itself. */
export function providerLabel(provider: string): string {
	return PROVIDER_LABELS[provider] ?? provider;
}
