// Pure helpers for the LogView log terminal.
import type { LogEntry } from '$lib/api/logs';
import { entryGroup, serviceLabel, type LogService } from '$lib/utils/log-service';

/** A level filter: one level and every higher one, or every line. */
export type LogLevelFilter = 'all' | 'critical' | 'error' | 'warning' | 'info' | 'debug';
/** A service filter: one service group, or every line. */
export type LogServiceFilter = 'all' | LogService;
/** What LogView's toolbar filters by. An empty query matches every line. */
export interface LogFilter {
	service: LogServiceFilter;
	level: LogLevelFilter;
	query: string;
	matchCase: boolean;
}

// A Map, not an object literal, so inherited keys such as 'constructor' rank
// as unknown.
const LEVEL_RANK = new Map<string, number>([
	['debug', 0],
	['info', 1],
	['warning', 2],
	['error', 3],
	['critical', 4]
]);
const DEFAULT_RANK = 1;

// A level the filter does not know (or a missing one) ranks as info.
function levelRank(level: string | null | undefined): number {
	return LEVEL_RANK.get((level ?? '').toLowerCase()) ?? DEFAULT_RANK;
}

function passesLevel(entry: LogEntry, level: LogLevelFilter): boolean {
	return level === 'all' || levelRank(entry.level) >= levelRank(level);
}

function matchesSearch(entry: LogEntry, query: string, matchCase: boolean): boolean {
	if (!query) return true;
	const hay = [entry.msg, entry.event, entry.logger].filter(Boolean).join(' ');
	return matchCase ? hay.includes(query) : hay.toLowerCase().includes(query.toLowerCase());
}

/** The entries that pass the service, level and text filters, in order. */
export function filterEntries(entries: LogEntry[], filter: LogFilter): LogEntry[] {
	return entries.filter((e) => {
		if (filter.service !== 'all' && entryGroup(e) !== filter.service) return false;
		if (!passesLevel(e, filter.level)) return false;
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
	return `${count} ${count === 1 ? 'match' : 'matches'}`;
}

/** "Following", "Paused", or "Paused · N new line(s)". */
export function followLabel(following: boolean, waiting: number): string {
	return following
		? 'Following'
		: waiting === 0
			? 'Paused'
			: `Paused · ${waiting} new ${waiting === 1 ? 'line' : 'lines'}`;
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
	if (!entry.ts) return '';
	const d = new Date(entry.ts);
	if (Number.isNaN(d.getTime())) return '';
	return d.toLocaleTimeString([], { hour12: false });
}

/**
 * The plain text Copy writes: one "<time> [<service>] <msg>" line per
 * entry.
 */
export function formatCopyText(entries: LogEntry[]): string {
	return entries.map((e) => `${entryTimeLabel(e)} [${serviceLabel(entryGroup(e))}] ${e.msg}`).join('\n');
}
