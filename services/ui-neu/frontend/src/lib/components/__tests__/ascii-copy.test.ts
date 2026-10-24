import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import EpisodeRows from '../episodes/EpisodeRows.svelte';
import type { EpisodeRow } from '../episodes/episodeModel';

// UI copy is ASCII: an empty value is "-", a trailing wait is "...", and joined
// facts are separated by ", ". Comments and <style> blocks are not copy.
const FILES = [
	'DiscReviewWidget.svelte',
	'JobInfoForm.svelte',
	'episodes/EpisodeMatchPanel.svelte',
	'episodes/EpisodeRows.svelte',
	'episodes/RerunPanel.svelte'
];
const NON_ASCII = /[—–·…→✓✗⚠]/;

function copyOf(file: string): string {
	return readFileSync(resolve(__dirname, '..', file), 'utf8')
		.replace(/<style[\s\S]*?<\/style>/g, '')
		.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/\/\*[\s\S]*?\*\//g, '')
		.split('\n')
		.filter((line) => !/^\s*\/\//.test(line))
		.join('\n');
}

afterEach(cleanup);

describe('ASCII copy', () => {
	it.each(FILES)('%s has no typographic punctuation in its copy', (file) => {
		const bad = copyOf(file)
			.split('\n')
			.filter((l) => NON_ASCII.test(l));
		expect(bad, `${file} has non-ASCII copy`).toEqual([]);
	});

	it('shows "-" for an unplaced row', () => {
		const row: EpisodeRow = {
			trackId: 'trk_0',
			ref: 't00',
			length: '10:00',
			code: 'Not placed',
			name: '',
			origin: { kind: 'none', source: null },
			confidence: null,
			proposed: null,
			changed: false,
			handSet: false,
			season: null,
			seconds: null
		};
		renderComponent(EpisodeRows, { rows: [row], fileNames: new Map() });
		expect(screen.getAllByText('-').length).toBeGreaterThan(0);
	});
});
