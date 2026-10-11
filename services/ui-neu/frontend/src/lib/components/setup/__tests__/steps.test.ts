import { describe, it, expect } from 'vitest';
import { STEPS, nextStep, prevStep, uiState, stepMeta } from '../steps';

describe('setup step registry', () => {
	it('lists the nine steps in walkthrough order', () => {
		expect(STEPS.map((s) => s.id)).toEqual([
			'account',
			'system',
			'drives',
			'makemkv',
			'metadata',
			'discs',
			'transcoding',
			'notifications',
			'finish'
		]);
		expect(STEPS.filter((s) => s.optional).map((s) => s.id)).toEqual(['metadata', 'transcoding', 'notifications']);
	});

	it('walks forward and back', () => {
		expect(nextStep('account')).toBe('system');
		expect(nextStep('finish')).toBeNull();
		expect(prevStep('account')).toBeNull();
		expect(prevStep('drives')).toBe('system');
		expect(stepMeta('nope')).toBeUndefined();
	});

	it('maps recorded progress to stepper states', () => {
		const progress = {
			account: { state: 'done' as const },
			system: { state: 'attention' as const },
			metadata: { state: 'skipped' as const }
		};
		expect(uiState('drives', 'drives', progress)).toBe('current');
		expect(uiState('account', 'drives', progress)).toBe('done');
		expect(uiState('system', 'drives', progress)).toBe('attention');
		expect(uiState('metadata', 'drives', progress)).toBe('skipped');
		expect(uiState('finish', 'drives', progress)).toBe('not-started');
	});

	it('copy has no em dashes or single-character ellipses', () => {
		for (const s of STEPS) {
			for (const text of [s.label, s.title, s.intro]) {
				expect(text).not.toMatch(/[—…]/);
			}
		}
	});
});
