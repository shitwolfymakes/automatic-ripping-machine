import { describe, expect, it } from 'vitest';
import { sectionFields } from '../settings-sections';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

const meta = (key: string, type = 'bool'): ConfigFieldMeta => ({
	key,
	group: 'Metadata',
	tier: 'operator',
	label: key,
	help: '',
	type,
	editable: true
});

describe('sectionFields layout hints', () => {
	it('splits columns, fields and advanced, each key once', () => {
		// The real "TV episodes" section: disc_hint_sources + episode_sources
		// side by side (one column each), episode_auto_apply in the plain
		// stack, episode_match_tolerance_seconds after the Advanced divider.
		const fields = [
			meta('disc_hint_sources', 'ranked'),
			meta('episode_sources', 'ranked'),
			meta('episode_auto_apply'),
			meta('episode_match_tolerance_seconds', 'int')
		];

		const sections = sectionFields('Metadata', fields);
		const tvEpisodes = sections.find((s) => s.title === 'TV episodes');
		expect(tvEpisodes).toBeDefined();

		expect(tvEpisodes?.columns.map((col) => col.map((f) => f.key))).toEqual([
			['disc_hint_sources'],
			['episode_sources']
		]);
		expect(tvEpisodes?.fields.map((f) => f.key)).toEqual(['episode_auto_apply']);
		expect(tvEpisodes?.advanced.map((f) => f.key)).toEqual(['episode_match_tolerance_seconds']);
		expect(tvEpisodes?.summary).toBe('tv-episodes');

		// Each key appears in exactly one bucket.
		const allKeys = [
			...tvEpisodes!.columns.flat().map((f) => f.key),
			...tvEpisodes!.fields.map((f) => f.key),
			...tvEpisodes!.advanced.map((f) => f.key)
		];
		expect(allKeys.sort()).toEqual(fields.map((f) => f.key).sort());
	});

	it('drops the section entirely when none of its keys are present', () => {
		const sections = sectionFields('Metadata', [meta('metadata_provider', 'enum')]);
		expect(sections.find((s) => s.title === 'TV episodes')).toBeUndefined();
	});

	it('returns empty columns and advanced for a section that declares neither', () => {
		const sections = sectionFields('Metadata', [meta('metadata_provider', 'enum')]);
		const lookup = sections.find((s) => s.title === 'Lookup');
		expect(lookup?.columns).toEqual([]);
		expect(lookup?.advanced).toEqual([]);
		expect(lookup?.fields.map((f) => f.key)).toEqual(['metadata_provider']);
	});

	it('puts unmapped fields in a trailing card titled after the group', () => {
		const sections = sectionFields('Metadata', [meta('some_future_field')]);
		expect(sections).toHaveLength(1);
		expect(sections[0]).toMatchObject({ title: 'Metadata', columns: [], advanced: [] });
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
			{ name: 'Metadata', fields: [f('tmdb_api_key', { setup_step: 'metadata', setup_order: 1 })] }
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
