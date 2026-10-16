import { describe, expect, it } from 'vitest';
import { groupBlurb, legacyTab, sectionFields, settingsFieldHref, settingsTabFor } from '../settings-sections';
import type { ConfigFieldMeta, SettingsGroup } from '$lib/types/api.gen';

const meta = (key: string, type = 'bool'): ConfigFieldMeta => ({
	key,
	group: 'Identification',
	tier: 'operator',
	label: key,
	help: '',
	type,
	editable: true
});

describe('sectionFields layout hints', () => {
	const IDENTITY_KEYS = [
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
	];
	const SEARCH_KEYS = ['search_provider_movie', 'search_provider_tv', 'search_provider_music'];

	it('lays out Identification as a three-column Search card and the custom Identity card', () => {
		const fields = [...SEARCH_KEYS, ...IDENTITY_KEYS].map((k) => meta(k));
		const sections = sectionFields('Identification', fields);

		expect(sections.map((s) => s.title)).toEqual(['Search', 'Identity']);
		const [search, identity] = sections;
		expect(search.columns.map((col) => col.map((f) => f.key))).toEqual([
			['search_provider_movie'],
			['search_provider_tv'],
			['search_provider_music']
		]);
		expect(search.fields).toEqual([]);
		expect(search.custom).toBeUndefined();

		expect(identity.custom).toBe('identity');
		expect(identity.blurb).toBe('How ARM works out what a disc is before it rips, and when it trusts the answer.');
		expect(identity.columns).toEqual([]);
		expect(identity.fields).toEqual([]);
		expect(identity.advanced).toEqual([]);
	});

	it('gives the Search card one help line and hides the per-select help', () => {
		const sections = sectionFields(
			'Identification',
			SEARCH_KEYS.map((k) => meta(k))
		);
		expect(sections[0].note).toBe("The service the job page's search box uses for each media type.");
		expect(sections[0].hideFieldHelp).toBe(true);
	});

	it('words the Identification tab blurb', () => {
		expect(groupBlurb('Identification')).toBe('How ARM works out what a disc is, and where it looks titles up.');
	});

	it('lays out Keys as MakeMKV, API keys, TheDiscDB', () => {
		const sections = sectionFields(
			'Keys',
			['tmdb_api_key', 'omdb_api_key', 'tvdb_api_key', 'thediscdb_refresh_days', 'makemkv_key'].map((k) =>
				meta(k, 'string')
			)
		);
		expect(sections.map((s) => s.title)).toEqual(['MakeMKV', 'API keys', 'TheDiscDB']);
		expect(sections[0].fields.map((f) => f.key)).toEqual(['makemkv_key']);
		expect(sections[1].fields.map((f) => f.key)).toEqual(['tmdb_api_key', 'omdb_api_key', 'tvdb_api_key']);
		expect(sections[2].fields.map((f) => f.key)).toEqual(['thediscdb_refresh_days']);
	});

	it('drops the section entirely when none of its keys are present', () => {
		const sections = sectionFields('Identification', [meta('search_provider_movie', 'enum')]);
		expect(sections.map((s) => s.title)).toEqual(['Search']);
	});

	it('returns empty columns and advanced for a section that declares neither', () => {
		const sections = sectionFields('Keys', [meta('tmdb_api_key', 'string')]);
		const keys = sections.find((s) => s.title === 'API keys');
		expect(keys?.columns).toEqual([]);
		expect(keys?.advanced).toEqual([]);
		expect(keys?.fields.map((f) => f.key)).toEqual(['tmdb_api_key']);
	});

	it('puts unmapped fields in a trailing card titled after the group', () => {
		const sections = sectionFields('Keys', [meta('some_future_field')]);
		expect(sections).toHaveLength(1);
		expect(sections[0]).toMatchObject({ title: 'Keys', columns: [], advanced: [] });
		expect(sections[0].fields.map((f) => f.key)).toEqual(['some_future_field']);
	});
});

