import type { ConfigFieldMeta } from '$lib/types/api.gen';

/** Presentation-only grouping for the schema-driven settings tabs, so they
 *  read like the Sessions / Appearance tabs: a tab description, then one
 *  card per section. The backend only knows group + tier; any field this map
 *  doesn't name lands in a trailing card titled after its group. */

export interface SettingsSection {
	title: string;
	blurb?: string;
	keys: string[];
}

const GROUP_BLURBS: Record<string, string> = {
	Metadata: 'Where ARM looks up titles and disc data, and the keys those services need.',
	Ripping: 'What happens when a disc goes in.',
	Transcoding: 'When finished rips are handed to the transcoder.'
};

const SECTIONS: Record<string, SettingsSection[]> = {
	Metadata: [
		{
			title: 'Lookup',
			blurb: 'Which service identifies a disc, and whether TheDiscDB matching is used.',
			keys: ['metadata_provider', 'thediscdb_enabled', 'thediscdb_refresh_days']
		},
		{
			title: 'API keys',
			blurb: 'Stored on the server. A key that is already set shows as hidden; leave it blank to keep it.',
			keys: ['tmdb_api_key', 'omdb_api_key', 'tvdb_api_key', 'makemkv_key']
		}
	],
	Ripping: [
		{
			title: 'On insert',
			keys: ['auto_rip_on_insert', 'block_on_miss', 'ripping_paused']
		},
		{
			title: 'Review gate',
			blurb: 'Hold each disc after identification so the match can be corrected before the rip starts.',
			keys: ['hold_for_review', 'manual_wait_seconds']
		},
		{
			title: 'Decryption data',
			blurb: 'Key material MakeMKV needs for protected discs, refreshed in the background.',
			keys: ['community_keydb_enabled', 'makemkv_sdf_enabled']
		}
	],
	Transcoding: [{ title: 'Scheduling', keys: ['auto_transcode_on_idle'] }]
};

/** Maps the four API-key field keys (from the "API keys" section above) to
 *  the endpoint name POST /api/config/keys/{name}/check expects. */
export const KEY_CHECK_NAMES: Record<string, 'tmdb' | 'omdb' | 'tvdb' | 'makemkv'> = {
	tmdb_api_key: 'tmdb',
	omdb_api_key: 'omdb',
	tvdb_api_key: 'tvdb',
	makemkv_key: 'makemkv'
};

export function groupBlurb(group: string): string | undefined {
	return GROUP_BLURBS[group];
}

/** Split `fields` into the sections declared for `group`, in declared order,
 *  dropping empty sections and appending unmapped fields under the group name. */
export function sectionFields(
	group: string,
	fields: ConfigFieldMeta[]
): Array<SettingsSection & { fields: ConfigFieldMeta[] }> {
	const byKey = new Map(fields.map((f) => [f.key, f]));
	const placed = new Set<string>();
	const out: Array<SettingsSection & { fields: ConfigFieldMeta[] }> = [];
	for (const section of SECTIONS[group] ?? []) {
		const own = section.keys.map((k) => byKey.get(k)).filter((f): f is ConfigFieldMeta => f !== undefined);
		own.forEach((f) => placed.add(f.key));
		if (own.length > 0) out.push({ ...section, fields: own });
	}
	const rest = fields.filter((f) => !placed.has(f.key));
	if (rest.length > 0) out.push({ title: group, keys: rest.map((f) => f.key), fields: rest });
	return out;
}
