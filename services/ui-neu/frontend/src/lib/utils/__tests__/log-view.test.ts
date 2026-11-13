import { describe, it, expect } from 'vitest';
import type { LogEntry } from '$lib/api/logs';
import { logService, serviceLabel } from '$lib/logs/service';
import {
	chipBackground,
	chipText,
	countLabel,
	entryTimeLabel,
	filterEntries,
	followLabel,
	formatCopyText,
	levelTone,
	matchLabel,
	type LogFilter
} from '../../logs/view';

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

describe('countLabel', () => {
	it('shows just the total when nothing is hidden', () => {
		expect(countLabel(5, 5)).toBe('5 lines');
	});

	it('shows just the total for 0 of 0', () => {
		expect(countLabel(0, 0)).toBe('0 lines');
	});

	it('shows X of Y when a filter hides some lines', () => {
		expect(countLabel(2, 7)).toBe('Showing 2 of 7 lines');
	});
});

describe('matchLabel', () => {
	it('uses the plural for 0', () => {
		expect(matchLabel(0)).toBe('0 matches');
	});

	it('uses the singular for 1', () => {
		expect(matchLabel(1)).toBe('1 match');
	});

	it('uses the plural for 2', () => {
		expect(matchLabel(2)).toBe('2 matches');
	});
});

describe('followLabel', () => {
	it('says Following whatever the waiting count', () => {
		expect(followLabel(true, 0)).toBe('Following');
		expect(followLabel(true, 3)).toBe('Following');
	});

	it('says Paused with nothing waiting', () => {
		expect(followLabel(false, 0)).toBe('Paused');
	});

	it('says Paused with 1 new line', () => {
		expect(followLabel(false, 1)).toBe('Paused · 1 new line');
	});

	it('says Paused with N new lines', () => {
		expect(followLabel(false, 2)).toBe('Paused · 2 new lines');
	});
});

describe('chipBackground', () => {
	it('tints backend from primary', () => {
		expect(chipBackground('backend')).toBe('color-mix(in srgb, var(--color-primary) 26%, transparent)');
	});

	it('tints ripper from accent-1', () => {
		expect(chipBackground('ripper')).toBe('color-mix(in srgb, var(--color-accent-1) 28%, transparent)');
	});

	it('tints transcode from accent-3', () => {
		expect(chipBackground('transcode')).toBe('color-mix(in srgb, var(--color-accent-3) 22%, transparent)');
	});

	it('tints other from the terminal ink', () => {
		expect(chipBackground('other')).toBe('color-mix(in srgb, var(--color-terminal-ink) 10%, transparent)');
	});
});

describe('chipText', () => {
	it('mixes backend primary towards the ink', () => {
		expect(chipText('backend')).toBe('color-mix(in srgb, var(--color-primary) 45%, var(--color-terminal-ink))');
	});

	it('mixes ripper accent-1 towards the ink', () => {
		expect(chipText('ripper')).toBe('color-mix(in srgb, var(--color-accent-1) 60%, var(--color-terminal-ink))');
	});

	it('mixes transcode accent-3 towards the ink', () => {
		expect(chipText('transcode')).toBe('color-mix(in srgb, var(--color-accent-3) 45%, var(--color-terminal-ink))');
	});

	it('fades other from the terminal ink', () => {
		expect(chipText('other')).toBe('color-mix(in srgb, var(--color-terminal-ink) 70%, transparent)');
	});
});

describe('levelTone', () => {
	it('maps warning to warning', () => {
		expect(levelTone('warning')).toBe('warning');
	});

	it('maps error and critical to danger', () => {
		expect(levelTone('error')).toBe('danger');
		expect(levelTone('critical')).toBe('danger');
	});

	it('maps debug to debug', () => {
		expect(levelTone('debug')).toBe('debug');
	});

	it('gives info no tone', () => {
		expect(levelTone('info')).toBeNull();
	});

	it('matches case-insensitively', () => {
		expect(levelTone('Error')).toBe('danger');
		expect(levelTone('DEBUG')).toBe('debug');
	});

	it('gives a null level no tone', () => {
		expect(levelTone(null as never)).toBeNull();
	});

	it('gives inherited object keys no tone', () => {
		expect(levelTone('constructor')).toBeNull();
		expect(levelTone('toString')).toBeNull();
		expect(levelTone('__proto__')).toBeNull();
	});
});

describe('entryTimeLabel', () => {
	it('formats a valid timestamp as local time without AM or PM', () => {
		const ts = '2026-01-02T03:04:05Z';
		expect(entryTimeLabel(entry({ timestamp: ts }))).toBe(new Date(ts).toLocaleTimeString([], { hour12: false }));
	});

	it('is empty when the timestamp is missing', () => {
		expect(entryTimeLabel(entry({ timestamp: undefined }))).toBe('');
	});

	it('is empty when the timestamp is null', () => {
		expect(entryTimeLabel(entry({ timestamp: null as never }))).toBe('');
	});

	it('is empty when the timestamp does not parse', () => {
		expect(entryTimeLabel(entry({ timestamp: 'not a date' }))).toBe('');
	});
});

describe('formatCopyText', () => {
	it('writes one time, service and event line per entry, joined by newlines', () => {
		const ts = '2026-01-02T03:04:05Z';
		const time = new Date(ts).toLocaleTimeString([], { hour12: false });
		const text = formatCopyText([
			entry({ event: 'b', service: 'arm-backend', timestamp: ts }),
			entry({ event: 'r', service: 'arm-ripper-SER1', timestamp: ts }),
			entry({ event: 't', service: 'arm-transcode-task_1', timestamp: ts }),
			entry({ event: 'o', service: 'mystery', timestamp: ts })
		]);
		const lines = text.split('\n');
		expect(lines).toHaveLength(4);
		expect(lines[0]).toBe(`${time} [${serviceLabel(logService('arm-backend'))}] b`);
		expect(lines[1]).toBe(`${time} [${serviceLabel(logService('arm-ripper-SER1'))}] r`);
		expect(lines[2]).toBe(`${time} [${serviceLabel(logService('arm-transcode-task_1'))}] t`);
		expect(lines[3]).toBe(`${time} [${serviceLabel(logService('mystery'))}] o`);
	});

	it('leaves the event and the time blank when an entry has neither', () => {
		const text = formatCopyText([entry({ event: null as never, timestamp: null as never })]);
		expect(text).toBe(` [${serviceLabel(logService('arm-backend'))}] `);
	});

	it('is empty for an empty list', () => {
		expect(formatCopyText([])).toBe('');
	});
});
