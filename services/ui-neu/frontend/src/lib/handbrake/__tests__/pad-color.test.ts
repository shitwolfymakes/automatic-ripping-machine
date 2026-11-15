import { describe, it, expect } from 'vitest';
import { PAD_CUSTOM, padColorView } from '../pad-color';

const names = ['black', 'white'];

describe('padColorView', () => {
	it('selects a listed name', () => {
		expect(padColorView('white', names, false)).toEqual({ selected: 'white', custom: false, text: '' });
	});

	it('reads an unlisted value as custom and keeps its text', () => {
		expect(padColorView('#1a2b3c', names, false)).toEqual({ selected: PAD_CUSTOM, custom: true, text: '#1a2b3c' });
	});

	it('stays custom once Custom is picked, even for a listed name or no value', () => {
		expect(padColorView('black', names, true)).toEqual({ selected: PAD_CUSTOM, custom: true, text: 'black' });
		expect(padColorView('', names, false)).toEqual({ selected: '', custom: false, text: '' });
	});
});