describe('setup step field selection (setup spec 2026-10-01 §7.2)', () => {
	const f = (key: string, extra: Partial<ConfigFieldMeta> = {}): ConfigFieldMeta => ({
		key,
		group: 'Ripping',
		tier: 'operator',
		label: key,
		help: '',
		type: 'bool',
		editable: true,
		...extra
	});

	it('stepFields picks tagged fields across groups in setup_order, plus their part_of fields', async () => {
		const { stepFields } = await import('../settings-sections');
		const groups = [
			{
				name: 'Ripping',
				fields: [
					f('hold_for_review', { part_of: 'auto_rip_on_insert' }),
					f('auto_rip_on_insert', { setup_step: 'discs', setup_order: 1, widget: 'disc_handling' }),
					f('block_on_miss')
				]
			},
			{ name: 'Keys', fields: [f('tmdb_api_key', { setup_step: 'metadata', setup_order: 1 })] }
		];
		expect(stepFields(groups, 'discs').map((x) => x.key)).toEqual(['auto_rip_on_insert', 'hold_for_review']);
		expect(stepFields(groups, 'metadata').map((x) => x.key)).toEqual(['tmdb_api_key']);
		expect(stepFields(groups, 'drives')).toEqual([]);
	});

	it('stepGroup wraps them in a synthetic group', async () => {
		const { stepGroup } = await import('../settings-sections');
		const g = stepGroup(
			[
				{
					name: 'X',
					fields: [f('a', { setup_step: 'makemkv', setup_order: 2 }), f('b', { setup_step: 'makemkv', setup_order: 1 })]
				}
			],
			'makemkv'
		);
		expect(g.name).toBe('setup:makemkv');
		expect(g.fields.map((x) => x.key)).toEqual(['b', 'a']);
	});

	it('sectionFields never renders a part_of field on its own', () => {
		const out = sectionFields('Ripping', [
			f('auto_rip_on_insert', { widget: 'disc_handling' }),
			f('hold_for_review', { part_of: 'auto_rip_on_insert' }),
			f('manual_wait_seconds', { type: 'int' })
		]);
		const keys = out.flatMap((s) => [...s.columns.flat(), ...s.fields, ...s.advanced]).map((x) => x.key);
		expect(keys).toContain('auto_rip_on_insert');
		expect(keys).toContain('manual_wait_seconds');
		expect(keys).not.toContain('hold_for_review');
	});
});

describe('settingsTabFor', () => {
	it('keeps the config group names and lower-cases the screen tabs', () => {
		expect(settingsTabFor('Identification')).toBe('Identification');
		expect(settingsTabFor('Keys')).toBe('Keys');
		expect(settingsTabFor('Ripping')).toBe('Ripping');
		expect(settingsTabFor('Transcoding')).toBe('transcoding');
		expect(settingsTabFor('System')).toBe('system');
	});
});

describe('settingsFieldHref', () => {
	it("links to the tab of the field's own group, else to the field's anchor on this page", () => {
		const groups = [{ name: 'Keys', fields: [{ key: 'tvdb_api_key', label: 'TVDb API key' }] }] as SettingsGroup[];
		expect(settingsFieldHref('tvdb_api_key', groups)).toBe('#Keys/tvdb_api_key');
		expect(settingsFieldHref('tvdb_api_key', undefined)).toBe('#setting-tvdb_api_key');
		expect(settingsFieldHref('not_a_field', groups)).toBe('#setting-not_a_field');
	});

	it('uses the screen tab id for a group that folds into one', () => {
		const groups = [{ name: 'Transcoding', fields: [{ key: 'transcode_enabled' }] }] as SettingsGroup[];
		expect(settingsFieldHref('transcode_enabled', groups)).toBe('#transcoding/transcode_enabled');
	});
});

describe('legacyTab', () => {
	it('maps retired tab names to their successors and leaves the rest alone', () => {
		expect(legacyTab('Metadata')).toBe('Identification');
		expect(legacyTab('appearance')).toBe('themes');
		expect(legacyTab('Ripping')).toBe('Ripping');
		expect(legacyTab('drives')).toBe('drives');
	});
});
