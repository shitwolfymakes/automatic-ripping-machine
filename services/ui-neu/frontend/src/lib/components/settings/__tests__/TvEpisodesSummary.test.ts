import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import TvEpisodesSummary, { tvEpisodesEmptyNote } from '../TvEpisodesSummary.svelte';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

function defaults(): Record<string, unknown> {
	return {
		disc_hint_sources: ['bd_title', 'label'],
		episode_sources: ['tmdb', 'tvmaze', 'tvdb'],
		episode_auto_apply: true,
		episode_match_tolerance_seconds: 300
	};
}

function meta(): ConfigFieldMeta[] {
	return [
		{
			key: 'disc_hint_sources',
			group: 'Metadata',
			tier: 'operator',
			label: 'Read season and disc number from',
			help: '',
			type: 'ranked',
			editable: true,
			enum_values: ['bd_title', 'label'],
			enum_labels: { bd_title: 'Blu-ray disc title', label: 'Disc volume label' }
		},
		{
			key: 'episode_sources',
			group: 'Metadata',
			tier: 'operator',
			label: 'Episode sources',
			help: '',
			type: 'ranked',
			editable: true,
			enum_values: ['tmdb', 'tvmaze', 'tvdb'],
			enum_labels: { tmdb: 'TMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' },
			enum_requires: { tmdb: 'tmdb_api_key', tvdb: 'tvdb_api_key' }
		}
	];
}

afterEach(() => cleanup());

describe('TvEpisodesSummary', () => {
	it('summarises the defaults', () => {
		renderComponent(TvEpisodesSummary, { props: { values: defaults(), fields: meta() } });
		const group = screen.getByRole('group', { name: 'Summary' });
		expect(group).toHaveTextContent('Blu-ray disc title, Disc volume label');
		expect(group).toHaveTextContent('TMDb, TVmaze, TVDB');
		expect(group).toHaveTextContent('In order, runtime within 300 s');
		expect(group).toHaveTextContent('Apply confident matches');
	});

	it('follows reordering and removal', () => {
		renderComponent(TvEpisodesSummary, {
			props: { values: { ...defaults(), episode_sources: ['tvmaze', 'tmdb'] }, fields: meta() }
		});
		expect(screen.getByRole('group', { name: 'Summary' })).toHaveTextContent('TVmaze, TMDb');
	});

	it('explains an empty source list', () => {
		renderComponent(TvEpisodesSummary, { props: { values: { ...defaults(), episode_sources: [] }, fields: meta() } });
		const group = screen.getByRole('group', { name: 'Summary' });
		expect(group).toHaveTextContent('None');
		expect(group).toHaveTextContent('No automatic episode matching');
		expect(group).toHaveTextContent('Nothing to match');
	});

	it('reflects auto-apply off', () => {
		renderComponent(TvEpisodesSummary, {
			props: { values: { ...defaults(), episode_auto_apply: false }, fields: meta() }
		});
		expect(screen.getByRole('group', { name: 'Summary' })).toHaveTextContent('Suggest every match');
	});
});

describe('tvEpisodesEmptyNote', () => {
	it('returns the note for an empty episode_sources array', () => {
		expect(tvEpisodesEmptyNote({ ...defaults(), episode_sources: [] })).toBe(
			'With every source off, ARM does not match episodes automatically.'
		);
	});

	it('returns null when episode_sources has entries', () => {
		expect(tvEpisodesEmptyNote(defaults())).toBeNull();
	});

	it('returns null when episode_sources is missing or not an array', () => {
		expect(tvEpisodesEmptyNote({})).toBeNull();
		expect(tvEpisodesEmptyNote({ episode_sources: 'tmdb' })).toBeNull();
		expect(tvEpisodesEmptyNote({ episode_sources: null })).toBeNull();
	});
});
