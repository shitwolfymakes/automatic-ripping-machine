import { describe, it, expect } from 'vitest';
import { mediaTypesCompatible } from './sessions';

describe('mediaTypesCompatible (mirrors auto_session._media_types_compatible)', () => {
	it.each([
		['movie', 'movie', true],
		['movie', 'tv', true],
		['tv', 'movie', true],
		['movie', 'iso', true],
		['data', 'iso', true],
		['tv', 'data', true],
		['data', 'data', true],
		['music', 'music', true],
		['music', 'movie', false],
		['movie', 'music', false],
		['music', 'iso', false],
		['data', 'movie', false]
	])('job %s, session %s -> %s', (job, session, expected) => {
		expect(mediaTypesCompatible(job, session)).toBe(expected);
	});
});
