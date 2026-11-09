import { describe, it, expect } from 'vitest';
import type { LogEntry } from '$lib/api/logs';
import { filterEntries, type LogFilter } from '../log-view';

function entry(over: Partial<LogEntry> = {}): LogEntry {
	return { level: 'info', logger: 'log', event: 'evt', service: 'arm-backend', ...over };
}

function filter(over: Partial<LogFilter> = {}): LogFilter {
	return { service: 'all', level: 'all', query: '', matchCase: false, ...over };
}

describe('filterEntries service filter', () => {
	const entries = [
		entry({ event: 'b', service: 'arm-backend' }),
		entry({ event: 'r', service: 'arm-ripper-SER1' }),
		entry({ event: 't', service: 'arm-transcode-task_1' }),
		entry({ event: 'o', service: 'mystery' })
	];
	const events = (f: Partial<LogFilter>) => filterEntries(entries, filter(f)).map((e) => e.event);

	it('keeps only backend lines under backend', () => {
		expect(events({ service: 'backend' })).toEqual(['b']);
	});

	it('keeps only ripper lines under ripper', () => {
		expect(events({ service: 'ripper' })).toEqual(['r']);
	});

	it('keeps only transcode lines under transcode', () => {
		expect(events({ service: 'transcode' })).toEqual(['t']);
	});

	it('keeps a service outside the three groups only under all', () => {
		expect(events({ service: 'all' })).toEqual(['b', 'r', 't', 'o']);
		expect(events({ service: 'backend' })).not.toContain('o');
		expect(events({ service: 'ripper' })).not.toContain('o');
		expect(events({ service: 'transcode' })).not.toContain('o');
	});
});

describe('filterEntries level filter', () => {
	const entries = ['error', 'warning', 'info', 'debug'].map((level) => entry({ level, event: level }));
	const events = (level: LogFilter['level']) => filterEntries(entries, filter({ level })).map((e) => e.event);

	it.each(['error', 'warning', 'info', 'debug'] as const)('keeps only %s lines', (level) => {
		expect(events(level)).toEqual([level]);
	});

	it('matches the level case-insensitively', () => {
		const out = filterEntries([entry({ level: 'WARNING' })], filter({ level: 'warning' }));
		expect(out).toHaveLength(1);
	});

	it('keeps a null level only under all', () => {
		const nullLevel = [entry({ level: null as never })];
		expect(filterEntries(nullLevel, filter({ level: 'all' }))).toHaveLength(1);
		expect(filterEntries(nullLevel, filter({ level: 'info' }))).toHaveLength(0);
	});
});

describe('filterEntries text filter', () => {
	it('matches the query against the event case-insensitively by default', () => {
		const out = filterEntries([entry({ event: 'Disc Ejected' })], filter({ query: 'disc ejected' }));
		expect(out).toHaveLength(1);
	});

	it('matches the query against the logger', () => {
		const out = filterEntries([entry({ logger: 'arm.Ripper' })], filter({ query: 'ARM.ripper' }));
		expect(out).toHaveLength(1);
	});

	it('matches across the event and logger joined by a space', () => {
		const out = filterEntries([entry({ event: 'ev', logger: 'lg' })], filter({ query: 'ev lg' }));
		expect(out).toHaveLength(1);
	});

	it('is exact under matchCase', () => {
		const entries = [entry({ event: 'Disc' })];
		expect(filterEntries(entries, filter({ query: 'Disc', matchCase: true }))).toHaveLength(1);
		expect(filterEntries(entries, filter({ query: 'disc', matchCase: true }))).toHaveLength(0);
	});

	it('reads a null event and logger as empty', () => {
		const nulls = entry({ event: null as never, logger: null as never });
		expect(filterEntries([nulls], filter({ query: 'x' }))).toHaveLength(0);
		expect(filterEntries([nulls], filter({ query: ' ' }))).toHaveLength(1);
	});

	it('keeps every line for an empty query', () => {
		const entries = [entry({ event: 'a' }), entry({ event: 'b' })];
		expect(filterEntries(entries, filter({ query: '', matchCase: true }))).toHaveLength(2);
	});
});

describe('filterEntries combined filters', () => {
	it('requires the service, level and text filters together', () => {
		const entries = [
			entry({ event: 'hit', level: 'error', service: 'arm-ripper-S' }),
			entry({ event: 'hit', level: 'error', service: 'arm-backend' }),
			entry({ event: 'hit', level: 'info', service: 'arm-ripper-S' }),
			entry({ event: 'miss', level: 'error', service: 'arm-ripper-S' })
		];
		const out = filterEntries(entries, filter({ service: 'ripper', level: 'error', query: 'hit' }));
		expect(out).toEqual([entries[0]]);
	});

	it('keeps the order of the entries', () => {
		const entries = [entry({ event: 'c' }), entry({ event: 'a' }), entry({ event: 'b' })];
		expect(filterEntries(entries, filter()).map((e) => e.event)).toEqual(['c', 'a', 'b']);
	});
});
