// Helpers for reading the transcoder stats payload.
import type { TranscodeStatsView } from '$lib/types/api.gen';

/** Number of transcode tasks in `status`; 0 when the status is absent. */
export function taskCount(stats: TranscodeStatsView, status: string): number {
	return stats.tasks_by_status?.[status] ?? 0;
}
