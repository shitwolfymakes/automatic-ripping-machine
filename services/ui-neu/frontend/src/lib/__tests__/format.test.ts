import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
	formatBytes,
	statusColor,
	statusLabel,
	statusAccentVar,
	timeAgo,
	elapsedTime,
	etaTime,
	formatDateTime
} from '../utils/format';

describe('formatBytes', () => {
	it.each([
		[0, '0 B'],
		[1024, '1 KB'],
		[1048576, '1 MB'],
		[1073741824, '1 GB'],
		[1536, '1.5 KB']
	])('formatBytes(%i) = %s', (input, expected) => {
		expect(formatBytes(input)).toBe(expected);
	});
});

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
		[null, 'Unknown']
	])('statusLabel(%s) = %s', (input, expected) => {
		expect(statusLabel(input)).toBe(expected);
	});
});

describe('timeAgo', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});
	afterEach(() => vi.useRealTimers());

	it.each([
		[null, 'N/A'],
		['2025-06-15T11:59:30Z', '30s ago'],
		['2025-06-15T11:55:00Z', '5m ago'],
		['2025-06-15T09:00:00Z', '3h ago'],
		['2025-06-13T12:00:00Z', '2d ago']
	])('timeAgo(%s) = %s', (input, expected) => {
		expect(timeAgo(input)).toBe(expected);
	});
});

describe('elapsedTime', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});
	afterEach(() => vi.useRealTimers());

	it.each([
		[null, 'N/A'],
		['2025-06-15T11:59:45Z', '15s'],
		['2025-06-15T11:57:30Z', '2m 30s'],
		['2025-06-15T09:45:00Z', '2h 15m']
	])('elapsedTime(%s) = %s', (input, expected) => {
		expect(elapsedTime(input)).toBe(expected);
	});
});

describe('statusAccentVar', () => {
	it.each<[string | null | undefined, string]>([
		['created', 'var(--color-status-scanning)'],
		['ripping', 'var(--color-status-ripping)'],
		['identified', 'var(--color-status-ripping)'],
		['transcoding', 'var(--color-status-transcoding)'],
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

describe('etaTime', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});
	afterEach(() => vi.useRealTimers());

	it('returns null when start time missing', () => {
		expect(etaTime(null, 50)).toBeNull();
	});

	it('returns null when progress is null/undefined', () => {
		expect(etaTime('2025-06-15T11:59:00Z', null)).toBeNull();
		expect(etaTime('2025-06-15T11:59:00Z', undefined)).toBeNull();
	});

	it('returns null when progress is 0 or negative', () => {
		expect(etaTime('2025-06-15T11:59:00Z', 0)).toBeNull();
		expect(etaTime('2025-06-15T11:59:00Z', -5)).toBeNull();
	});

	it('returns null when progress is 100 or over', () => {
		expect(etaTime('2025-06-15T11:59:00Z', 100)).toBeNull();
		expect(etaTime('2025-06-15T11:59:00Z', 105)).toBeNull();
	});

	it('returns null below the 30s elapsed threshold', () => {
		// 25s elapsed at 10% — formula would give 3m45s, but we suppress
		// to avoid wild estimates from MakeMKV warm-up jitter.
		expect(etaTime('2025-06-15T11:59:35Z', 10)).toBeNull();
	});

	it('formats seconds-only ETA', () => {
		// 60s elapsed at 80% → 15s remaining
		expect(etaTime('2025-06-15T11:59:00Z', 80)).toBe('15s');
	});

	it('formats minutes ETA', () => {
		// 2m elapsed at 25% → 6m remaining
		expect(etaTime('2025-06-15T11:58:00Z', 25)).toBe('6m 0s');
	});

	it('formats hours ETA', () => {
		// 30m elapsed at 10% → 4h 30m remaining
		expect(etaTime('2025-06-15T11:30:00Z', 10)).toBe('4h 30m');
	});

	it('caps absurdly long estimates at 24h+', () => {
		// 5m elapsed at 0.1% → ~83h. Cap.
		expect(etaTime('2025-06-15T11:55:00Z', 0.1)).toBe('24h+');
	});
});

describe('formatDateTime', () => {
	it('returns N/A for null', () => {
		expect(formatDateTime(null)).toBe('N/A');
	});

	it('returns a locale string for a valid date', () => {
		const result = formatDateTime('2025-06-15T12:00:00Z');
		expect(result).toBeTypeOf('string');
		expect(result).not.toBe('N/A');
		expect(result).toContain('2025');
	});
});
