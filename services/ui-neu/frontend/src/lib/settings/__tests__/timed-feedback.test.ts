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

	it("clears a second message when the first one's timer fires", () => {
		// The early-clear defect: show never cancels an earlier timer, so the
		// first message's timer clears the second message early.
		const feedback = new TimedFeedback();
		feedback.show('success', 'First');
		vi.advanceTimersByTime(FEEDBACK_MS - 1000);
		feedback.show('error', 'Second');
		vi.advanceTimersByTime(1000);
		expect(feedback.current).toBeNull();
	});
});
