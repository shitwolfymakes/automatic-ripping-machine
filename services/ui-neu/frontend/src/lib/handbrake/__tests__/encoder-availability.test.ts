import { describe, expect, it } from 'vitest';
import type { EncoderAvailabilityView } from '$lib/types/api.gen';
import { availabilityLabel, findAvailability } from '../encoder-availability';

const catalog = [
	{ id: 'x265', label: 'x265 (CPU)', available: true },
	{ id: 'nvenc_h265', label: 'NVIDIA NVENC', available: false }
] as EncoderAvailabilityView[];

describe('findAvailability', () => {
	it('finds the entry by catalog id', () => {
		expect(findAvailability(catalog, 'nvenc_h265')).toBe(catalog[1]);
	});

	it('is undefined for an id the catalog does not list', () => {
		expect(findAvailability(catalog, 'nope')).toBeUndefined();
	});
});

describe('availabilityLabel', () => {
	it('is the catalog label for a listed id', () => {
		expect(availabilityLabel(catalog, 'x265', 'fallback')).toBe('x265 (CPU)');
	});

	it('is the caller fallback for an unlisted id', () => {
		expect(availabilityLabel(catalog, 'nope', 'This preset')).toBe('This preset');
	});
});
