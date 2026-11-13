import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
	formatBytes,
	statusColor,
	statusLabel,
	statusAccentVar,
	timeAgo,
	elapsedTime,
	etaTime,
	formatRemaining,
	formatEta,
	formatRipStage,
	formatTransfer,
	formatDateTime,
	formatShortDateTime,
	calendarTimeAgo,
	formatTrackLength,
	formatTrackDuration,
	formatMinSec,
	formatElapsed
} from '../format';

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

describe('formatRemaining', () => {
	it('formats a reported ETA like etaTime does', () => {
		expect(formatRemaining(42)).toBe('42s');
		expect(formatRemaining(1800)).toBe('30m 0s');
		expect(formatRemaining(5400)).toBe('1h 30m');
	});

	it('clamps negatives to 0s and caps at 24h+', () => {
		expect(formatRemaining(-5)).toBe('0s');
		expect(formatRemaining(24 * 3600)).toBe('24h+');
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

describe('formatShortDateTime', () => {
	const now = new Date(2026, 9, 16, 12, 0);
	it('formats month, day and time', () => {
		const out = formatShortDateTime(new Date(2026, 9, 16, 8, 18).toISOString(), now);
		expect(out).toMatch(/Oct 16/);
		expect(out).toMatch(/8:18/);
		expect(out).not.toMatch(/2026/);
	});
	it('adds the year when it is not the current year', () => {
		expect(formatShortDateTime(new Date(2025, 11, 30, 9, 5).toISOString(), now)).toMatch(/2025/);
	});
	it('is empty for an unparseable date', () => {
		expect(formatShortDateTime('not a date', now)).toBe('');
	});
});

describe('calendarTimeAgo', () => {
	// Fixed local "now": Oct 16 2026, 12:00
	const now = new Date(2026, 9, 16, 12, 0, 0);
	const at = (...args: [number, number, number, number, number]) => new Date(...args).toISOString();

	it('says just now under a minute', () => {
		expect(calendarTimeAgo(new Date(now.getTime() - 30_000).toISOString(), now)).toBe('Just now');
	});
	it('counts minutes, then hours the same day', () => {
		expect(calendarTimeAgo(at(2026, 9, 16, 11, 18), now)).toBe('42 min ago');
		expect(calendarTimeAgo(at(2026, 9, 16, 9, 0), now)).toBe('3h ago');
		expect(calendarTimeAgo(at(2026, 9, 16, 0, 5), now)).toBe('11h ago');
	});
	it('says yesterday for the previous calendar day', () => {
		expect(calendarTimeAgo(at(2026, 9, 15, 23, 0), now)).toBe('Yesterday');
		expect(calendarTimeAgo(at(2026, 9, 15, 0, 1), now)).toBe('Yesterday');
	});
	it('counts days up to six', () => {
		expect(calendarTimeAgo(at(2026, 9, 14, 20, 0), now)).toBe('2 days ago');
		expect(calendarTimeAgo(at(2026, 9, 10, 1, 0), now)).toBe('6 days ago');
	});
	it('is null for an unparseable date', () => {
		expect(calendarTimeAgo('garbage', now)).toBeNull();
	});
	it('is null past six days, so only the absolute date shows', () => {
		expect(calendarTimeAgo(at(2026, 9, 9, 23, 0), now)).toBeNull();
	});
	it('counts minutes across midnight before calendar days', () => {
		const justAfterMidnight = new Date(2026, 9, 16, 0, 10);
		expect(calendarTimeAgo(at(2026, 9, 15, 23, 50), justAfterMidnight)).toBe('20 min ago');
	});
});

describe('formatEta', () => {
	it('returns "< 1m" for sub-minute', () => {
		expect(formatEta(45)).toBe('< 1m');
	});
	it('returns minutes+seconds for under 5 minutes', () => {
		expect(formatEta(150)).toBe('2m 30s');
	});
	it('returns whole minutes for 5+ minute ETAs', () => {
		expect(formatEta(720)).toBe('12m');
	});
	it('returns hours+minutes when over an hour', () => {
		expect(formatEta(4_350)).toBe('1h 12m');
	});
});

describe('formatRipStage', () => {
	it('words the scratch-to-media copy stage plainly', () => {
		expect(formatRipStage('scratch-to-media')).toBe('Copying to shared storage');
	});
	it('words the work-to-completed move stage plainly', () => {
		expect(formatRipStage('work-to-completed')).toBe('Moving to completed');
	});
	it('shows any other stage as the ripper named it', () => {
		expect(formatRipStage('ripping')).toBe('ripping');
	});
});

describe('formatTransfer', () => {
	it('has no transfer line for a MakeMKV rip', () => {
		expect(formatTransfer(null)).toBeNull();
		expect(
			formatTransfer({
				bytes_done: null,
				bytes_total: null,
				rate_bps: null
			})
		).toBeNull();
	});

	it('shows only the bytes done, with no rate, when a copy reports no total or rate', () => {
		expect(
			formatTransfer({
				bytes_done: 3 * 1024 ** 3,
				bytes_total: null,
				rate_bps: 0
			})
		).toBe('3 GB');
	});
});

describe('formatTrackLength', () => {
	it.each([
		[null, ''],
		[undefined, ''],
		[0, '0:00'],
		[45, '0:45'],
		[65, '1:05'],
		[120, '2:00'],
		[3725, '62:05']
	])('formatTrackLength(%s) = %j', (input, expected) => {
		expect(formatTrackLength(input)).toBe(expected);
	});
});

describe('formatTrackDuration', () => {
	it.each([
		[null, '--'],
		[undefined, '--'],
		[0, '--'],
		[59, '0m 59s'],
		[123, '2m 3s'],
		[3599, '59m 59s'],
		[3600, '1h 0m 0s'],
		[3723, '1h 2m 3s'],
		[90000, '25h 0m 0s']
	])('formatTrackDuration(%s) = %j', (input, expected) => {
		expect(formatTrackDuration(input)).toBe(expected);
	});
});

describe('formatElapsed', () => {
	const START = '2025-01-01T00:00:00Z';

	afterEach(() => {
		vi.useRealTimers();
	});

	it.each<[string | null, string]>([
		[null, 'no start'],
		['not-a-date', 'unparsable start']
	])('returns null for %j (%s)', (start) => {
		expect(formatElapsed(start, START)).toBeNull();
	});

	it('returns null for an unparsable end', () => {
		expect(formatElapsed(START, 'not-a-date')).toBeNull();
	});

	it('formats hours, minutes and seconds', () => {
		expect(formatElapsed(START, '2025-01-01T01:02:03Z')).toBe('1h 2m 3s');
	});

	it('omits hours when under an hour', () => {
		expect(formatElapsed(START, '2025-01-01T00:02:03Z')).toBe('2m 3s');
	});

	it('shows only seconds when under a minute', () => {
		expect(formatElapsed(START, '2025-01-01T00:00:03Z')).toBe('3s');
	});

	it('clamps an end before the start to 0s', () => {
		expect(formatElapsed('2025-01-01T00:00:10Z', START)).toBe('0s');
	});

	it('measures to now when there is no end', () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-01-01T00:01:05Z'));
		expect(formatElapsed(START)).toBe('1m 5s');
	});
});

describe('formatMinSec', () => {
	it('returns a dash for null and undefined in both units', () => {
		expect(formatMinSec(null, 1000)).toBe('-');
		expect(formatMinSec(undefined, 1000)).toBe('-');
		expect(formatMinSec(null, 1)).toBe('-');
		expect(formatMinSec(undefined, 1)).toBe('-');
	});

	it('formats milliseconds rounded to the nearest second', () => {
		expect(formatMinSec(0, 1000)).toBe('0:00');
		expect(formatMinSec(59_499, 1000)).toBe('0:59');
		expect(formatMinSec(59_500, 1000)).toBe('1:00');
		expect(formatMinSec(213_000, 1000)).toBe('3:33');
		expect(formatMinSec(3_600_000, 1000)).toBe('60:00');
	});

	it('formats seconds rounded to the nearest second', () => {
		expect(formatMinSec(0, 1)).toBe('0:00');
		expect(formatMinSec(9.4, 1)).toBe('0:09');
		expect(formatMinSec(9.5, 1)).toBe('0:10');
		expect(formatMinSec(245, 1)).toBe('4:05');
	});
});
