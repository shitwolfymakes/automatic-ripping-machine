import { describe, it, expect } from 'vitest';
import { encoderGroups } from '$lib/transcode/encoder-groups';
import type { EncoderAvailabilityView } from '$lib/types/api.gen';

const enc = (id: string, group: string) =>
	({ id, label: id, group, engine: 'x', available: true, reason: null }) as unknown as EncoderAvailabilityView;

describe('encoderGroups', () => {
	it('gives no groups for an empty catalog', () => {
		expect(encoderGroups([])).toEqual([]);
	});

	it('returns the groups in the fixed order, each with its heading', () => {
		const result = encoderGroups([
			enc('v', 'vaapi'),
			enc('n', 'nvenc'),
			enc('q', 'qsv'),
			enc('a', 'any'),
			enc('c', 'cpu'),
			enc('p', 'preset')
		]);
		expect(result.map((g) => [g.group, g.label])).toEqual([
			['preset', "HandBrake preset's own"],
			['cpu', 'CPU'],
			['any', 'Any GPU'],
			['qsv', 'Intel QSV'],
			['nvenc', 'NVIDIA NVENC'],
			['vaapi', 'AMD VAAPI']
		]);
	});

	it('keeps catalog order for several encoders in one group', () => {
		const result = encoderGroups([enc('c2', 'cpu'), enc('p', 'preset'), enc('c1', 'cpu')]);
		expect(result[1].encoders.map((e) => e.id)).toEqual(['c2', 'c1']);
	});

	it('leaves out groups with no encoders', () => {
		const result = encoderGroups([enc('n', 'nvenc'), enc('c', 'cpu')]);
		expect(result.map((g) => g.group)).toEqual(['cpu', 'nvenc']);
	});

	it('leaves out an encoder whose group is not in the order', () => {
		const result = encoderGroups([enc('x', 'mystery'), enc('c', 'cpu')]);
		expect(result.map((g) => g.group)).toEqual(['cpu']);
		expect(result.flatMap((g) => g.encoders).map((e) => e.id)).toEqual(['c']);
	});
});
