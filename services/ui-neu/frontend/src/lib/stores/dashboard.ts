import { createPollingStore } from './polling';
import { fetchDashboardSnapshot, STICKY_FIELDS } from '$lib/api/dashboard';
import type { DashboardData, DashboardSnapshot } from '$lib/api/dashboard';
const emptyDashboard: DashboardData = {
	db_available: true,
	arm_online: false,
	active_jobs: [],
	drives_online: 0,
	drive_names: {},
	iso_sources: {},
	iso_source_kinds: {},
	drive_source_kinds: {},
	preparing: [],
	notification_count: 0,
	ripping_enabled: true,
	makemkv_key_valid: null,
	makemkv_key_checked_at: null,
	transcoder_online: false,
	transcoder_stats: null,
	active_transcodes: []
};

// Booleans that flip to `false` on a single backend blip (RemoteProtocolError,
// timeout, etc). Don't pop the sidebar to "Cannot reach …" until we've seen
// two consecutive `false` polls — one stale reading absorbs transient blips
// while real outages still surface within ~10s.
const TWO_STRIKE_FIELDS = ['arm_online', 'transcoder_online'] as const satisfies readonly (keyof DashboardData)[];

let lastGood: DashboardData = emptyDashboard;
const consecutiveFalse: Record<(typeof TWO_STRIKE_FIELDS)[number], number> = {
	arm_online: 0,
	transcoder_online: 0
};

// A sticky field comes back `null` when its endpoint blipped on this
// poll; hold the previous value so a transient timeout doesn't flicker
// badges/counts to zero.
function holdStickyFields(fresh: DashboardSnapshot, previous: DashboardData): DashboardData {
	const merged = { ...fresh } as DashboardData;
	for (const key of STICKY_FIELDS) {
		if (fresh[key] === null || fresh[key] === undefined) {
			(merged[key] as unknown) = previous[key];
		}
	}
	return merged;
}

function countFalseStreaks(data: DashboardSnapshot): void {
	for (const key of TWO_STRIKE_FIELDS) {
		if (data[key] === false) {
			consecutiveFalse[key]++;
		} else {
			consecutiveFalse[key] = 0;
		}
	}
}

// First `false` after a `true` — keep showing online (debounce
// a single-poll blip). A second consecutive `false` surfaces
// the real outage on the next poll, ~5s later.
function debounceOffline(
	data: DashboardData,
	streaks: Record<(typeof TWO_STRIKE_FIELDS)[number], number>
): DashboardData {
	const debounced = { ...data } as DashboardData;
	for (const key of TWO_STRIKE_FIELDS) {
		if (streaks[key] === 1) {
			(debounced[key] as unknown) = true;
		}
	}
	return debounced;
}

async function fetchDashboardSticky(): Promise<DashboardData> {
	const fresh = await fetchDashboardSnapshot();
	const merged = holdStickyFields(fresh, lastGood);
	countFalseStreaks(fresh);
	lastGood = debounceOffline(merged, consecutiveFalse);
	return lastGood;
}

/** Singleton dashboard store — survives page navigations, retains last-known data. */
export const dashboard = createPollingStore(fetchDashboardSticky, emptyDashboard, 5000);
