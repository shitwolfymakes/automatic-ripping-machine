import { describe, it, expect } from 'vitest';
import { filterCounts, matchesFilter, summaryCounts, type ChannelFilter } from '../channel-filters';
import { webhookChannel } from '../../components/notifications/__tests__/apprise-fixtures';

const enabled = webhookChannel({ id: 1, enabled: true, subscribed_events: ['job.started', 'rip.completed'] });
const paused = webhookChannel({ id: 2, enabled: false, subscribed_events: ['rip.completed'] });
const failing = webhookChannel({ id: 3, enabled: true, last_error: 'boom', subscribed_events: ['job.failed'] });

describe('matchesFilter', () => {
	const cases: [ChannelFilter, boolean, boolean, boolean][] = [
		['all', true, true, true],
		['enabled', true, false, true],
		['paused', false, true, false],
		['issues', false, false, true]
	];
	it.each(cases)('under %s: enabled, paused and errored channels', (filter, e, p, f) => {
		expect(matchesFilter(enabled, filter)).toBe(e);
		expect(matchesFilter(paused, filter)).toBe(p);
		expect(matchesFilter(failing, filter)).toBe(f);
	});
});

describe('filterCounts', () => {
	it('counts each pill over a mixed list', () => {
		expect(filterCounts([enabled, paused, failing])).toEqual({ all: 3, enabled: 2, paused: 1, issues: 1 });
	});

	it('is all zeros for an empty list', () => {
		expect(filterCounts([])).toEqual({ all: 0, enabled: 0, paused: 0, issues: 0 });
	});
});

describe('summaryCounts', () => {
	it('counts a shared event once', () => {
		expect(summaryCounts([enabled, paused, failing])).toEqual({ total: 3, issues: 1, subscribedEvents: 3 });
	});

	it('is all zeros for an empty list', () => {
		expect(summaryCounts([])).toEqual({ total: 0, issues: 0, subscribedEvents: 0 });
	});
});
