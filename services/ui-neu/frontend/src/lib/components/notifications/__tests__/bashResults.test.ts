import { describe, it, expect } from 'vitest';
import { armContext, incompleteInput, isCustomized } from '../bashResults';

const inputs = [{ key: 'TO', label: 'Recipient' }];

describe('incompleteInput', () => {
	it('is null for a null error', () => {
		expect(incompleteInput(null, inputs)).toBeNull();
	});

	it('is null for an undefined error', () => {
		expect(incompleteInput(undefined, inputs)).toBeNull();
	});

	it('is null for any other error', () => {
		expect(incompleteInput('script exploded', inputs)).toBeNull();
	});

	it('names a listed input by its label', () => {
		expect(incompleteInput('input TO is required', inputs)).toBe('Recipient');
	});

	it('names an unlisted input by its key', () => {
		expect(incompleteInput('input SMTP_PASS is required', inputs)).toBe('SMTP_PASS');
	});

	it('ignores a lowercase key', () => {
		expect(incompleteInput('input to is required', inputs)).toBeNull();
	});

	it('ignores text around the message', () => {
		expect(incompleteInput('error: input TO is required.', inputs)).toBeNull();
	});
});

describe('isCustomized', () => {
	it('is false for no template', () => {
		expect(isCustomized(undefined)).toBe(false);
	});

	it('is false for an empty template', () => {
		expect(isCustomized({})).toBe(false);
	});

	it('is true for only a title', () => {
		expect(isCustomized({ title: 'T' })).toBe(true);
	});

	it('is true for only a body', () => {
		expect(isCustomized({ body: 'B' })).toBe(true);
	});

	it('is false for empty inputs', () => {
		expect(isCustomized({ inputs: {} })).toBe(false);
	});

	it('is true when an input is set', () => {
		expect(isCustomized({ inputs: { TO: 'x' } })).toBe(true);
	});
});

describe('armContext', () => {
	it('keeps the ARM_ variables in order', () => {
		const env = { ARM_B: '2', TO: 'x', ARM_A: '1' };
		expect(armContext(env)).toEqual([
			['ARM_B', '2'],
			['ARM_A', '1']
		]);
	});

	it('is empty for an empty env', () => {
		expect(armContext({})).toEqual([]);
	});
});
