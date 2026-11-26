import type { TranscodeTaskView } from '$lib/types/api.gen';

/** Sort transcode tasks: in_progress first, then newest created_at. */
export function sortTranscodeTasks(a: TranscodeTaskView, b: TranscodeTaskView): number {
	const aActive = a.status === 'in_progress' ? 1 : 0;
	const bActive = b.status === 'in_progress' ? 1 : 0;
	if (aActive !== bActive) return bActive - aActive; // active first
	const aT = a.created_at ?? '';
	const bT = b.created_at ?? '';
	return bT < aT ? -1 : bT > aT ? 1 : 0; // newest first (ISO strings sort lexicographically)
}
