import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { FEEDBACK_MS, TimedFeedback } from '../timed-feedback.svelte';

describe('TimedFeedback', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('starts with no message', () => {
		expect(new TimedFeedback().current).toBeNull();
	});

	it('hold keeps a message up long after FEEDBACK_MS', () => {
		const feedback = new TimedFeedback();
		feedback.hold('error', 'Failed to load');
		vi.advanceTimersByTime(FEEDBACK_MS * 10);
		expect(feedback.current).toEqual({ type: 'error', message: 'Failed to load' });
	});

	it('show keeps a message up until just before FEEDBACK_MS, then clears it', () => {
		const feedback = new TimedFeedback();
		feedback.show('success', 'Saved');
		vi.advanceTimersByTime(FEEDBACK_MS - 1);
		expect(feedback.current).toEqual({ type: 'success', message: 'Saved' });
		vi.advanceTimersByTime(1);
		expect(feedback.current).toBeNull();
	});

	it("keeps a second message up for its own FEEDBACK_MS, not the first one's", () => {
		const feedback = new TimedFeedback();
		feedback.show('success', 'First');
		vi.advanceTimersByTime(FEEDBACK_MS - 1000);
		feedback.show('error', 'Second');
		vi.advanceTimersByTime(FEEDBACK_MS - 1);
		expect(feedback.current).toEqual({ type: 'error', message: 'Second' });
		vi.advanceTimersByTime(1);
		expect(feedback.current).toBeNull();
	});

	it('hold cancels a pending clear, so the held message stays', () => {
		const feedback = new TimedFeedback();
		feedback.show('success', 'Saved');
		feedback.hold('error', 'Failed to load');
		vi.advanceTimersByTime(FEEDBACK_MS * 2);
		expect(feedback.current).toEqual({ type: 'error', message: 'Failed to load' });
	});

	it('clears after the duration it was built with', () => {
		const feedback = new TimedFeedback(3000);
		feedback.show('success', 'Done');
		vi.advanceTimersByTime(2999);
		expect(feedback.current).not.toBeNull();
		vi.advanceTimersByTime(1);
		expect(feedback.current).toBeNull();
	});

	it('clear removes the message and cancels its pending clear', () => {
		const feedback = new TimedFeedback();
		feedback.show('success', 'Saved');
		feedback.clear();
		expect(feedback.current).toBeNull();
		expect(vi.getTimerCount()).toBe(0);
	});

	it('dispose cancels the pending clear and keeps the message as it is', () => {
		const feedback = new TimedFeedback();
		feedback.show('success', 'Saved');
		feedback.dispose();
		expect(vi.getTimerCount()).toBe(0);
		expect(feedback.current).toEqual({ type: 'success', message: 'Saved' });
	});

	it('dispose with no pending clear does nothing', () => {
		const feedback = new TimedFeedback();
		feedback.dispose();
		expect(feedback.current).toBeNull();
	});
});
