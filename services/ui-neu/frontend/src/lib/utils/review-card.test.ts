import { describe, it, expect } from 'vitest';
import { reviewStatusLabel, type StatusLabelFlags } from './review-card';

const none: StatusLabelFlags = { previouslyRipped: false, suggestion: false, reviewGate: false, postRip: false };

describe('reviewStatusLabel', () => {
	it('says Awaiting Review when no flag is set', () => {
		expect(reviewStatusLabel(none)).toBe('Awaiting Review');
	});
	it('says Ripped when only postRip is set', () => {
		expect(reviewStatusLabel({ ...none, postRip: true })).toBe('Ripped: Apply Session');
	});
	it('says Ready when only reviewGate is set', () => {
		expect(reviewStatusLabel({ ...none, reviewGate: true })).toBe('Ready: Review & Start');
	});
	it('says Confirm the title when only suggestion is set', () => {
		expect(reviewStatusLabel({ ...none, suggestion: true })).toBe('Confirm the title: use it or search');
	});
	it('says Already ripped when only previouslyRipped is set', () => {
		expect(reviewStatusLabel({ ...none, previouslyRipped: true })).toBe('Already ripped: Rip again or Discard');
	});
	it('lets previouslyRipped win over every other flag', () => {
		expect(reviewStatusLabel({ previouslyRipped: true, suggestion: true, reviewGate: true, postRip: true })).toBe(
			'Already ripped: Rip again or Discard'
		);
	});
	it('lets suggestion win over reviewGate and postRip', () => {
		expect(reviewStatusLabel({ ...none, suggestion: true, reviewGate: true, postRip: true })).toBe(
			'Confirm the title: use it or search'
		);
	});
	it('lets reviewGate win over postRip', () => {
		expect(reviewStatusLabel({ ...none, reviewGate: true, postRip: true })).toBe('Ready: Review & Start');
	});
});
