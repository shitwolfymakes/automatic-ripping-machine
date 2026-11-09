// Words the dashboard's feedback banner after a bulk delete. Pure; the page
// owns the banner state.
import type { BulkDeleteJobsResponse } from '$lib/types/api.gen';

export interface BulkFeedback {
	type: 'success' | 'error';
	message: string;
}

// The response reports deleted_ids plus skipped_non_terminal (in-flight jobs
// the backend refused).
export function bulkDeleteFeedback(result: BulkDeleteJobsResponse): BulkFeedback {
	const skipped = result.skipped_non_terminal.length;
	return {
		type: skipped > 0 ? 'error' : 'success',
		message:
			skipped > 0
				? `Deleted ${result.deleted_ids.length}, skipped ${skipped} in-flight job(s)`
				: `Deleted ${result.deleted_ids.length} job(s)`
	};
}
