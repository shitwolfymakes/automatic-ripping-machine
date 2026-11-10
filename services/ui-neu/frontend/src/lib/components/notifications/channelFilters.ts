// Which channels each filter pill on Settings > Notifications shows, and
// the counts the pills and the stat strip read.
import type { Channel } from '$lib/types/notifications';

export type ChannelFilter = 'all' | 'enabled' | 'paused' | 'issues';

/** The channel shows under the filter. */
export function matchesFilter(c: Channel, filter: ChannelFilter): boolean {
	return filter === 'all' ? true : filter === 'enabled' ? c.enabled : filter === 'paused' ? !c.enabled : !!c.last_error;
}

/** How many channels each filter pill shows. */
export function filterCounts(channels: Channel[]): Record<ChannelFilter, number> {
	return {
		all: channels.length,
		enabled: channels.filter((c) => c.enabled).length,
		paused: channels.filter((c) => !c.enabled).length,
		issues: channels.filter((c) => c.last_error).length
	};
}

/**
 * The stat strip's numbers: the channels, those with an issue, and the
 * distinct events they subscribe to.
 */
export function summaryCounts(channels: Channel[]): { total: number; issues: number; subscribedEvents: number } {
	return {
		total: channels.length,
		issues: channels.filter((c) => c.last_error).length,
		subscribedEvents: new Set(channels.flatMap((c) => c.subscribed_events)).size
	};
}
