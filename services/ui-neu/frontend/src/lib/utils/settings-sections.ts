import type { ConfigFieldMeta, SettingsGroup } from '$lib/types/api.gen';

/** Presentation-only grouping for the schema-driven settings tabs, so they
 *  read like the Sessions / Appearance tabs: a tab description, then one
 *  card per section. The backend only knows group + tier; any field this map
 *  doesn't name lands in a trailing card titled after its group. */

export interface SettingsSection {
	title: string;
	blurb?: string;
	keys: string[];
	/** Groups of keys rendered side by side on desktop (each group's own
	 *  keys stack vertically); the whole grid collapses to one column on a
	 *  narrow panel. Keys named here are not repeated in `fields`. */
	columns?: string[][];
	/** Keys rendered last, under a muted "Advanced" divider. Not repeated
	 *  in `fields`. */
	advanced?: string[];
	/** A named summary component rendered under the section blurb. An
	 *  unrecognised name (or none) renders nothing. */
	summary?: 'tv-episodes';
}

/** The section shape `sectionFields()` hands the form: keys already split
 *  into their layout buckets, none repeated across buckets. */
export interface SectionFieldGroups {
	title: string;
	blurb?: string;
	summary?: 'tv-episodes';
	columns: ConfigFieldMeta[][];
	fields: ConfigFieldMeta[];
	advanced: ConfigFieldMeta[];
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
			title: 'TV episodes',
			blurb: 'How ARM works out season and episode numbers for TV discs.',
			summary: 'tv-episodes',
			keys: ['disc_hint_sources', 'episode_sources', 'episode_auto_apply', 'episode_match_tolerance_seconds'],
			columns: [['disc_hint_sources'], ['episode_sources']],
			advanced: ['episode_match_tolerance_seconds']
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
			blurb: 'With "Review first", how long ARM waits for you to check the title before it rips anyway.',
			keys: ['hold_for_review', 'manual_wait_seconds']
		},
		{
			title: 'Decryption data',
			blurb: 'Key material MakeMKV needs for protected discs, refreshed in the background.',
			keys: ['community_keydb_enabled', 'makemkv_sdf_enabled']
		}
	],
	Transcoding: [{ title: 'Scheduling', keys: ['transcode_enabled', 'auto_transcode_on_idle'] }]
};

/** Maps the four API-key field keys (from the "API keys" section above) to
 *  the endpoint name POST /api/config/keys/{name}/check expects. */
export const KEY_CHECK_NAMES: Record<string, 'tmdb' | 'omdb' | 'tvdb' | 'makemkv'> = {
	tmdb_api_key: 'tmdb',
	omdb_api_key: 'omdb',
	tvdb_api_key: 'tvdb',
	makemkv_key: 'makemkv'
};

/** Display name per key-check service, for "Couldn't reach {service}". */
export const KEY_SERVICE_LABEL: Record<'tmdb' | 'omdb' | 'tvdb' | 'makemkv', string> = {
	tmdb: 'TMDb',
	omdb: 'OMDb',
	tvdb: 'TVDB',
	makemkv: 'MakeMKV'
};

/** The fields a setup walkthrough step renders: those tagged `setup_step`, in
 *  `setup_order`, plus any field whose widget lives on one of them
 *  (`part_of`), across every settings group (setup spec 2026-10-01 §7.2). */
export function stepFields(groups: SettingsGroup[], step: string): ConfigFieldMeta[] {
	const all = groups.flatMap((g) => g.fields);
	const tagged = all.filter((f) => f.setup_step === step).sort((a, b) => (a.setup_order ?? 0) - (b.setup_order ?? 0));
	const owners = new Set(tagged.map((f) => f.key));
	const parts = all.filter((f) => f.part_of != null && owners.has(f.part_of));
	return [...tagged, ...parts];
}

/** A synthetic group for SchemaConfigForm holding one setup step's fields. */
export function stepGroup(groups: SettingsGroup[], step: string): SettingsGroup {
	return { name: `setup:${step}`, fields: stepFields(groups, step) };
}

export function groupBlurb(group: string): string | undefined {
	return GROUP_BLURBS[group];
}

/** Split `fields` into the sections declared for `group`, in declared order,
 *  dropping empty sections and appending unmapped fields under the group
 *  name. Each section's own keys are further split into `columns`,
 *  `advanced` and the remaining `fields`, so a key named in `columns` or
 *  `advanced` is never repeated in `fields`. */
export function sectionFields(group: string, allFields: ConfigFieldMeta[]): SectionFieldGroups[] {
	// A `part_of` field is rendered by its owner's widget, never on its own.
	const fields = allFields.filter((f) => f.part_of == null);
	const byKey = new Map(fields.map((f) => [f.key, f]));
	const placed = new Set<string>();
	const out: SectionFieldGroups[] = [];
	for (const section of SECTIONS[group] ?? []) {
		const own = section.keys.map((k) => byKey.get(k)).filter((f): f is ConfigFieldMeta => f !== undefined);
		if (own.length === 0) continue;
		own.forEach((f) => placed.add(f.key));

		const columns = (section.columns ?? [])
			.map((col) => col.map((k) => byKey.get(k)).filter((f): f is ConfigFieldMeta => f !== undefined))
			.filter((col) => col.length > 0);
		const columnKeys = new Set(columns.flat().map((f) => f.key));

		const advanced = (section.advanced ?? [])
			.map((k) => byKey.get(k))
			.filter((f): f is ConfigFieldMeta => f !== undefined);
		const advancedKeys = new Set(advanced.map((f) => f.key));

		const plainFields = own.filter((f) => !columnKeys.has(f.key) && !advancedKeys.has(f.key));

		out.push({
			title: section.title,
			blurb: section.blurb,
			summary: section.summary,
			columns,
			fields: plainFields,
			advanced
		});
	}
	const rest = fields.filter((f) => !placed.has(f.key));
	if (rest.length > 0) out.push({ title: group, columns: [], fields: rest, advanced: [] });
	return out;
}
