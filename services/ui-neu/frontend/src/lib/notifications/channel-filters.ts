// Which channels each filter pill on Settings > Notifications shows, and
// the counts the pills and the stat strip read.
import type { Channel } from '$lib/types/notifications';

export type ChannelFilter = 'all' | 'enabled' | 'paused' | 'issues';

// What each filter shows.
const FILTERS: Record<ChannelFilter, (c: Channel) => boolean> = {
	all: () => true,
	enabled: (c) => c.enabled,
	paused: (c) => !c.enabled,
	issues: (c) => !!c.last_error
};

/** The channel shows under the filter. */
export function matchesFilter(c: Channel, filter: ChannelFilter): boolean {
	return FILTERS[filter](c);
}

/** How many channels each filter pill shows. */
export function filterCounts(channels: Channel[]): Record<ChannelFilter, number> {
	const count = (filter: ChannelFilter) => channels.filter((c) => matchesFilter(c, filter)).length;
	return { all: count('all'), enabled: count('enabled'), paused: count('paused'), issues: count('issues') };
}

/**
 * The stat strip's numbers: the channels, those with an issue, and the
 * distinct events they subscribe to.
 */
export function summaryCounts(channels: Channel[]): { total: number; issues: number; subscribedEvents: number } {
	return {
		total: channels.length,
		issues: channels.filter((c) => matchesFilter(c, 'issues')).length,
		subscribedEvents: new Set(channels.flatMap((c) => c.subscribed_events)).size
	};
}
