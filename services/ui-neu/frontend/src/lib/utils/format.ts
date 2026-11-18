export function timeAgo(dateString: string | null | undefined): string {
	if (!dateString) return 'N/A';
	const date = new Date(dateString);
	const now = new Date();
	const seconds = Math.max(0, Math.floor((now.getTime() - date.getTime()) / 1000));

	if (seconds < 60) return `${seconds}s ago`;
	const minutes = Math.floor(seconds / 60);
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	const days = Math.floor(hours / 24);
	return `${days}d ago`;
}

/**
 * The time from startISO to endISO (or to now when endISO is missing) as
 * `1h 2m 3s`, `2m 3s` or `3s`; null when the start is missing or either
 * stamp is unparsable. An end before the start gives `0s`.
 */
export function formatElapsed(startISO: string | null, endISO?: string | null): string | null {
	if (!startISO) return null;
	const start = new Date(startISO).getTime();
	if (isNaN(start)) return null;
	const end = endISO ? new Date(endISO).getTime() : Date.now();
	if (isNaN(end)) return null;
	const diffSec = Math.max(0, Math.floor((end - start) / 1000));
	const h = Math.floor(diffSec / 3600);
	const m = Math.floor((diffSec % 3600) / 60);
	const sec = diffSec % 60;
	if (h > 0) return `${h}h ${m}m ${sec}s`;
	if (m > 0) return `${m}m ${sec}s`;
	return `${sec}s`;
}

const MINUTE = 60_000;

function startOfDay(d: Date): number {
	return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/**
 * Relative time in local calendar days, for a list that pairs it with an
 * absolute date (the Logs list's "Last modified"): `Just now`, `42 min ago`,
 * `3h ago` (same day), `Yesterday`, `2 days ago` up to six days. Older than
 * that it returns null and the row shows only the absolute date.
 */
export function calendarTimeAgo(iso: string, now: Date = new Date()): string | null {
	const then = new Date(iso);
	if (Number.isNaN(then.getTime())) return null;
	const ms = Math.max(0, now.getTime() - then.getTime());
	if (ms < MINUTE) return 'Just now';
	if (ms < 60 * MINUTE) return `${Math.floor(ms / MINUTE)} min ago`;
	// Math.round absorbs a DST shift (a 23h or 25h day)
	const days = Math.round((startOfDay(now) - startOfDay(then)) / (24 * 60 * MINUTE));
	if (days <= 0) return `${Math.floor(ms / (60 * MINUTE))}h ago`;
	if (days === 1) return 'Yesterday';
	if (days <= 6) return `${days} days ago`;
	return null;
}

/**
 * `Oct 16, 8:18 AM` in the viewer's locale and time zone, with the year when
 * it is not the current one; empty for an unparseable date.
 */
export function formatShortDateTime(iso: string, now: Date = new Date()): string {
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return '';
	return d.toLocaleString(undefined, {
		month: 'short',
		day: 'numeric',
		...(d.getFullYear() !== now.getFullYear() ? { year: 'numeric' } : {}),
		hour: 'numeric',
		minute: '2-digit'
	});
}

export function formatBytes(bytes: number): string {
	if (bytes === 0) return '0 B';
	const k = 1024;
	const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatDateTime(dateString: string | null | undefined): string {
	if (!dateString) return 'N/A';
	return new Date(dateString).toLocaleString();
}

export function elapsedTime(startTime: string | null | undefined): string {
	if (!startTime) return 'N/A';
	const start = new Date(startTime);
	const now = new Date();
	const totalSeconds = Math.max(0, Math.floor((now.getTime() - start.getTime()) / 1000));

	const hours = Math.floor(totalSeconds / 3600);
	const minutes = Math.floor((totalSeconds % 3600) / 60);
	const seconds = totalSeconds % 60;

	if (hours > 0) return `${hours}h ${minutes}m`;
	if (minutes > 0) return `${minutes}m ${seconds}s`;
	return `${seconds}s`;
}

/**
 * Format a remaining-time estimate in seconds the way etaTime does, for an
 * ETA that arrives ready-made (the transcoder reports HandBrake's own).
 * Capped at 24h+.
 */
export function formatRemaining(remainingSec: number): string {
	if (remainingSec >= 24 * 3600) return '24h+';
	const sec = Math.max(0, remainingSec);
	const h = Math.floor(sec / 3600);
	const m = Math.floor((sec % 3600) / 60);
	const s = Math.floor(sec % 60);
	if (h > 0) return `${h}h ${m}m`;
	if (m > 0) return `${m}m ${s}s`;
	return `${s}s`;
}

/** The byte-copy fields of a live rip tick that formatTransfer reads. */
interface ByteTransfer {
	bytes_done: number | null;
	bytes_total: number | null;
	rate_bps: number | null;
}

/** "12.3 GB of 20.9 GB · 45.1 MB/s" for a byte copy, or null when none was reported. */
export function formatTransfer(live: ByteTransfer | null | undefined): string | null {
	if (!live || live.bytes_done == null) return null;
	const parts = [
		live.bytes_total != null
			? `${formatBytes(live.bytes_done)} of ${formatBytes(live.bytes_total)}`
			: formatBytes(live.bytes_done)
	];
	if (live.rate_bps != null && live.rate_bps > 0) parts.push(`${formatBytes(live.rate_bps)}/s`);
	return parts.join(' · ');
}

export function formatEta(seconds: number): string {
	if (seconds < 60) return '< 1m';
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	const s = seconds % 60;
	if (h > 0) return `${h}h ${m}m`;
	if (m >= 5) return `${m}m`;
	return `${m}m ${s}s`;
}

// Formats a track length in seconds as m:ss ('' when missing).
export function formatTrackLength(seconds: number | null | undefined): string {
	if (seconds == null) return '';
	const m = Math.floor(seconds / 60);
	const s = seconds % 60;
	return `${m}:${String(s).padStart(2, '0')}`;
}

// Formats a track length in seconds as "1h 2m 3s", or "2m 3s" under an hour
// ('--' when missing or 0).
export function formatTrackDuration(secs: number | null | undefined): string {
	if (!secs) return '--';
	const h = Math.floor(secs / 3600);
	const m = Math.floor((secs % 3600) / 60);
	const s = secs % 60;
	if (h > 0) return `${h}h ${m}m ${s}s`;
	return `${m}m ${s}s`;
}

/**
 * A length as m:ss, rounded to the nearest second, and `-` when missing.
 * `unitsPerSecond` is 1000 for milliseconds and 1 for seconds.
 */
export function formatMinSec(value: number | null | undefined, unitsPerSecond: number): string {
	if (value == null) return '-';
	const total = Math.round(value / unitsPerSecond);
	return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}
