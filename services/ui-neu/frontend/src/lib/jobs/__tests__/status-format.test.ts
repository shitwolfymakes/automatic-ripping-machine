import { describe, it, expect } from 'vitest';
import { statusColor, statusLabel, statusAccentVar } from '../status-format';

describe('statusColor', () => {
	it.each<[string | null, string]>([
		// v3 JobStatus
		['created', 'status-scanning'],
		['awaiting_user_id', 'status-warning'],
		['awaiting_review', 'status-warning'],
		['identified', 'status-active'],
		['ripping', 'status-active'],
		['ripped', 'status-success'],
		['ripped_partial', 'status-warning'],
		['ripped_awaiting_identify', 'status-warning'],
		['abandoned', 'status-unknown'],
		['failed', 'status-error'],
		// effective statuses
		['transcoding', 'status-processing'],
		['complete', 'status-success'],
		['transcode_failed', 'status-error'],
		// task / track / application statuses
		['done', 'status-success'],
		['queued', 'status-unknown'],
		['in_progress', 'status-unknown'],
		['running', 'status-unknown'],
		['cancelled', 'status-unknown'],
		['waiting_identify', 'status-warning'],
		['done_partial', 'status-error'],
		// Fallthrough
		['unknown', 'status-unknown'],
		[null, 'status-unknown'],
		// Removed v2 names now fall through to status-unknown
		['video_ripping', 'status-unknown'],
		['success', 'status-unknown'],
		['error', 'status-unknown']
	])('statusColor(%s) = %s', (input, expected) => {
		expect(statusColor(input)).toBe(expected);
	});
});

describe('statusLabel', () => {
	it.each<[string | null, string]>([
		['created', 'Created'],
		['awaiting_review', 'Ready: review'],
		['ripping', 'Ripping'],
		['failed', 'Failed'],
		['transcoding', 'Transcoding'],
		['complete', 'Complete'],
		['transcode_failed', 'Transcode failed'],
		// TrackStatus / TranscodeTaskStatus
		['queued', 'Queued'],
		['in_progress', 'In Progress'],
		['done', 'Done'],
		['running', 'Running'],
		['waiting_identify', 'Waiting to identify'],
		['done_partial', 'Done (partial)'],
		// Unmapped statuses humanize
		['video_ripping', 'Video Ripping'],
		// A doubled underscore leaves an empty word, kept as is
		['some__state', 'Some  State'],
		[null, 'Unknown']
	])('statusLabel(%s) = %s', (input, expected) => {
		expect(statusLabel(input)).toBe(expected);
	});
});

describe('statusAccentVar', () => {
	it.each<[string | null | undefined, string]>([
		['created', 'var(--color-status-scanning)'],
		['ripping', 'var(--color-status-ripping)'],
		['identified', 'var(--color-status-ripping)'],
		['transcoding', 'var(--color-status-transcoding)'],
		['awaiting_user_id', 'var(--color-status-waiting)'],
		['awaiting_review', 'var(--color-status-waiting)'],
		['waiting_identify', 'var(--color-status-waiting)'],
		['complete', 'var(--color-status-success)'],
		['ripped', 'var(--color-status-success)'],
		['done', 'var(--color-status-success)'],
		['failed', 'var(--color-status-error)'],
		['transcode_failed', 'var(--color-status-error)'],
		['done_partial', 'var(--color-status-error)'],
		['in_progress', 'var(--color-primary)'],
		['running', 'var(--color-primary)'],
		[null, 'var(--color-primary)'],
		[undefined, 'var(--color-primary)'],
		['something-new', 'var(--color-primary)']
	])('statusAccentVar(%s) = %s', (input, expected) => {
		expect(statusAccentVar(input)).toBe(expected);
	});
});
