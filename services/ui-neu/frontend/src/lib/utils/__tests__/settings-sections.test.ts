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
		// in one column group, episode_auto_apply in the plain stack,
		// episode_match_tolerance_seconds after the Advanced divider.
		const fields = [
			meta('disc_hint_sources', 'ranked'),
			meta('episode_sources', 'ranked'),
			meta('episode_auto_apply'),
			meta('episode_match_tolerance_seconds', 'int')
		];

		const sections = sectionFields('Metadata', fields);
		const tvEpisodes = sections.find((s) => s.title === 'TV episodes');
		expect(tvEpisodes).toBeDefined();

		expect(tvEpisodes?.columns.map((col) => col.map((f) => f.key))).toEqual([['disc_hint_sources', 'episode_sources']]);
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
