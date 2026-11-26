import { describe, it, expect } from 'vitest';
import type { SettingIssue } from '$lib/types/api.gen';
import { ApiError, NETWORK_ERROR_MESSAGE } from '../client';
import { saveFailure } from '../save-failure';

const issue = (over: Partial<SettingIssue>): SettingIssue => ({
	key: 'VideoQualitySlider',
	encoder: null,
	code: 'out_of_range',
	message: 'Too high',
	...over
});

describe('saveFailure', () => {
	it('marks fields for a 422 with an issue list', () => {
		const issues = [issue({})];
		const f = saveFailure(new ApiError(422, 'API 422', { detail: { issues } }));
		expect(f).toEqual({ issues, message: 'Fix the marked settings and save again.', schemaMissing: false });
	});

	it('keeps a 422 without issues as a plain message', () => {
		expect(saveFailure(new ApiError(422, 'Bad name', { detail: 'Bad name' }))).toEqual({
			issues: null,
			message: 'Bad name',
			schemaMissing: false
		});
		expect(saveFailure(new ApiError(422, 'Bad', null)).issues).toBeNull();
	});

	it('flags a 503 as no schema loaded', () => {
		expect(saveFailure(new ApiError(503, 'No HandBrake schema loaded yet', null))).toEqual({
			issues: null,
			message: 'No HandBrake schema loaded yet',
			schemaMissing: true
		});
	});

	it('uses the network message for anything else', () => {
		expect(saveFailure(new TypeError('fetch failed')).message).toBe(NETWORK_ERROR_MESSAGE);
	});
});
