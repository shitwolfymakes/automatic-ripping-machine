// Pure helpers for the LogView log terminal.
import type { LogEntry } from '$lib/api/logs';
import { logService, serviceLabel, type LogService } from '$lib/logs/service';
import { plural } from '$lib/utils/plural';

/** A level filter: one level, or every line. */
export type LogLevelFilter = 'all' | 'error' | 'warning' | 'info' | 'debug';
/** A service filter: one service group, or every line. */
export type LogServiceFilter = 'all' | LogService;
/** What LogView's toolbar filters by. An empty query matches every line. */
export interface LogFilter {
	service: LogServiceFilter;
	level: LogLevelFilter;
	query: string;
	matchCase: boolean;
}

function levelOf(entry: LogEntry): string {
	return (entry.level ?? '').toLowerCase();
}

function matchesSearch(entry: LogEntry, query: string, matchCase: boolean): boolean {
	if (!query) return true;
	const hay = `${entry.event ?? ''} ${entry.logger ?? ''}`;
	return matchCase ? hay.includes(query) : hay.toLowerCase().includes(query.toLowerCase());
}

/** The entries that pass the service, level and text filters, in order. */
export function filterEntries(entries: LogEntry[], filter: LogFilter): LogEntry[] {
	return entries.filter((e) => {
		if (filter.service !== 'all' && logService(e.service) !== filter.service) return false;
		if (filter.level !== 'all' && levelOf(e) !== filter.level) return false;
		if (!matchesSearch(e, filter.query, filter.matchCase)) return false;
		return true;
	});
}

/** "N lines", or "Showing X of Y lines" once a filter hides some. */
export function countLabel(shown: number, total: number): string {
	return shown !== total ? `Showing ${shown} of ${total} lines` : `${total} lines`;
}

/** "1 match", or "N matches". */
export function matchLabel(count: number): string {
	return `${count} ${plural(count, 'match', 'matches')}`;
}

/** "Following", "Paused", or "Paused · N new line(s)". */
export function followLabel(following: boolean, waiting: number): string {
	return following ? 'Following' : waiting === 0 ? 'Paused' : `Paused · ${waiting} new ${plural(waiting, 'line')}`;
}

/** What a log line's `data-tone` can be: a tone, or null for none. */
export type LogTone = 'warning' | 'danger' | 'debug' | null;

// The well is a fixed dark surface in both modes (see the --color-terminal-*
// tokens), so the chips take fixed-dark recipes mixed towards the ink rather
// than the mode-flipping tone tokens. Backend tints from primary, ripper
// from accent-1 (amber) and transcode from accent-3 (violet).
const CHIP_COLOURS: Record<LogService, { background: string; text: string }> = {
	backend: {
		background: 'color-mix(in srgb, var(--color-primary) 26%, transparent)',
		text: 'color-mix(in srgb, var(--color-primary) 45%, var(--color-terminal-ink))'
	},
	ripper: {
		background: 'color-mix(in srgb, var(--color-accent-1) 28%, transparent)',
		text: 'color-mix(in srgb, var(--color-accent-1) 60%, var(--color-terminal-ink))'
	},
	transcode: {
		background: 'color-mix(in srgb, var(--color-accent-3) 22%, transparent)',
		text: 'color-mix(in srgb, var(--color-accent-3) 45%, var(--color-terminal-ink))'
	},
	other: {
		background: 'color-mix(in srgb, var(--color-terminal-ink) 10%, transparent)',
		text: 'color-mix(in srgb, var(--color-terminal-ink) 70%, transparent)'
	}
};

/** The service chip's background colour. */
export function chipBackground(service: LogService): string {
	return CHIP_COLOURS[service].background;
}

/** The chip's text colour, the partner of `chipBackground`. */
export function chipText(service: LogService): string {
	return CHIP_COLOURS[service].text;
}

// A Map, not an object literal: a plain object would also answer inherited
// keys such as 'constructor'.
const LEVEL_TONES = new Map<string, LogTone>([
	['warning', 'warning'],
	['error', 'danger'],
	['critical', 'danger'],
	['debug', 'debug']
]);

/**
 * A line's `data-tone` from its level, matched case-insensitively; null for
 * none.
 */
export function levelTone(level: string): LogTone {
	return LEVEL_TONES.get((level ?? '').toLowerCase()) ?? null;
}

/**
 * The entry's local time with no AM or PM, or '' when it has none or it does
 * not parse.
 */
export function entryTimeLabel(entry: LogEntry): string {
	if (!entry.timestamp) return '';
	const d = new Date(entry.timestamp);
	if (Number.isNaN(d.getTime())) return '';
	return d.toLocaleTimeString([], { hour12: false });
}

/**
 * The plain text Copy writes: one "<time> [<service>] <event>" line per
 * entry.
 */
export function formatCopyText(entries: LogEntry[]): string {
	return entries
		.map((e) => `${entryTimeLabel(e)} [${serviceLabel(logService(e.service))}] ${e.event ?? ''}`)
		.join('\n');
}
