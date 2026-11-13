import { describe, it, expect } from 'vitest';
import { armContext, failedPreview, failedRun, incompleteInput, isCustomized, runSummary } from '../bash-results';

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

describe('failedPreview', () => {
	it('is a blank preview carrying the message and no result', () => {
		expect(failedPreview('boom')).toEqual({
			title: '',
			body: '',
			inputs: {},
			env: {},
			argv: [],
			error: 'boom',
			result: null
		});
	});
});

describe('failedRun', () => {
	it('is a failed run with no exit code carrying the message', () => {
		expect(failedRun('boom')).toEqual({
			ok: false,
			exit_code: null,
			duration_ms: 0,
			stdout: '',
			stderr: '',
			error: 'boom'
		});
	});
});

describe('runSummary', () => {
	const run = { ok: true, exit_code: 0, duration_ms: 400, stdout: '', stderr: '', error: null };

	it('says passed with the exit code and the duration', () => {
		expect(runSummary(run)).toBe('Passed: exit code 0 after 0.4s');
	});

	it('leaves the error out of a failure that has an exit code', () => {
		expect(runSummary({ ...run, ok: false, exit_code: 67, error: 'bad' })).toBe('Failed: exit code 67 after 0.4s');
	});

	it('adds the error to a failure with no exit code', () => {
		expect(runSummary({ ...run, ok: false, exit_code: null, error: 'bad' })).toBe('Failed after 0.4s: bad');
	});

	it('adds nothing to a failure with no exit code and no error', () => {
		expect(runSummary({ ...run, ok: false, exit_code: null, error: null })).toBe('Failed after 0.4s');
	});

	it('rounds the duration to one decimal', () => {
		expect(runSummary({ ...run, duration_ms: 1250 })).toBe(`Passed: exit code 0 after ${(1.25).toFixed(1)}s`);
	});
});
