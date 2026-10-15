import type { ConfigFieldMeta } from '$lib/types/api.gen';

/** The thirteen Identification metas, mirroring arm_common's config_metadata. */
const base = { group: 'Identification', tier: 'operator', editable: true } as const;

export const IDENTITY_METAS: ConfigFieldMeta[] = [
	{
		...base,
		key: 'search_provider_movie',
		label: 'Search movies with',
		help: "The service behind the job page's search box for movies.",
		type: 'enum',
		enum_values: ['tmdb', 'omdb'],
		enum_labels: { tmdb: 'TMDb', omdb: 'OMDb' },
		enum_requires: { tmdb: 'tmdb_api_key', omdb: 'omdb_api_key' }
	},
	{
		...base,
		key: 'search_provider_tv',
		label: 'Search TV with',
		help: "The service behind the job page's search box for TV. TVmaze needs no key.",
		type: 'enum',
		enum_values: ['tmdb', 'omdb', 'tvmaze', 'tvdb'],
		enum_labels: { tmdb: 'TMDb', omdb: 'OMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' },
		enum_requires: { tmdb: 'tmdb_api_key', omdb: 'omdb_api_key', tvdb: 'tvdb_api_key' }
	},
	{
		...base,
		key: 'search_provider_music',
		label: 'Search music with',
		help: "The service behind the job page's search box for audio CDs.",
		type: 'enum',
		enum_values: ['musicbrainz'],
		enum_labels: { musicbrainz: 'MusicBrainz' }
	},
	{
		...base,
		key: 'thediscdb_enabled',
		label: 'Match discs against TheDiscDB',
		help: 'Match discs against the local TheDiscDB snapshot to label titles, pick the main feature, and name extras/episodes.',
		type: 'bool'
	},
	{
		...base,
		key: 'crc64service_enabled',
		label: 'ARM community database (CRC64)',
		help: "Send a DVD's CRC64 fingerprint to the ARM project's community database and take its title when it has one. DVDs only; no key needed.",
		type: 'bool'
	},
	{
		...base,
		key: 'movie_sources',
		label: 'Movie sources',
		help: 'Tried top to bottom when a disc looks like a movie. ARM stops at the first confident match.',
		type: 'ranked',
		enum_values: ['tmdb', 'omdb'],
		enum_labels: { tmdb: 'TMDb', omdb: 'OMDb' },
		enum_requires: { tmdb: 'tmdb_api_key', omdb: 'omdb_api_key' }
	},
	{
		...base,
		key: 'episode_sources',
		label: 'Episode sources',
		help: 'Tried top to bottom. ARM stops at the first confident match. TVmaze needs no key.',
		type: 'ranked',
		enum_values: ['tmdb', 'tvmaze', 'tvdb'],
		enum_labels: { tmdb: 'TMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' },
		enum_requires: { tmdb: 'tmdb_api_key', tvdb: 'tvdb_api_key' }
	},
	{
		...base,
		key: 'music_sources',
		label: 'Music sources',
		help: "Tried top to bottom for audio CDs, matched by the disc's track layout. MusicBrainz needs no key.",
		type: 'ranked',
		enum_values: ['musicbrainz'],
		enum_labels: { musicbrainz: 'MusicBrainz' }
	},
	{
		...base,
		key: 'episode_match_tolerance_seconds',
		label: 'Match tolerance (seconds)',
		help: "The most a track's runtime may differ from an episode's and still match. ARM narrows this to a tenth of the episode's runtime, at least 60 seconds. 1 to 1800, default 300.",
		type: 'int'
	},
	{
		...base,
		key: 'movie_auto_apply',
		label: 'Apply confident movie matches',
		help: 'When off, a movie match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping › Hold discs for review still holds every disc.',
		type: 'bool'
	},
	{
		...base,
		key: 'episode_auto_apply',
		label: 'Apply confident matches',
		help: 'When off, a TV show match and every episode match are kept as suggestions to confirm on the job page; the disc is held with no countdown. Ripping › Hold discs for review still holds every disc.',
		type: 'bool'
	},
	{
		...base,
		key: 'music_auto_apply',
		label: 'Apply confident music matches',
		help: 'When off, an audio CD match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping › Hold discs for review still holds every disc.',
		type: 'bool'
	},
	{
		...base,
		key: 'disc_hint_sources',
		label: 'Read season and disc number from',
		help: 'Read from the disc in this order, before ARM identifies it.',
		type: 'ranked',
		enum_values: ['bd_title', 'label'],
		enum_labels: { bd_title: 'Blu-ray disc title', label: 'Disc volume label' }
	}
];

/** The backend defaults: every switch on, every list in its default order. */
export const IDENTITY_DEFAULTS: Record<string, unknown> = {
	search_provider_movie: 'tmdb',
	search_provider_tv: 'tvmaze',
	search_provider_music: 'musicbrainz',
	thediscdb_enabled: true,
	crc64service_enabled: true,
	movie_sources: ['tmdb', 'omdb'],
	episode_sources: ['tmdb', 'tvmaze', 'tvdb'],
	music_sources: ['musicbrainz'],
	episode_match_tolerance_seconds: 300,
	movie_auto_apply: true,
	episode_auto_apply: true,
	music_auto_apply: true,
	disc_hint_sources: ['bd_title', 'label']
};
