import { describe, it, expect } from 'vitest';
import { applyNote, identifyNote } from '$lib/jobs/action-notes';

const resolved = (fan_out?: unknown[]) => ({ fan_out }) as any;
const applied = (status: string, tasks?: unknown[]) => ({ session_application: { status }, tasks }) as any;

describe('identifyNote', () => {
	it('has no note when the resolve has no fan_out', () => {
		expect(identifyNote(resolved())).toBeNull();
	});
	it('has no note when fan_out is empty', () => {
		expect(identifyNote(resolved([]))).toBeNull();
	});
	it('says one session resumed, singular', () => {
		expect(identifyNote(resolved([{}]))).toBe('1 session resumed');
	});
	it('says several sessions resumed, plural', () => {
		expect(identifyNote(resolved([{}, {}, {}]))).toBe('3 sessions resumed');
	});
});

describe('applyNote', () => {
	it('says the rip has to finish when parked pre-rip', () => {
		expect(applyNote(applied('waiting_identify'), false)).toBe('Session parked; applies when the rip finishes');
	});
	it('just says waiting when parked post-rip', () => {
		expect(applyNote(applied('waiting_identify'), true)).toBe('Session parked; waiting');
	});
	it('counts 0 tasks when the response has no tasks field', () => {
		expect(applyNote(applied('applied'), false)).toBe('0 transcode tasks queued');
	});
	it('says one transcode task queued, singular', () => {
		expect(applyNote(applied('applied', [{}]), false)).toBe('1 transcode task queued');
	});
	it('says several transcode tasks queued, plural', () => {
		expect(applyNote(applied('applied', [{}, {}]), true)).toBe('2 transcode tasks queued');
	});
});
