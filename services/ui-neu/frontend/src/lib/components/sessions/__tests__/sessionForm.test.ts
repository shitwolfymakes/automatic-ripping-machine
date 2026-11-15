import { describe, it, expect } from 'vitest';
import {
	SESSION_FIELD_ORDER,
	parseOverrides,
	sessionErrors,
	sessionUpdate,
	sessionCreate,
	type SessionForm
} from '../sessionForm';

const form: SessionForm = {
	name: 'Movies',
	mediaType: 'movie',
	ripId: 'rip-1',
	tcId: 'tc-1',
	template: '{title}',
	overrides: { a: 1 }
};

describe('parseOverrides', () => {
	it('gives null for an empty field', () => {
		expect(parseOverrides('')).toBeNull();
	});

	it('gives null for a field of only spaces', () => {
		expect(parseOverrides('  \n\t ')).toBeNull();
	});

	it('gives the parsed object for JSON with spaces around it', () => {
		expect(parseOverrides('  {"a": 1}  ')).toEqual({ a: 1 });
	});

	it('throws a SyntaxError for text that is not JSON', () => {
		expect(() => parseOverrides('{nope')).toThrow(SyntaxError);
	});
});

describe('sessionUpdate', () => {
	it('gives the five fields and no media_type', () => {
		expect(sessionUpdate(form)).toEqual({
			name: 'Movies',
			rip_preset_id: 'rip-1',
			transcode_preset_id: 'tc-1',
			output_path_template: '{title}',
			overrides_json: { a: 1 }
		});
	});

	it('sends a null transcode preset for a blank tcId', () => {
		expect(sessionUpdate({ ...form, tcId: '' }).transcode_preset_id).toBeNull();
	});
});

describe('sessionCreate', () => {
	it('gives the five fields plus media_type', () => {
		expect(sessionCreate(form)).toEqual({
			name: 'Movies',
			media_type: 'movie',
			rip_preset_id: 'rip-1',
			transcode_preset_id: 'tc-1',
			output_path_template: '{title}',
			overrides_json: { a: 1 }
		});
	});
});

describe('sessionErrors', () => {
	it('flags each empty required field by its input id', () => {
		expect(sessionErrors({ name: '', ripId: '', template: '' })).toEqual({
			'sb-name': 'Name is required',
			'sb-rip': 'Choose a rip preset',
			'sb-path': 'Output path is required'
		});
	});

	it('has no errors once name, rip preset and template are set', () => {
		expect(sessionErrors(form)).toEqual({});
	});

	it('lists the required inputs in form order', () => {
		expect(SESSION_FIELD_ORDER).toEqual(['sb-name', 'sb-rip', 'sb-path']);
	});
});
