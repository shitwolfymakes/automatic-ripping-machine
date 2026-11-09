// Pure helpers for the LogView log terminal.
import type { LogEntry } from '$lib/api/logs';
import { logService, type LogService } from '$lib/utils/log-service';

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
