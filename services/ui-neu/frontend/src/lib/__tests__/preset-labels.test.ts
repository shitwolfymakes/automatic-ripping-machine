import { describe, it, expect } from 'vitest';
import { humanizeOutputMode } from '../utils/preset-labels';

describe('humanizeOutputMode', () => {
	it.each([
		['tracks', 'Tracks'],
		['iso', 'ISO image'],
		['data_copy', 'File copy'],
		['folder', 'Disc backup (folder)']
	])('maps %s -> %s', (mode, label) => {
		expect(humanizeOutputMode(mode)).toBe(label);
	});

	it('passes an unknown mode through and shows - for none', () => {
		expect(humanizeOutputMode('weird')).toBe('weird');
		expect(humanizeOutputMode(null)).toBe('-');
	});
});
