import { describe, it, expect } from 'vitest';
import type { SetupView } from '$lib/types/api.gen';
import {
	STEPS,
	REVIEWABLE_STEPS,
	STATE_BADGE,
	nextStep,
	openSteps,
	prevStep,
	progressState,
	uiState,
	stepMeta
} from '../../../setup/steps';

describe('REVIEWABLE_STEPS', () => {
	it('is every step but Finish, in walkthrough order', () => {
		expect(REVIEWABLE_STEPS).toEqual(STEPS.slice(0, -1));
		expect(REVIEWABLE_STEPS.map((s) => s.id)).not.toContain('finish');
	});
});

describe('STATE_BADGE', () => {
	it('gives the text, glyph and class for each state', () => {
		expect(STATE_BADGE).toEqual({
			done: { text: 'Done', glyph: 'check', cls: 'chip-success' },
			skipped: { text: 'Skipped', glyph: 'minus-circle', cls: '' },
			attention: { text: 'Needs attention', glyph: 'warning', cls: 'chip-warning' },
			pending: { text: 'Not done', glyph: 'clock', cls: '' }
		});
	});
});

describe('openSteps', () => {
	it('returns skipped and attention steps in walkthrough order with their state', () => {
		const progress: SetupView['progress'] = {
			notifications: { state: 'skipped' },
			system: { state: 'attention' },
			metadata: { state: 'skipped' }
		};
		expect(openSteps(progress).map((o) => [o.step.id, o.state])).toEqual([
			['system', 'attention'],
			['metadata', 'skipped'],
			['notifications', 'skipped']
		]);
		expect(openSteps(progress)[0].step).toBe(stepMeta('system'));
	});

	it('leaves out done steps and steps with no entry', () => {
		const progress: SetupView['progress'] = { account: { state: 'done' }, drives: { state: 'skipped' } };
		expect(openSteps(progress).map((o) => o.step.id)).toEqual(['drives']);
	});

	it('leaves out the Finish step', () => {
		expect(openSteps({ finish: { state: 'skipped' } })).toEqual([]);
	});

	it('returns an empty list while progress is undefined', () => {
		expect(openSteps(undefined)).toEqual([]);
	});

	it('returns an empty list for empty progress', () => {
		expect(openSteps({})).toEqual([]);
	});
});

describe('progressState', () => {
	const progress: SetupView['progress'] = {
		account: { state: 'done' },
		system: { state: 'attention' },
		metadata: { state: 'skipped' }
	};

	it('returns each recorded state', () => {
		expect(progressState('account', progress)).toBe('done');
		expect(progressState('system', progress)).toBe('attention');
		expect(progressState('metadata', progress)).toBe('skipped');
	});

	it('returns null for a step with no entry', () => {
		expect(progressState('finish', progress)).toBeNull();
	});

	it('returns null for a state the UI does not know', () => {
		const unknown = { account: { state: 'weird' } } as unknown as SetupView['progress'];
		expect(progressState('account', unknown)).toBeNull();
	});
});

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

	it('names the metadata step Identification', () => {
		const m = stepMeta('metadata')!;
		expect(m.label).toBe('Identification');
		expect(m.title).toBe('Identification');
		expect(m.intro).toBe(
			'ARM looks up what is on each disc so your files get the right names. The disc databases, TVmaze and MusicBrainz need no key; TMDb, OMDb and TVDB do.'
		);
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

	it('gives only the notifications step a plain Skip for now button', () => {
		expect(STEPS.filter((s) => s.skipEmphasis).map((s) => s.id)).toEqual(['notifications']);
	});

	it('copy has no em dashes or single-character ellipses', () => {
		for (const s of STEPS) {
			for (const text of [s.label, s.title, s.intro]) {
				expect(text).not.toMatch(/[—…]/);
			}
		}
	});
});
