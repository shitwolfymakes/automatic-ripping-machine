import { describe, expect, it } from 'vitest';
import { isoPhaseLabel } from '../../drives/iso-phase';

describe('isoPhaseLabel', () => {
	it('labels an image scan', () => {
		expect(isoPhaseLabel('scanning', 'iso')).toBe('Scanning image');
	});

	it('labels an image extraction', () => {
		expect(isoPhaseLabel('extracting', 'iso')).toBe('Unpacking image');
	});

	it('returns an unknown image phase as is', () => {
		expect(isoPhaseLabel('mystery', 'iso')).toBe('mystery');
	});

	it('labels a folder scan with the folder wording', () => {
		expect(isoPhaseLabel('scanning', 'folder')).toBe('Scanning disc folder');
	});

	it('labels a folder extraction with the image wording', () => {
		expect(isoPhaseLabel('extracting', 'folder')).toBe('Unpacking image');
	});

	it('returns an unknown folder phase as is', () => {
		expect(isoPhaseLabel('mystery', 'folder')).toBe('mystery');
	});

	it('returns an empty phase as is', () => {
		expect(isoPhaseLabel('', 'iso')).toBe('');
	});
});
