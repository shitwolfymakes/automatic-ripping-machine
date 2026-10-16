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
	/** A named component that renders the whole section from the group's
	 *  fields (its keys are claimed here, so none fall through to the
	 *  trailing card). The section keeps no columns, fields or advanced. */
	custom?: 'identity';
	/** One help line rendered under the section's fields. */
	note?: string;
	/** Hide each field's own help text in this section (the `note` covers it). */
	hideFieldHelp?: boolean;
	/** Keys this section owns but does not render (a setting with a single
	 *  option, kept at its default until a second option exists). */
	hidden?: string[];
}

/** The section shape `sectionFields()` hands the form: keys already split
 *  into their layout buckets, none repeated across buckets. */
export interface SectionFieldGroups {
	title: string;
	blurb?: string;
	custom?: 'identity';
	note?: string;
	hideFieldHelp?: boolean;
	columns: ConfigFieldMeta[][];
	fields: ConfigFieldMeta[];
	advanced: ConfigFieldMeta[];
}

const GROUP_BLURBS: Record<string, string> = {
	Identification: 'How ARM works out what a disc is, and where it looks titles up.',
	Keys: 'Keys and the service snapshots ARM uses to identify discs.',
	Ripping: 'What happens when a disc goes in.',
	Transcoding: 'When finished rips are handed to the transcoder.'
};

const SECTIONS: Record<string, SettingsSection[]> = {
	Identification: [
		{
			title: 'Search',
			note: "The service the job page's search box uses for each media type.",
			hideFieldHelp: true,
			keys: ['search_provider_movie', 'search_provider_tv', 'search_provider_music'],
			columns: [['search_provider_movie'], ['search_provider_tv']],
			// Music has one search service (MusicBrainz); nothing to choose yet.
			hidden: ['search_provider_music']
		},
		{
			title: 'Identity',
			blurb: 'How ARM works out what a disc is before it rips, and when it trusts the answer.',
			keys: [
				'thediscdb_enabled',
				'crc64service_enabled',
				'movie_sources',
				'episode_sources',
				'music_sources',
				'episode_match_tolerance_seconds',
				'movie_auto_apply',
				'episode_auto_apply',
				'music_auto_apply',
				'disc_hint_sources'
			],
			custom: 'identity'
		}
	],
	Keys: [
		{ title: 'MakeMKV', keys: ['makemkv_key'] },
		{
			title: 'API keys',
			blurb:
				'Stored on the server. A key that is already set shows as hidden; leave it blank to keep it. Environment variables seed a key once at first boot; after that only what is saved here is used.',
			keys: ['tmdb_api_key', 'omdb_api_key', 'tvdb_api_key']
		},
		{
			title: 'TheDiscDB',
			blurb: 'The local snapshot ARM matches discs against.',
			keys: ['thediscdb_refresh_days']
		}
	],
	Ripping: [
		{
			title: 'On insert',
			keys: ['auto_rip_on_insert', 'block_on_miss', 'on_previously_ripped', 'ripping_paused']
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

/** Maps the four key field keys (the Keys tab's "API keys" and "MakeMKV" sections) to
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

/** The Settings tab (a `#<tab>` hash) that renders a schema group: the config
 *  groups keep their own name, the others fold into their lower-case screen tab. */
export function settingsTabFor(groupName: string): string {
	return ['Identification', 'Keys', 'Ripping'].includes(groupName) ? groupName : groupName.toLowerCase();
}

/** Svelte context key: Settings publishes a getter for the loaded schema groups
 *  so field widgets can deep-link to another tab's field (`#<tab>/<key>`). */
export const SETTINGS_SCHEMA_CONTEXT = Symbol('settings-schema');

/** The Settings deep link for a field: `#<tab>/<key>` on the tab that renders
 *  the field's own schema group, else the field's anchor on the current page
 *  (`#setting-<key>`, e.g. the setup walkthrough, which has no tabs). */
export function settingsFieldHref(key: string, groups: SettingsGroup[] | undefined): string {
	const group = groups?.find((g) => g.fields.some((f) => f.key === key))?.name;
	return group ? `#${settingsTabFor(group)}/${key}` : `#setting-${key}`;
}

/** Retired Settings tab names in old bookmarks and links, mapped to the tab
 *  that replaced them; any other name is returned unchanged. */
export function legacyTab(tab: string): string {
	if (tab === 'Metadata') return 'Identification';
	if (tab === 'appearance') return 'themes';
	return tab;
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

		if (section.custom) {
			out.push({
				title: section.title,
				blurb: section.blurb,
				custom: section.custom,
				columns: [],
				fields: [],
				advanced: []
			});
			continue;
		}

		const columns = (section.columns ?? [])
			.map((col) => col.map((k) => byKey.get(k)).filter((f): f is ConfigFieldMeta => f !== undefined))
			.filter((col) => col.length > 0);
		const columnKeys = new Set(columns.flat().map((f) => f.key));

		const advanced = (section.advanced ?? [])
			.map((k) => byKey.get(k))
			.filter((f): f is ConfigFieldMeta => f !== undefined);
		const advancedKeys = new Set(advanced.map((f) => f.key));

		const hiddenKeys = new Set(section.hidden ?? []);
		const plainFields = own.filter((f) => !columnKeys.has(f.key) && !advancedKeys.has(f.key) && !hiddenKeys.has(f.key));

		out.push({
			title: section.title,
			blurb: section.blurb,
			note: section.note,
			hideFieldHelp: section.hideFieldHelp,
			columns,
			fields: plainFields,
			advanced
		});
	}
	const rest = fields.filter((f) => !placed.has(f.key));
	if (rest.length > 0) out.push({ title: group, columns: [], fields: rest, advanced: [] });
	return out;
}
