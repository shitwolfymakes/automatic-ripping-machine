import { describe, it, expect } from 'vitest';
import { formatRotate, parseRotate } from '../rotate';

describe('rotate', () => {
	it('round-trips every angle and flip', () => {
		for (const angle of [0, 90, 180, 270] as const) {
			for (const hflip of [false, true]) {
				expect(parseRotate(formatRotate({ angle, hflip }))).toEqual({ angle, hflip });
			}
		}
	});

	it('formats as angle=N:hflip=0|1', () => {
		expect(formatRotate({ angle: 90, hflip: true })).toBe('angle=90:hflip=1');
		expect(formatRotate({ angle: 0, hflip: false })).toBe('angle=0:hflip=0');
	});

	it.each(['', 'nonsense', 'angle=45:hflip=0', 'angle=:hflip=', 'angle=90x', 'hflip=2'])(
		'parses malformed %j to no rotation and no flip',
		(s) => {
			expect(parseRotate(s)).toEqual({ angle: 0, hflip: false });
		}
	);

	it('reads each part independently', () => {
		expect(parseRotate('angle=270')).toEqual({ angle: 270, hflip: false });
		expect(parseRotate('hflip=1')).toEqual({ angle: 0, hflip: true });
	});
});
