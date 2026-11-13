import { describe, expect, it } from 'vitest';
import type { DiscRouteSummary } from '$lib/types/api.gen';
import { discKindLabel, exampleMovie, routeCells } from '../../sessions/disc-routes';

const EMPTY_ROUTE: DiscRouteSummary = {
	kind: 'movie',
	session_id: null,
	session_name: null,
	rip_summary: null,
	transcode_summary: null,
	output_template: null
};

function makeRoute(over: Partial<DiscRouteSummary> = {}): DiscRouteSummary {
	return { ...EMPTY_ROUTE, ...over };
}

describe('discKindLabel', () => {
	it.each([
		['movie', 'Movie'],
		['tv', 'TV'],
		['music', 'Music CD'],
		['data', 'Data'],
		['iso', 'ISO']
	])('labels %s as %s', (kind, label) => {
		expect(discKindLabel(kind)).toBe(label);
	});

	it('returns an unknown kind unchanged', () => {
		expect(discKindLabel('vhs')).toBe('vhs');
	});
});

describe('routeCells', () => {
	it('fills every cell from a route that has all values', () => {
		const route = makeRoute({
			session_name: 'Movie rip',
			rip_summary: 'Main feature',
			transcode_summary: 'H.265',
			output_template: '{title} ({year}).{ext}'
		});
		expect(routeCells(route)).toEqual([
			{ label: 'Rips', value: 'Main feature', sub: 'Movie rip', empty: 'No session' },
			{ label: 'Encodes', value: 'H.265', empty: 'No encode' },
			{ label: 'Lands in', value: 'Fight Club (1999).mkv', mono: true, empty: 'Not set' }
		]);
	});

	it('leaves values null for a route with none', () => {
		expect(routeCells(makeRoute())).toEqual([
			{ label: 'Rips', value: null, sub: null, empty: 'No session' },
			{ label: 'Encodes', value: null, empty: 'No encode' },
			{ label: 'Lands in', value: null, mono: true, empty: 'Not set' }
		]);
	});
});

describe('exampleMovie', () => {
	it('resolves the template of a movie route', () => {
		expect(exampleMovie([makeRoute({ output_template: '{title}.{ext}' })])).toBe('Fight Club.mkv');
	});

	it('returns null for a movie route with an empty template', () => {
		expect(exampleMovie([makeRoute({ output_template: '' })])).toBeNull();
	});

	it('returns null when only a TV route has a template', () => {
		expect(exampleMovie([makeRoute({ kind: 'tv', output_template: '{show}.{ext}' })])).toBeNull();
	});

	it('uses the first movie route that has a template', () => {
		const routes = [makeRoute({ output_template: '{title}.{ext}' }), makeRoute({ output_template: '{year}.{ext}' })];
		expect(exampleMovie(routes)).toBe('Fight Club.mkv');
	});

	it('returns null when there are no routes', () => {
		expect(exampleMovie([])).toBeNull();
	});
});
